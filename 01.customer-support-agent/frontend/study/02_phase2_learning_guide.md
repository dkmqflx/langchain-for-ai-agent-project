# Phase 2 학습 가이드 — 채팅 UI 기본 스트리밍 (`useChat` + AI Elements)

**목표**: `useChat`으로 Phase 1의 `/chat/stream`에 연결하고, 일반 답변 토큰이 화면에 실시간으로 흐르게 한다.

---

## 🔴 선결 과제 (Phase 2 착수 전 반드시 해결)

plan.md Phase 0 메모에 기록된 **`next build` 실패**를 먼저 고쳐야 합니다.

- **증상**: `npm run dev`는 뜨지만(타입에러 무시) `npm run build`(프로덕션 빌드)가 깨짐.
- **원인**: AI Elements 컴포넌트가 구 Base UI API(`openDelay`/`closeDelay`, `preventBaseUIHandler` 등)로 작성됐는데,
  설치된 `@base-ui/react@1.5.0`에는 그 prop이 없는 **버전 드리프트**.
- **영향 파일**: `inline-citation`, `attachments`, `prompt-input`, `context`, `schema-display`, `voice-selector` 등 —
  **우리가 쓸 `prompt-input` 포함**.
- **해결 후보**: ① Base UI 호환 버전 핀, ② 해당 컴포넌트 수동 패치, ③ ai-elements 레지스트리 갱신 대기.
- **금지**: `typescript.ignoreBuildErrors`로 덮기. 레포의 "공식 문서대로" 표준에 어긋남.

> 검증: 먼저 `npm run build`를 돌려 깨지는 파일을 확인하고, 우리가 실제로 import하는 컴포넌트(`prompt-input` 등)만
> 우선 고쳐도 Phase 2 진행에는 충분합니다. 전부 한 번에 고칠 필요는 없습니다.

---

## 학습 흐름도

```
app/page.tsx (클라이언트 컴포넌트, "use client")
     │
     │  const { messages, sendMessage, status } = useChat({ transport })
     ▼
DefaultChatTransport({ api: `${NEXT_PUBLIC_API_URL}/chat/stream`,
                       prepareSendMessagesRequest: 바디를 백엔드 스키마로 변환 })
     │  POST /chat/stream  ← Phase 1에서 만든 v6 스트림
     ▼
messages 배열이 토큰마다 갱신 → AI Elements 컴포넌트가 렌더
     ▼
<Conversation> → <Message> → <MessageContent> → <MessageResponse>(마크다운)
<PromptInput>  → 입력/전송
```

---

## Step 1: `useChat`의 v6 반환값 (구버전과 다름!) (10분)

> ⚠️ **훈련 데이터의 `useChat`과 다릅니다.** v6에는 `input`/`handleInputChange`/`handleSubmit`이 없습니다.
> 아래는 설치된 `@ai-sdk/react@3.0.199`의 `UseChatHelpers` 타입에서 직접 확인한 반환값입니다.

```ts
const {
  messages,      // UIMessage[] — 화면에 그릴 대화 배열
  sendMessage,   // 메시지 전송 함수 (구버전 handleSubmit 대체)
  status,        // "submitted" | "streaming" | "ready" | "error" 등 — 로딩 표시에 사용
  error,         // Error | undefined
  stop,          // 스트리밍 중단
  regenerate,    // 마지막 답변 재생성
  setMessages,   // 메시지 배열 직접 수정
  addToolResult, // (Phase 3 참고) 도구 결과 주입
} = useChat({ transport });
```

핵심: **입력창의 텍스트 state는 우리가 직접 관리**하고(`useState`), 전송할 때 `sendMessage`를 호출합니다.

### 학습 질문
- [ ] `messages`는 누가 갱신하나? (힌트: 스트림 파트가 올 때마다 useChat 내부가)
- [ ] `status`의 값으로 무엇을 표현할 수 있나? (로딩 스피너/전송 버튼 비활성화)

---

## Step 2: 요청 바디를 백엔드 스키마에 맞추기 (가장 까다로운 부분) (10분)

문제: `useChat`은 기본적으로 `{ messages: [...] }`를 보냅니다.
하지만 우리 백엔드는 `{ message, thread_id, user_id }`를 받습니다. → **변환이 필요.**

해결: `DefaultChatTransport`의 `prepareSendMessagesRequest` 옵션(설치된 `ai@6.0.197`에서 확인된 정확한 이름).

```ts
import { DefaultChatTransport } from "ai";

const transport = new DefaultChatTransport({
  api: `${process.env.NEXT_PUBLIC_API_URL}/chat/stream`,
  prepareSendMessagesRequest: ({ messages, body }) => ({
    body: {
      message: messages[messages.length - 1]?.parts /* 마지막 사용자 입력 텍스트 추출 */,
      thread_id: body?.thread_id,   // 대화 단위 식별자
      user_id: body?.user_id,       // 임시 상수/입력값
    },
  }),
});
```

> 위 코드는 **형태 예시**입니다. `prepareSendMessagesRequest`의 정확한 인자/반환 형태는
> 공식 문서(https://ai-sdk.dev/docs/ai-sdk-ui)와 `node_modules/ai/dist/index.d.ts`의
> `PrepareSendMessagesRequest` 타입으로 한 번 더 확인하세요. (텍스트 추출은 `parts`에서 `type:"text"`를 찾는 방식)

### thread_id / user_id 관리
- `thread_id`: 대화 한 세션을 묶는 ID. 새 대화 시작 시 생성(`nanoid` 등), 이후 같은 값 유지 → 단기 기억 연결.
- `user_id`: 지금은 임시 상수 또는 입력값. (Phase 3·6에서 confirm/조회에 재사용)

### 학습 질문
- [ ] 왜 `messages` 전체가 아니라 마지막 메시지의 텍스트만 보내나? (백엔드 스키마가 `message` 단일 필드라서)
- [ ] `thread_id`를 새로고침 후에도 유지하려면 어디에 저장해야 하나? (localStorage/URL 등)

---

## Step 3: AI Elements 컴포넌트 조합 (검증된 export 이름) (10분)

> ⚠️ **plan.md의 컴포넌트 이름 일부가 실제 설치본과 다릅니다.** (advisor 지적 사항)
> 아래는 `components/ai-elements/*.tsx`에서 **실제로 export하는** 이름입니다.

| plan.md 표기 | 실제 설치된 export | 파일 |
|---|---|---|
| `Conversation` | `Conversation`, `ConversationContent`, `ConversationEmptyState`, `ConversationScrollButton` | `conversation.tsx` |
| `Message`/`MessageContent` | `Message`, `MessageContent` | `message.tsx` |
| **`Response`** ❌ | ✅ **`MessageResponse`** | `message.tsx` |
| `PromptInput` | `PromptInput`, `PromptInputTextarea`, `PromptInputSubmit`, `PromptInputBody`, `PromptInputTools` 등 | `prompt-input.tsx` |
| **`Loader`** ❌ | ✅ **`Shimmer`** (또는 `status`로 직접 표시) | `shimmer.tsx` |

**규칙**: AI Elements는 `@/components/ai-elements/`에 **코드로 설치**되어 직접 커스터마이즈 가능합니다.
정확한 props는 항상 해당 `.tsx` 파일을 직접 열어 확인하세요(상상 금지 — 이게 plan/CLAUDE.md의 "공식 문서대로" 표준).

### 대략적인 골격
```tsx
"use client";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { Conversation, ConversationContent } from "@/components/ai-elements/conversation";
import { Message, MessageContent, MessageResponse } from "@/components/ai-elements/message";
import { PromptInput, PromptInputTextarea, PromptInputSubmit } from "@/components/ai-elements/prompt-input";

export default function ChatPage() {
  const { messages, sendMessage, status } = useChat({ transport });
  return (
    <Conversation>
      <ConversationContent>
        {messages.map((m) => (
          <Message key={m.id} from={m.role}>
            <MessageContent>
              {/* m.parts 중 text 파트를 MessageResponse로 마크다운 렌더 */}
            </MessageContent>
          </Message>
        ))}
      </ConversationContent>
      <PromptInput onSubmit={/* sendMessage 호출 */}>
        <PromptInputTextarea />
        <PromptInputSubmit status={status} />
      </PromptInput>
    </Conversation>
  );
}
```
> props(`from`, `onSubmit`, `status` 등)는 각 `.tsx` 파일에서 실제 시그니처를 확인 후 채우세요.

---

## Step 4: 메시지 파트 렌더링 (5분)

v6 `UIMessage`는 `content` 문자열이 아니라 **`parts` 배열**입니다.
```ts
message.parts.forEach((part) => {
  if (part.type === "text") { /* MessageResponse로 렌더 */ }
  // Phase 3: part.type === "data-blocked" / "data-confirmation" 처리
});
```
- 일반 답변은 `text` 파트만 신경 쓰면 됩니다.
- `data-*` 파트(차단/환불확인) 처리는 **Phase 3**에서.

---

## 검증

- [ ] 일반 질문 입력 → 토큰이 한 글자씩 실시간으로 누적 렌더된다.
- [ ] 전송 중 `status`가 바뀌고 로딩 표시(Shimmer 등)가 보인다.
- [ ] 같은 `thread_id`로 새로고침 후에도 대화 맥락이 이어진다(단기 기억 — 백엔드 InMemorySaver와 연결).
- [ ] `npm run build`가 통과한다(선결 과제 해결 확인).

---

## 검증 체크리스트 (개념)
- [ ] v6 `useChat`이 `input`/`handleSubmit`이 아니라 `sendMessage`/`status`를 준다는 걸 안다.
- [ ] `prepareSendMessagesRequest`로 바디를 백엔드 스키마에 맞추는 이유를 안다.
- [ ] `UIMessage.parts` 배열 구조를 이해한다.
- [ ] AI Elements가 코드로 설치되어 `.tsx`를 직접 봐야 정확한 props를 안다는 걸 안다.

---

## 커밋
```
feat(frontend): streaming chat ui with usechat + ai elements
```

## 다음 단계
- **Phase 3**: `data-blocked`(차단)·`data-confirmation`(환불 본인확인) 파트를 UI에서 처리.
