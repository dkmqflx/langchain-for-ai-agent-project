# Phase 6 학습 가이드 — 채팅 스트리밍 (SSE)

이 가이드는 Phase 6에서 추가된 스트리밍 채팅 흐름을 의존성 순서대로 학습할 수 있도록 구성되었습니다.

---

## Phase 6에서 새로 추가된 것

Phase 5까지는 에이전트가 **답변을 다 만들고 나서** 한 번에 보냈습니다.

```
[Phase 5까지]

고객: "AI 에이전트란 무엇인가요?"
Agent: (30초 동안 조용히 생각...)
Agent: "AI 에이전트란 목표를 달성하기 위해 스스로 도구를 선택하고
        행동하는 인공지능 시스템입니다. 예를 들어..." ← 완성 후 한 번에
```

고객은 답변이 완성될 때까지 **아무것도 볼 수 없습니다.** 화면이 멈춘 것처럼 느껴지죠.

Phase 6은 일반 답변을 **글자가 생성되는 즉시** 화면에 흘려줍니다.

```
[Phase 6 스트리밍]

고객: "AI 에이전트란 무엇인가요?"
화면: "AI 에이전트란" ← 즉시 나타남
화면: "AI 에이전트란 목표를" ← 계속 추가됨
화면: "AI 에이전트란 목표를 달성하기 위해" ← ...
화면: (완성될 때까지 계속 흘러나옴)
```

마치 ChatGPT나 Claude 웹 화면에서 답변이 타이핑되는 것처럼 보이는 것과 같은 원리입니다.

---

## ⭐ 가장 중요한 설계 결정: 왜 일반 답변만 스트리밍하나?

처음엔 "모든 답변을 다 스트리밍하면 되지 않나?" 하고 생각할 수 있습니다. 하지만 이 시스템에는 스트리밍과 충돌하는 두 가지 흐름이 있습니다.

### 문제 1: RAG 답변 — 할루시네이션 검사와 충돌

```
[RAG 흐름]

모델이 토큰 생성 → 토큰을 화면에 흘림 → ...
  ↓
스트리밍이 "끝난 뒤에" 할루시네이션 검사를 한다
  ↓
"이 답변은 거짓입니다. 수정된 내용: ..." ← 이미 화면에 다 보였는데!
```

RAG 답변은 GPT-4o-mini가 **통째로 교체**할 수 있습니다. 이미 화면에 흘러나간 토큰을 되돌릴 방법이 없습니다.

### 문제 2: 환불 흐름 — interrupt와 충돌

```
[환불 흐름]

모델이 submit_refund_request 호출 시도
  ↓
HumanInTheLoopMiddleware가 실행 직전 ⏸️ interrupt (완전히 멈춤)
  ↓
토큰이 더 이상 나오지 않음 → "환불 신청을 접수할까요?" 확인 카드를 띄워야 함
```

interrupt가 발생하면 토큰 스트리밍이 아니라 **확인 카드**를 화면에 표시해야 합니다.

### 해결: 단일 엔드포인트가 내부에서 분기

```
[Phase 6 해결]

단일 POST /chat/stream 엔드포인트가 agent.astream을 관찰하며 내부에서 분기:

  욕설 입력     → event:blocked       → 차단 메시지 표시, 끝
  일반 답변     → event:token (연속)  → 글자 실시간 누적, 마지막에 event:done
  RAG 답변      → 버퍼링 → 검사 → event:message 1회  → 완성본 한 번에 표시
  환불 interrupt → event:confirmation_required         → 확인 카드 표시
  예외          → event:error         → 오류 메시지 표시
```

프론트는 엔드포인트를 하나만 호출하면 됩니다. 어떤 흐름인지 미리 알 필요가 없습니다.

---

## SSE(Server-Sent Events)란?

### 비유: 식당의 두 가지 서비스 방식

```
[방식 A — 일반 HTTP 응답]
손님: "스파게티 주세요"
주방: (15분 동안 조용히 요리)
주방: 완성된 접시를 통째로 가져다 줌

[방식 B — SSE 스트리밍]
손님: "스파게티 주세요"
주방: (면 먼저) 바로 가져다 줌
주방: (소스) 또 가져다 줌
주방: (치즈 뿌려서) 또 가져다 줌
주방: "다 됐습니다" 알림
```

SSE(Server-Sent Events)는 방식 B입니다. 서버가 응답을 **작은 조각(이벤트)으로 나눠 순서대로** 보냅니다. 클라이언트(브라우저)는 연결을 열어두고 이벤트가 올 때마다 받아 처리합니다.

### SSE 메시지 형식

실제 네트워크를 통해 전달되는 텍스트는 이렇게 생겼습니다:

```
event: token
data: {"content": "AI 에이전트란"}

event: token
data: {"content": " 목표를 달성하기"}

event: done
data: {"thread_id": "abc123", "status": "completed"}
```

핵심 규칙 두 가지:
- `event:` 줄이 이벤트 이름
- `data:` 줄이 JSON 데이터
- 이벤트와 이벤트 사이는 **빈 줄(`\n\n`)** 로 구분

---

## 학습 흐름도

```
[Phase 6에서 추가된 파일]

backend/agent/streaming.py  → 스트림 청크 판별 순수 함수 3종
backend/routers/chat.py     → POST /chat/stream 엔드포인트 추가
                               (기존 /chat, /chat/confirm 불변)
frontend/lib/chat.ts        → SSE 호출·파싱 함수 + 타입
frontend/app/page.tsx       → 채팅 UI (스트리밍 소비)

[전체 흐름]

브라우저: POST /chat/stream {"message", "thread_id", "user_id"}
  ↓ (연결 유지)
백엔드: agent.astream(stream_mode=["updates","messages"]) 관찰
        (Before Guardrail은 에이전트 내부 before_agent 미들웨어가 담당 →
         updates 스트림에서 blocked 신호 감지)
  ↓
  ├── 욕설 → event:blocked → 연결 종료
  ├── 일반 토큰 → event:token (여러 번) → event:done
  ├── RAG 답변 → 버퍼링 → 검사 → event:message → event:done
  └── interrupt → event:confirmation_required → 연결 종료
  ↓
브라우저: 이벤트 타입에 따라 화면 갱신
```

---

## Step 1: `agent/streaming.py` 읽기 — 청크 판별 순수 함수 (15분)

### 목표

LangGraph `astream`이 토큰을 어떤 형태로 주는지, 그 중 어떤 것이 "사용자에게 보여줄 최종 답변 토큰"인지 이해

---

### 핵심 개념 1: astream이 주는 것들

`agent.astream(stream_mode=["updates","messages"])`는 `(mode, payload)` 튜플을 yield합니다. mode가 무엇이냐에 따라 payload 형태가 달라집니다.

```
mode == "messages"  →  payload == (message_chunk, metadata)
                        message_chunk: AIMessageChunk (LLM 토큰) 또는 ToolMessage 등
                        metadata:      {"langgraph_node": "model"} 등 내부 노드 정보

mode == "updates"   →  payload == {"__interrupt__": (...)} 또는 {"model": {...}} 등
                        interrupt 여부를 여기서 확인
```

문제는 `messages` 모드에서 오는 `AIMessageChunk`가 **두 종류**라는 점입니다:

```
[종류 A — 최종 답변 토큰] 화면에 흘려야 함
AIMessageChunk(content="AI 에이전트란", tool_call_chunks=[])

[종류 B — 도구 호출 청크] 화면에 흘리면 안 됨 (내부 구조)
AIMessageChunk(content="", tool_call_chunks=[{"name":"search_documents", ...}])
```

도구 호출 청크는 모델이 `search_documents` 같은 도구를 호출할 때 나오는 내부 청크입니다. 사용자에게 보여주면 안 됩니다.

---

### 핵심 개념 2: 판별 함수 3종

`streaming.py`는 이 구분을 위한 **순수 함수** 3개를 제공합니다 (I/O 없음, 테스트 가능):

```python
def is_final_answer_chunk(chunk, metadata) -> bool:
    """이 청크가 사용자에게 보여줄 '최종 답변' 토큰인지 판별."""
    return (
        isinstance(chunk, AIMessageChunk)
        and metadata.get("langgraph_node") == "model"  # model 노드에서 온 것만
        and not chunk.tool_call_chunks                 # 도구 호출 청크 제외
        and bool(chunk.content)                        # 빈 청크 제외
    )
```

조건 4개를 모두 통과해야 "최종 답변 토큰"으로 인정합니다. 하나라도 어긋나면 무시합니다.

```python
def is_search_tool_result(chunk) -> bool:
    """search_documents 도구 결과(ToolMessage)인지 판별."""
    return isinstance(chunk, ToolMessage) and chunk.name == "search_documents"
```

`search_documents` 결과가 등장했다는 것은 RAG 흐름이 진행 중이라는 신호입니다. 이후 나오는 최종 답변 토큰은 버퍼에 담아야 합니다.

```python
def extract_interrupt_action(update_payload):
    """updates 모드 payload에서 환불 interrupt action을 추출."""
    interrupts = update_payload.get("__interrupt__")
    if not interrupts:
        return None
    return interrupts[0].value["action_requests"][0]
```

`updates` 모드에서 `__interrupt__` 키가 있으면 환불 본인 확인 요청이 발생한 것입니다. `action_requests[0]`에 `{"name", "args", "description"}`이 담겨 있습니다.

---

### 핵심 개념 3: 왜 별도 파일로 분리했나?

```
[분리하지 않은 경우]
chat.py 안에 판별 로직이 섞여 있음 → 테스트하려면 FastAPI + LangGraph + DB 다 띄워야 함

[분리한 경우]
streaming.py: 순수 함수 (import만 하면 테스트 가능)
chat.py: 위 함수를 호출하는 엔드포인트

→ tests/test_streaming.py에서 네트워크/DB 없이 pytest로 빠르게 테스트
```

이 프로젝트에서 처음으로 단위 테스트가 추가된 파일입니다.

---

### 학습 질문

- `is_final_answer_chunk`에서 `langgraph_node == "model"` 조건을 빼면 어떤 청크가 잘못 포함될까?
- `search_documents` 결과는 `messages` 모드에서 오는가, `updates` 모드에서 오는가?
- `extract_interrupt_action`이 None을 반환하면 어떤 상황인가?

---

## Step 2: `routers/chat.py` 읽기 — `POST /chat/stream` (30분)

### 목표

`astream` 루프에서 각 이벤트를 어떻게 분기해 SSE 이벤트로 내보내는지 이해

---

### 핵심 개념 1: EventSourceResponse와 generator

FastAPI에서 SSE를 구현하는 방법은 `sse-starlette`의 `EventSourceResponse`를 쓰는 것입니다.

```python
from sse_starlette import EventSourceResponse

@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    async def event_generator():
        yield {"event": "token", "data": '{"content": "안녕"}'}
        yield {"event": "done", "data": '{"status": "completed"}'}

    return EventSourceResponse(event_generator())
```

`event_generator`는 `{"event": ..., "data": ...}` 딕셔너리를 yield합니다. `data`는 **문자열**이어야 하므로 `json.dumps(...)`를 사용합니다.

---

### 핵심 개념 2: astream 루프와 분기

실제 `chat_stream` 내부 event_generator의 핵심 부분입니다:

```python
used_search = False          # search_documents 사용 여부
search_contexts: list[str] = []  # 할루시네이션 검사용
answer_buffer: list[str] = []    # RAG 답변 버퍼
interrupt_action = None

async for mode, payload in agent.astream(
    {"messages": [("human", request.message)]},
    config=config,
    context=AgentContext(user_id=request.user_id),
    stream_mode=["updates", "messages"],
):
    if mode == "updates":
        action = extract_interrupt_action(payload)
        if action is not None:
            interrupt_action = action
            break  # 환불 interrupt → 스트림 중단

    elif mode == "messages":
        chunk, metadata = payload
        if is_search_tool_result(chunk):
            used_search = True
            search_contexts.append(chunk.content)
        elif is_final_answer_chunk(chunk, metadata):
            if used_search:
                answer_buffer.append(chunk.content)  # RAG: 버퍼에 담기
            else:
                yield {"event": "token",            # 일반: 즉시 전송
                       "data": json.dumps({"content": chunk.content}, ensure_ascii=False)}
```

**흐름을 읽는 법:**

```
스트림 루프 중 updates 모드 → interrupt 확인 → 발견하면 break
스트림 루프 중 messages 모드 → 청크 종류 확인
  search_documents ToolMessage → used_search=True, 컨텍스트 수집
  최종 답변 AIMessageChunk → used_search 여부에 따라 분기
    False(일반): event:token 즉시 전송
    True(RAG):   버퍼에 누적
```

---

### 핵심 개념 3: 스트림 종료 후 분기

astream 루프가 끝나면 세 가지 경우를 처리합니다:

```python
# 경우 1: 환불 interrupt 발생 (루프 중 break)
if interrupt_action is not None:
    yield {"event": "confirmation_required",
           "data": json.dumps({
               "thread_id": request.thread_id,
               "tool": interrupt_action["name"],
               "args": interrupt_action["args"],
           }, ensure_ascii=False)}
    return  # 이후 event:done 없이 종료

# 경우 2: RAG 답변 (used_search=True, 버퍼에 뭔가 쌓인 경우)
if used_search and answer_buffer:
    combined_context = "\n\n---\n\n".join(search_contexts)
    answer = "".join(answer_buffer)
    checked = check_hallucination(answer, combined_context)  # 할루시네이션 검사
    yield {"event": "message",
           "data": json.dumps({"response": checked, "status": "completed"}, ...)}

# 경우 3: 모든 경우 공통 — 정상 종료 알림
yield {"event": "done",
       "data": json.dumps({"thread_id": request.thread_id, "status": "completed"}, ...)}
```

**비유: 편의점 배달**

```
루프 중  = 음식 만드는 중
  일반 답변 토큰  = 만들어지는 즉시 배달 (token)
  RAG 답변 토큰  = 품질 검사 통과할 때까지 보관 (buffer)

루프 종료 = 다 만들어짐
  interrupt → "확인이 필요합니다" 알림 (confirmation_required)
  RAG 완성 → 검사 통과본 한 번에 배달 (message)
  항상     → "배달 완료" 알림 (done)
```

---

### 핵심 개념 4: SSE 이벤트 프로토콜 정리

| event | data 필드 | 의미 |
|-------|-----------|------|
| `token` | `{"content": "..."}` | 일반 답변 토큰. 프론트에서 누적 |
| `message` | `{"response": "...", "thread_id": "...", "status": "completed"}` | RAG 답변 완성본 (할루시네이션 검사 통과) |
| `blocked` | `{"response": "...", "thread_id": "..."}` | Before 가드레일 차단 |
| `confirmation_required` | `{"thread_id": "...", "tool": "...", "args": {...}}` | 환불 본인 확인 필요 |
| `done` | `{"thread_id": "...", "status": "completed"}` | 스트림 정상 종료 |
| `error` | `{"detail": "..."}` | 처리 오류 |

---

### 학습 질문

- `stream_mode=["updates","messages"]`에서 `"updates"`를 빼면 어떤 기능이 동작하지 않을까?
- RAG 답변에서 `answer_buffer`가 비어 있는 경우(검색은 했지만 최종 답변 토큰이 없음)를 왜 `if used_search and answer_buffer:`로 방어하나?
- `event:confirmation_required` 이후 `return`하지 않으면 어떻게 될까? (힌트: `event:done`이 뒤따라옴)

---

## Step 3: `frontend/lib/chat.ts` 읽기 — SSE 파싱 (20분)

### 목표

브라우저에서 `fetch` + `ReadableStream`으로 SSE를 받아 파싱하는 흐름 이해

---

### 핵심 개념 1: 왜 `EventSource` 대신 `fetch`인가?

브라우저에는 SSE를 받는 내장 API인 `EventSource`가 있습니다. 하지만 `EventSource`는 **GET 요청만** 지원합니다. `POST /chat/stream`으로 메시지를 보내야 하므로 `fetch` + `ReadableStream`을 써야 합니다.

```
[EventSource — GET만 가능]
const es = new EventSource("/chat/stream?message=안녕"); // GET ✅
// POST 바디로 전달 불가 ❌

[fetch + ReadableStream — POST 가능]
const res = await fetch("/chat/stream", {
    method: "POST",
    body: JSON.stringify({message: "안녕", thread_id: "...", user_id: "..."})
});
// 응답 body를 스트리밍으로 읽음
const reader = res.body.getReader();
```

---

### 핵심 개념 2: 청크 읽기 → 이벤트 블록으로 나누기

`reader.read()`는 네트워크에서 바이트 단위로 데이터를 가져옵니다. SSE 이벤트 경계(`\n\n`)가 어디에 올지 모르기 때문에 **버퍼**가 필요합니다.

```typescript
const reader = res.body.getReader();
const decoder = new TextDecoder();
let buffer = "";

while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE 이벤트는 빈 줄(\n\n)로 구분
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? ""; // 마지막 미완성 블록은 다음 루프까지 보관

    for (const block of blocks) {
        if (!block.trim()) continue;
        const evt = parseSseBlock(block);
        if (evt) onEvent(evt);
    }
}
```

**비유: 전보 수신기**

```
전보가 끊어서 도착:
  수신: "event: toke"       (아직 블록 완성 안 됨 → buffer에 보관)
  수신: "n\ndata: {}\n\n"   (이제 \n\n 발견! 블록 완성 → parseSseBlock 호출)
```

---

### 핵심 개념 3: SSE 블록 파싱

```typescript
function parseSseBlock(block: string): ChatEvent | null {
    let event = "message";
    const dataLines: string[] = [];
    for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (dataLines.length === 0) return null;
    try {
        const data = JSON.parse(dataLines.join("\n"));
        return { type: event, ...data } as ChatEvent;
    } catch {
        return null;
    }
}
```

백엔드에서 보낸 것:
```
event: token
data: {"content": "안녕"}
```

파싱 후:
```typescript
{ type: "token", content: "안녕" }
```

`type` 필드가 이벤트 이름이 되고, `data` JSON의 내용이 나머지 필드로 펼쳐집니다.

---

### 핵심 개념 4: 타입 정의

```typescript
export type ChatEvent =
  | { type: "token"; content: string }
  | { type: "message"; response: string; status: string }
  | { type: "blocked"; response: string }
  | { type: "confirmation_required"; tool: string; args: Record<string, unknown> }
  | { type: "done"; status: string }
  | { type: "error"; detail: string };
```

백엔드 SSE 이벤트 프로토콜과 1:1로 대응합니다. TypeScript의 유니온 타입 덕분에 `switch(e.type)`에서 각 케이스의 필드가 정확하게 타입 추론됩니다.

---

### 학습 질문

- `buffer = blocks.pop() ?? ""`에서 `pop()`을 하는 이유는? 마지막 블록을 버리지 않고 보관하는 이유는?
- `parseSseBlock`이 `null`을 반환하는 경우는 어떤 경우인가?
- `EventSource` 대신 `fetch`를 쓰는 이유는?

---

## Step 4: `frontend/app/page.tsx` 읽기 — 채팅 UI (20분)

### 목표

이벤트 타입에 따라 화면을 어떻게 갱신하는지, 특히 토큰 누적 vs 완성본 교체 패턴 이해

---

### 핵심 개념 1: upsertAssistant — 토큰 누적과 완성본 교체

```typescript
function upsertAssistant(updater: (prev: string) => string) {
    setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last?.role === "assistant") {
            const copy = [...prev];
            copy[copy.length - 1] = { role: "assistant", content: updater(last.content) };
            return copy;
        }
        return [...prev, { role: "assistant", content: updater("") }];
    });
}
```

마지막 메시지가 assistant이면 그 content를 `updater` 함수로 변환합니다. 없으면 새 말풍선을 추가합니다. 두 가지 용도로 씁니다:

```typescript
// 토큰 누적: 기존 content에 새 토큰을 뒤에 붙임
upsertAssistant((prev) => prev + e.content);
// "안녕" → "안녕하" → "안녕하세" → "안녕하세요"

// 완성본 교체: 기존 content를 완전히 새 것으로 덮어씀
upsertAssistant(() => e.response);
// (버퍼에 있던 내용 무시) → 할루시네이션 검사 통과본으로 교체
```

---

### 핵심 개념 2: handleEvent — 이벤트별 처리

```typescript
function handleEvent(e: ChatEvent) {
    switch (e.type) {
        case "token":
            upsertAssistant((prev) => prev + e.content);  // 말풍선에 누적
            break;
        case "message":
            upsertAssistant(() => e.response);            // 완성본으로 교체
            break;
        case "blocked":
            upsertAssistant(() => `⚠️ ${e.response}`);  // 차단 안내
            break;
        case "confirmation_required":
            setPending({ tool: e.tool, args: e.args });  // 확인 카드 표시
            break;
        case "error":
            upsertAssistant(() => `❌ 오류: ${e.detail}`);
            break;
        case "done":
            break;  // 아무것도 안 함 (이미 다 처리됨)
    }
}
```

`token`과 `message`의 차이:

```
token:   prev + e.content → 말풍선이 타이핑되는 것처럼 글자 추가
message: () => e.response → 말풍선 전체를 새 내용으로 덮어씀 (RAG 완성본)
```

RAG 답변의 경우, 스트리밍 중에는 `token` 이벤트가 오지 않고 `message` 이벤트가 한 번만 옵니다. `message` 이벤트가 도착하는 순간 assistant 말풍선이 완성본으로 바로 나타납니다 (`upsertAssistant(() => e.response)`). 일반 답변과 달리 말풍선이 타이핑되는 중간 단계가 없습니다.

---

### 핵심 개념 3: thread_id 관리

```typescript
const threadId = useRef<string>(crypto.randomUUID());
```

`useRef`로 관리하므로 컴포넌트가 리렌더링되어도 값이 유지됩니다. 페이지를 처음 방문할 때 UUID를 한 번 생성하고 그 세션 동안 계속 씁니다. Phase 5의 checkpointer가 이 `thread_id`로 대화 상태를 기억합니다.

---

### 핵심 개념 4: 환불 확인 카드

```tsx
{pending && (
    <div className="...border-amber-300...">
        <p>환불 신청을 접수할까요? ({JSON.stringify(pending.args)})</p>
        <button onClick={() => decide("approve")}>확인(접수)</button>
        <button onClick={() => decide("reject")}>취소</button>
    </div>
)}
```

`confirmation_required` 이벤트가 오면 `pending` 상태가 설정되어 이 카드가 나타납니다. [확인] 또는 [취소]를 누르면 `decide` 함수가 기존 비스트리밍 엔드포인트를 호출합니다:

```typescript
async function decide(decision: "approve" | "reject") {
    const { response } = await confirmChat({
        thread_id: threadId.current,
        decision,
        user_id: USER_ID,
    });
    setMessages((prev) => [...prev, { role: "assistant", content: response }]);
    setPending(null);
}
```

환불 확인 후 응답은 `POST /chat/confirm`에서 받아 말풍선으로 추가합니다. SSE가 아니라 일반 JSON 응답입니다.

---

### 학습 질문

- `upsertAssistant`에서 `updater`를 함수로 받는 이유는? (힌트: React `setState` 배치 처리)
- RAG 답변을 받을 때 화면에서 어떤 순서로 변화가 일어나는가?
- `threadId`를 `useRef`로 관리하는 이유는? `useState`로 하면 어떤 문제가 생기나?

---

## PII 출력 마스킹 빈틈 — 학습용 한계

### 왜 이 빈틈이 생기나?

Phase 4에서 추가한 `PIIMiddleware`는 에이전트 출력에서 이메일을 지우고 카드번호를 마스킹합니다. 그런데 스트리밍에서는 이것이 완전히 보장되지 않습니다.

```
[비스트리밍 /chat]
에이전트 실행 완료 → PIIMiddleware 출력 마스킹 → 응답 반환
                      ↑ 여기서 마스킹 처리
                   결과: "카드번호 ****-****-****-5678"

[스트리밍 /chat/stream]
에이전트가 토큰 생성 → event:token 즉시 전송 → PIIMiddleware 출력 마스킹
                        ↑ 여기서 이미 보냄           ↑ 너무 늦음
                   결과: "카드번호 1234-5678-9012-3456" 이 토큰으로 흘러나올 수 있음
```

스트리밍 토큰은 `PIIMiddleware`의 **출력 마스킹 이전 단계**에 전송됩니다.

### 이 프로젝트에서 어떻게 다루나

설계 문서에 명시된 학습용 한계입니다:

```
입력 마스킹(apply_to_input)에 의존한다.
→ 사용자가 "카드번호는 1234-5678..." 같은 내용을 입력하면 Before Guardrail에서 처리됨
완전한 출력 PII 보장은 비스트리밍 /chat에서만 이뤄진다.
```

실제 서비스라면 두 가지 선택지가 있습니다:
1. 스트리밍을 포기하고 `/chat`만 사용
2. 출력 마스킹을 스트림 파이프라인 앞단에서 처리 (토큰을 보내기 전에 마스킹)

이 프로젝트는 학습 목적이므로 빈틈을 문서화하고 그대로 둡니다.

---

## 전체 흐름 실습 (20분)

```bash
# 1. 백엔드 실행
cd customer-support-agent/backend
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# === 일반 답변 토큰 스트리밍 ===

# 2. 일반 질문 → token 이벤트가 연속해서 옴, 마지막에 done
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"안녕하세요. 자기소개 해줘","thread_id":"t1","user_id":"u1"}'
# 기대: event:token 여러 개 → event:done
# event: token
# data: {"content": "안녕하세요"}
# (줄들이 실시간으로 도착)
# event: done
# data: {"thread_id": "t1", "status": "completed"}

# === Before Guardrail 차단 ===

# 3. 욕설 포함 입력 → blocked 이벤트 1개, token 없음
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"씨발 환불해줘","thread_id":"t2","user_id":"u1"}'
# 기대: event:blocked 1개
# event: blocked
# data: {"response": "부적절한 언어가 포함되어 있어 처리할 수 없습니다. 다시 문의해 주세요.", "thread_id": "t2"}

# === 환불 흐름 ===

# 4. 환불 요청 → confirmation_required 이벤트
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"ORD-123 주문 50000원 환불해줘. 제품 불량이야","thread_id":"t3","user_id":"u1"}'
# 기대: event:confirmation_required
# event: confirmation_required
# data: {"thread_id": "t3", "tool": "submit_refund_request", "args": {"order_id": "ORD-123", ...}}

# 5. 환불 확인(approve) — 기존 비스트리밍 엔드포인트
curl -X POST http://localhost:8000/chat/confirm \
  -H "Content-Type: application/json" \
  -d '{"thread_id":"t3","decision":"approve","user_id":"u1"}'
# 기대: {"data": {"status": "submitted", "response": "환불 신청이 접수되었습니다..."}}

# === RAG 답변 (문서 업로드 후) ===

# 6. 문서 관련 질문 → message 이벤트 1개 (할루시네이션 검사 통과본)
# 전제: /upload로 문서가 인덱싱되어 있어야 함
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"환불 정책 알려줘","thread_id":"t4","user_id":"u1"}'
# 기대: event:token 없음, event:message 1개 후 event:done
# event: message
# data: {"response": "환불 정책은...", "thread_id": "t4", "status": "completed"}
# event: done
# data: {"thread_id": "t4", "status": "completed"}

# === 프론트엔드 확인 ===

# 7. 프론트 실행
cd customer-support-agent/frontend
npm run dev
# http://localhost:3000 에서:
# - 일반 질문 → 글자가 실시간으로 흘러나옴
# - 욕설 → ⚠️ 차단 메시지
# - 환불 요청 → 확인 카드(노란 박스) → [확인(접수)] 누르면 신청 완료
# - 문서 질문 → 완성본이 한 번에 바로 표시 (token 없이 message 이벤트 1회)
```

---

## Phase 6 핵심 구조 요약

```
[백엔드: POST /chat/stream]

입력: {message, thread_id, user_id}
  ↓
agent.astream(stream_mode=["updates","messages"]) 루프
   updates 모드 → extract_block_reason → 욕설 차단 발견하면 break (event:blocked)
                  (Before Guardrail은 에이전트 내부 before_agent 미들웨어가 단락)
                  extract_interrupt_action → 발견하면 break
   messages 모드 → is_search_tool_result → used_search=True
                   is_final_answer_chunk →
                     used_search=False → event:token (즉시)
                     used_search=True  → answer_buffer에 누적
  ↓
③ 루프 종료 후 분기
   interrupt_action != None → event:confirmation_required → return
   used_search and buffer   → check_hallucination → event:message
   항상                     → event:done

[프론트: lib/chat.ts + app/page.tsx]

streamChat() 호출 (POST /chat/stream)
  ↓
fetch + ReadableStream + getReader()
  ↓
buffer에 청크 누적, \n\n으로 분리
  ↓
parseSseBlock() → ChatEvent 파싱
  ↓
handleEvent() 분기:
  token                → upsertAssistant(prev => prev + content)  // 누적
  message              → upsertAssistant(() => response)          // 교체
  blocked              → upsertAssistant(() => ⚠️ ...)
  confirmation_required → setPending({tool, args})                // 확인 카드
  done                 → (아무것도 안 함)
  error                → upsertAssistant(() => ❌ ...)

확인 카드에서 [확인]/[취소] → confirmChat() → POST /chat/confirm (비스트리밍)
```

---

## 범위 밖 (다음 단계)

Phase 6의 이번 세션은 채팅 스트리밍 흐름만 완성했습니다. 다음이 아직 남아 있습니다:

- `frontend/app/admin/page.tsx` — 문서 업로드 관리자 화면
- `frontend/app/approve/page.tsx` — 환불 신청 관리자 승인 화면 (폴링 기반)
- `app.state` + `Depends` 리팩터링 — `get_agent()` 싱글톤을 FastAPI 의존성 주입 방식으로 개선
- LangSmith — 환경변수만으로 자동 추적 (코드 변경 없음)

이 항목들은 다음 세션에서 다룹니다.

---

## 검증 체크리스트

### agent/streaming.py
- `is_final_answer_chunk` 조건 4개를 모두 이해
- `is_search_tool_result`가 RAG 흐름 감지에 쓰이는 이유 이해
- `extract_interrupt_action`이 `updates` 모드에서 작동하는 이유 이해

### routers/chat.py (`/chat/stream`)
- `stream_mode=["updates","messages"]`가 `(mode, payload)` 튜플을 yield하는 구조 이해
- `used_search` 플래그로 일반 vs RAG 답변을 분기하는 이유 이해
- interrupt 감지 후 `break`와 루프 종료 후 `if interrupt_action`의 관계 이해
- RAG 답변 버퍼링 → 할루시네이션 검사 → `event:message` 흐름 이해

### frontend/lib/chat.ts
- `fetch` + `ReadableStream`으로 SSE를 받는 이유(`EventSource`가 POST 불가)
- `buffer.split("\n\n")` + `blocks.pop()` 패턴의 목적 이해
- `parseSseBlock`이 `{type, ...data}` 형태로 파싱하는 과정 이해

### frontend/app/page.tsx
- `upsertAssistant(prev => prev + content)` (누적) vs `upsertAssistant(() => response)` (교체) 차이
- `pending` 상태가 확인 카드 표시를 제어하는 방식 이해
- `threadId = useRef(crypto.randomUUID())`로 세션 동안 thread_id를 유지하는 이유
