# Phase 1 학습 가이드 — 프론트엔드 SSE 클라이언트 `lib/chat.ts`

산출물: `frontend/lib/chat.ts` 하나.  
백엔드 `backend/routers/chat.py`의 `/chat/stream`이 무엇을 보내는지 읽고,  
그것을 받는 프론트 코드를 단계별로 만든다.

---

## Step 1: 백엔드가 보내는 것 읽기

`backend/routers/chat.py`의 `event_generator()`를 보면 백엔드가 보내는 것은
**SSE(Server-Sent Events)** 포맷의 이벤트 스트림이다.

SSE 한 블록은 이렇게 생겼다:
```
event: token
data: {"content": "안녕"}

```
(끝에 **빈 줄** 하나가 블록 구분자)

백엔드 코드에서 `yield {"event": "token", "data": ...}` 한 줄이 위 블록 하나가 된다.
`EventSourceResponse`가 dict를 SSE 형식으로 직렬화해서 내보낸다.

### 백엔드가 보내는 이벤트 6종

백엔드 docstring의 이벤트 프로토콜을 그대로 옮기면:

```
event: token
data: {"content": "안"}                ← 일반 답변 토큰. 여러 번 온다.

event: message
data: {"response": "전체 답변", "thread_id": "...", "status": "completed"}
                                        ← RAG 답변. 토큰 없이 완성본이 1회 온다.

event: blocked
data: {"response": "욕설 감지...", "thread_id": "..."}
                                        ← 욕설 차단. 이후 스트림 종료.

event: confirmation_required
data: {"thread_id": "...", "tool": "submit_refund_request", "args": {"order_id": "ORD-1", ...}}
                                        ← 환불 본인확인. 이후 스트림 종료.

event: done
data: {"thread_id": "...", "status": "completed"}
                                        ← 정상 종료 신호.

event: error
data: {"detail": "오류 내용"}           ← 스트림 도중 오류.
```

### 왜 `token`과 `message`가 따로 있나?

백엔드 코드에서 찾으면:

```python
# 일반 답변: 토큰이 생성될 때마다 즉시 전송
yield {"event": "token", "data": json.dumps({"content": chunk.content})}

# RAG 답변: 검색 결과로 할루시네이션 검사 후 완성본을 한 번에 전송
checked = check_hallucination(answer, combined_context)
yield {"event": "message", "data": json.dumps({"response": checked, ...})}
```

RAG(문서 검색)를 쓸 때는 토큰을 모아뒀다가 `check_hallucination()`을 거친 후 한 번에 보낸다.
검사 전 틀린 내용이 화면에 먼저 뜨면 안 되기 때문이다.
→ **프론트는 두 경우를 다르게 처리해야 한다.**

---

## Step 2: 프론트가 받는 방법 — `ChatEvent` 타입

백엔드 이벤트 6종을 TypeScript 타입으로 옮긴다.
백엔드 `data` JSON의 필드명과 **1:1**로 일치시켜야 한다.

```ts
// lib/chat.ts

export type ChatEvent =
  | { type: "token";                content: string }
  | { type: "message";              response: string; thread_id: string; status: string }
  | { type: "blocked";              response: string; thread_id: string }
  | { type: "confirmation_required"; thread_id: string; tool: string; args: Record<string, unknown> }
  | { type: "done";                 thread_id: string; status: string }
  | { type: "error";                detail: string };
```

`type` 필드는 SSE의 `event:` 라인 값이다 (`token`, `message` 등).
나머지 필드는 `data:` 라인의 JSON 키다.

---

## Step 3: SSE를 어떻게 읽나 — `fetch` + `ReadableStream`

브라우저의 `EventSource`는 **GET 요청만** 가능하다.
우리는 `{message, thread_id, user_id}`를 **POST 바디**로 보내야 하므로 `fetch`를 써야 한다.

`fetch`로 POST를 하면 응답 본문을 **스트림**으로 읽을 수 있다:

```ts
const res = await fetch(`${API_BASE_URL}/chat/stream`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

const reader = res.body!.getReader();   // 스트림 리더
const decoder = new TextDecoder();     // 바이트 → 문자열
```

`reader.read()`를 반복 호출하면 네트워크에서 **바이트 덩어리(chunk)**가 조금씩 온다.
`decoder.decode(value, { stream: true })`로 문자열로 바꾼다.

---

## Step 4: 버퍼 누적 → 블록 분리

네트워크는 SSE 블록 경계에서 깔끔하게 끊겨 오지 않는다.

```
실제 도착 예시:
  청크1: "event: tok"
  청크2: "en\ndata: {\"content\":\"안\"}\r\n\r\nevent: tok"
  청크3: "en\ndata: {\"content\":\"녕\"}\r\n\r\n"
```

그래서 버퍼에 계속 이어 붙이고, **빈 줄**을 기준으로 블록을 나눠야 한다:

```ts
let buffer = "";

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  buffer += decoder.decode(value, { stream: true });  // 이어 붙이기

  const blocks = buffer.split(/\r\n\r\n|\n\n/);       // 빈 줄로 분리
  buffer = blocks.pop() ?? "";                        // 마지막 미완성 블록은 보관

  for (const block of blocks) {
    // 완성된 블록만 파싱
  }
}
```

`blocks.pop()`이 중요하다. 마지막 조각은 아직 다음 청크가 안 왔을 수 있으니
버퍼에 돌려놓는다. 빈 줄이 오기 전까지 쌓아둔다.

### ⚠️ CRLF 함정

`sse-starlette`(백엔드)는 SSE 규격대로 줄 끝을 **`\r\n`**으로 보낸다.
블록 구분자는 `\r\n\r\n`이다.

`buffer.split("\n\n")`만 쓰면 **블록이 영영 안 나뉜다** →
모든 이벤트가 버퍼에 갇혀 0개 방출 → HTTP 200인데 화면이 비는 증상.

해결: `split(/\r\n\r\n|\n\n/)` — CRLF와 LF 모두 처리.

---

## Step 5: 한 블록 파싱 — `parseSseBlock`

블록 하나는 이렇게 생겼다:
```
event: token\r\n
data: {"content":"안"}\r\n
\r\n
```

라인을 한 줄씩 읽어서 `event:`와 `data:`를 뽑는다:

```ts
function parseSseBlock(block: string): ChatEvent | null {
  let eventType = "message";       // event: 라인이 없으면 기본값
  const dataLines: string[] = [];

  for (const line of block.split("\n")) {
    const trimmed = line.trim();   // \r 제거
    if (trimmed.startsWith("event:"))
      eventType = trimmed.slice(6).trim();          // "token", "blocked" 등
    else if (trimmed.startsWith("data:"))
      dataLines.push(trimmed.slice(5).trim());      // JSON 문자열
  }

  if (dataLines.length === 0) return null;          // 빈 블록 무시

  try {
    const data = JSON.parse(dataLines.join("\n"));
    return { type: eventType, ...data } as ChatEvent;
    //          ↑ "token"    ↑ { content: "안" }
    //       → { type: "token", content: "안" }
  } catch {
    return null;
  }
}
```

`{ type: eventType, ...data }`로 합치면 `ChatEvent` 타입의 객체가 된다.

---

## Step 6: `confirmChat` — 환불 확인/취소

`confirmation_required` 이벤트를 받은 뒤, 사용자가 승인/취소하면
**비스트리밍 `POST /chat/confirm`** 을 호출해서 에이전트를 재개한다.

백엔드 `/chat/confirm` 엔드포인트는 `{ thread_id, decision, user_id }`를 받는다
(`backend/routers/chat.py`의 `confirm()` 참고).

```ts
export async function confirmChat(body: {
  thread_id: string;
  decision: "approve" | "reject";
  user_id: string;
}): Promise<{ response: string; status: string }> {
  const res = await fetch(`${API_BASE_URL}/chat/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const json = await res.json();
  return { response: json.data.response, status: json.data.status };
}
```

---

## 완성 코드 — `lib/chat.ts`

```ts
import { API_BASE_URL } from "./api";

export type ChatEvent =
  | { type: "token";                 content: string }
  | { type: "message";               response: string; thread_id: string; status: string }
  | { type: "blocked";               response: string; thread_id: string }
  | { type: "confirmation_required"; thread_id: string; tool: string; args: Record<string, unknown> }
  | { type: "done";                  thread_id: string; status: string }
  | { type: "error";                 detail: string };

function parseSseBlock(block: string): ChatEvent | null {
  let eventType = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    const t = line.trim();
    if (t.startsWith("event:")) eventType = t.slice(6).trim();
    else if (t.startsWith("data:")) dataLines.push(t.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  try {
    return { type: eventType, ...JSON.parse(dataLines.join("\n")) } as ChatEvent;
  } catch {
    return null;
  }
}

export async function streamChat(
  body: { message: string; thread_id: string; user_id: string },
  onEvent: (e: ChatEvent) => void,
): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.body) throw new Error("No response body");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split(/\r\n\r\n|\n\n/);   // CRLF + LF 모두 처리
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      if (!block.trim()) continue;
      const evt = parseSseBlock(block);
      if (evt) onEvent(evt);
    }
  }
}

export async function confirmChat(body: {
  thread_id: string;
  decision: "approve" | "reject";
  user_id: string;
}): Promise<{ response: string; status: string }> {
  const res = await fetch(`${API_BASE_URL}/chat/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const json = await res.json();
  return { response: json.data.response, status: json.data.status };
}
```

---

## 백엔드 ↔ 프론트 대응 정리

| 백엔드 코드 (`chat.py`) | 프론트 코드 (`chat.ts`) |
|---|---|
| `yield {"event":"token","data":...}` | `onEvent({type:"token", content:"..."})` |
| `yield {"event":"message","data":...}` | `onEvent({type:"message", response:"..."})` |
| `yield {"event":"blocked","data":...}` | `onEvent({type:"blocked", response:"..."})` |
| `yield {"event":"confirmation_required","data":...}` | `onEvent({type:"confirmation_required", thread_id, tool, args})` |
| `yield {"event":"done","data":...}` | `onEvent({type:"done", ...})` |
| `yield {"event":"error","data":...}` | `onEvent({type:"error", detail:"..."})` |
| `EventSourceResponse(event_generator())` | `fetch` + `res.body.getReader()` |

---

## 커밋

```
feat(frontend): add /chat/stream sse client (lib/chat.ts)
```

## 다음 단계 (Phase 2)

`streamChat(body, onEvent)`가 완성됐으니, Phase 2에서는 이걸 호출해서
`onEvent`로 받은 이벤트를 React state에 반영하는 채팅 UI를 만든다.
