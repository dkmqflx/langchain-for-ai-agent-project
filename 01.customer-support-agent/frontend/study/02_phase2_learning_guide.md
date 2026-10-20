# Phase 2 학습 가이드 — 채팅 UI 기본 스트리밍 (plain shadcn/ui)

> **목표**: Phase 1의 `lib/chat.ts`를 써서 일반 답변 토큰이 **실시간으로** 화면에 흐르게 한다.
> AI SDK/AI Elements 없이 **shadcn/ui + Tailwind로 말풍선·입력창을 직접** 만든다.
>
> 손대는 파일: `app/page.tsx` (+ 선택적으로 `lib/useChatStream.ts` 커스텀 훅).

---

## 왜 `useChat`을 안 쓰나 (1분)

`useChat`은 AI SDK의 "UI Message Stream" 형식만 받습니다. 우리 백엔드는 **커스텀 SSE**(`event: token` 등)를
내보내므로, 둘을 맞추려면 백엔드를 AI SDK 포맷으로 바꾸거나(C안) Node 변환 레이어를 두어야(B안) 합니다.
A안은 그 대신 **Phase 1의 `streamChat`**가 이미 이벤트를 콜백으로 주므로, 우리는 그 콜백으로
**그냥 React state를 갱신**하면 됩니다. 추가 라이브러리가 필요 없습니다.

---

## 학습 흐름도

```
입력창 전송
   ↓  streamChat({message, thread_id, user_id}, onEvent)
onEvent(evt) {
   token   → 진행 중 assistant 메시지에 content 누적(append)   ← 실시간 타이핑
   message → assistant 메시지를 response로 교체/확정(RAG 검사본, 1회)
   done    → streaming = false
   error   → 에러 메시지 표시
}
   ↓  setMessages(...)
React 리렌더 → 말풍선 갱신
```

핵심 한 줄: **"이벤트가 올 때마다 state를 바꾸면, React가 알아서 다시 그린다."**

---

## Step 1: 상태 설계 (10분)

```ts
type ChatMessage = { role: "user" | "assistant"; content: string };

const [messages, setMessages] = useState<ChatMessage[]>([]);
const [input, setInput] = useState("");
const [streaming, setStreaming] = useState(false);
// thread_id: 대화 단위(같으면 맥락 유지). user_id: 임시 상수 또는 입력값.
const threadId = useRef(crypto.randomUUID()).current;
const userId = "u1";
```

### 학습 질문
- [ ] `thread_id`를 매 전송마다 새로 만들면 무슨 일이 생기나? (힌트: 단기 기억이 끊김)
- [ ] 왜 `streaming` 플래그가 필요한가? (힌트: 전송 버튼 비활성화/로딩 표시)

---

## Step 2: 전송 핸들러 + `onEvent` 분기 (가장 중요) (15분)

```ts
async function handleSend() {
  const text = input.trim();
  if (!text || streaming) return;
  setInput("");
  setStreaming(true);

  // 1) 내 메시지 + 빈 assistant 자리(여기에 토큰을 누적)
  setMessages((m) => [...m, { role: "user", content: text }, { role: "assistant", content: "" }]);

  await streamChat({ message: text, thread_id: threadId, user_id: userId }, (evt) => {
    setMessages((m) => {
      const next = [...m];
      const last = next.length - 1;             // 마지막 = 진행 중 assistant
      switch (evt.type) {
        case "token":                            // 일반 답변: 조각 누적
          next[last] = { role: "assistant", content: next[last].content + evt.content };
          break;
        case "message":                          // RAG 답변: 완성본 1회 교체
          next[last] = { role: "assistant", content: evt.response };
          break;
        case "error":
          next[last] = { role: "assistant", content: `⚠️ 오류: ${evt.detail}` };
          break;
        // blocked / confirmation_required → Phase 3에서 처리
      }
      return next;
    });
    if (evt.type === "done" || evt.type === "error") setStreaming(false);
  });
}
```

### ⚠️ `token`(누적) vs `message`(교체)
- `token`은 **조각**입니다 → `content + evt.content`로 **이어 붙입니다.**
- `message`는 **완성본**입니다(RAG 검사본) → 통째로 **교체**합니다. 누적하면 안 됩니다.

### 학습 질문
- [ ] 빈 assistant 메시지를 미리 넣어두는 이유는? (힌트: 누적할 자리)
- [ ] `message`를 누적(append)하면 어떤 버그가 생기나?

---

## Step 3: UI 컴포넌트 (plain) (10분)

- **말풍선**: `messages.map(...)`으로 그리되 `role`에 따라 정렬/배경색을 다르게.
  shadcn 카드/유틸 + Tailwind(`justify-end`, `bg-primary/10` 등)로 충분합니다.
- **입력창**: shadcn `Input` + `Button`. `streaming`이면 버튼 비활성화.
- **스트리밍 표시**: 진행 중 assistant 말풍선 끝에 점멸 커서나 작은 spinner.
- **마크다운**(선택): 답변에 목록/코드가 많으면 `react-markdown` 같은 **경량 라이브러리만** 추가.

> `frontend/AGENTS.md` 주의: 이 Next는 익숙한 Next가 아닐 수 있으니, 클라이언트 컴포넌트 규칙 등은
> 코드 작성 전 `node_modules/next/dist/docs/`의 해당 가이드를 먼저 확인.

---

## 검증

- [ ] 일반 질문 → 토큰이 한 글자씩 실시간 누적 렌더.
- [ ] 문서 기반 질문(RAG) → 완성본이 한 번에 뜸(토큰 흐름 없이).
- [ ] 전송 중 버튼 비활성화 + 스트리밍 표시.
- [ ] 같은 `thread_id` 유지 시 후속 질문에 맥락이 이어짐(단기 기억).

## 검증 체크리스트 (개념 이해)
- [ ] "이벤트 → setState → 리렌더" 흐름을 설명할 수 있다.
- [ ] `token` 누적과 `message` 교체를 구분할 수 있다.
- [ ] `thread_id`가 대화 맥락 유지의 키임을 안다.

---

## 커밋

```
feat(frontend): streaming chat ui consuming /chat/stream sse
```

## 다음 단계
- **Phase 3**: `blocked`(차단)·`confirmation_required`(환불 본인확인) 이벤트 처리.
