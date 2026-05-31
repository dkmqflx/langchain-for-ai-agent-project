# Phase 6 (1차) 채팅 스트리밍 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 고객 채팅에서 일반 답변은 토큰 단위로 실시간 스트리밍하고, RAG·환불·차단 흐름은 안전하게 처리하는 백엔드 `POST /chat/stream` SSE 엔드포인트와 Next.js 채팅 UI를 만든다.

**Architecture:** 단일 `/chat/stream` 엔드포인트가 `agent.astream(stream_mode=["updates","messages"])` 스트림을 관찰하며 내부 분기한다 — 검색 도구를 안 쓴 일반 답변은 토큰을 실시간 전송(`token`), 검색을 쓴 RAG 답변은 버퍼링 후 할루시네이션 검사본을 1회 전송(`message`), 환불 interrupt는 `confirmation_required`, 욕설은 `blocked`. 기존 비스트리밍 `/chat`·`/chat/confirm`은 변경하지 않는다(전체 안전장치 보존 경로). 프론트는 `fetch` + `ReadableStream`으로 SSE를 파싱한다.

**Tech Stack:** FastAPI, sse-starlette 3.4.4, LangChain 1.3.2 / LangGraph 1.2.2 (`create_agent`, `astream`), Next.js 15 (App Router) + Tailwind, TypeScript. Python 3.14, 백엔드는 `uv` 사용.

**검증된 LangGraph 스트리밍 사실 (langgraph 1.2.2, 설치본으로 probe 확인):**
- `agent.astream(input, config, context=..., stream_mode=["updates","messages"])` 는 `(mode_str, payload)` 튜플을 yield 한다.
- `mode=="messages"` → `payload == (message_chunk, metadata)`. LLM 토큰은 `AIMessageChunk`.
- 최종 답변 청크 판별: `AIMessageChunk` 이고 `metadata["langgraph_node"]=="model"` 이며 `tool_call_chunks` 가 비어있고 `content` 가 있음. (도구 호출 청크는 `content=""`, `tool_call_chunks` 비어있지 않음 → 제외.)
- `search_documents` 결과는 `messages` 모드에서 `ToolMessage(name="search_documents")` 로 나타난다(최종 답변 토큰보다 먼저 도착).
- 환불 interrupt 는 `mode=="updates"` 에서 `payload["__interrupt__"][0].value["action_requests"][0]` == `{"name","args","description"}` 로 나타난다.
- sse-starlette `EventSourceResponse(gen())` 의 generator는 `{"event": <str>, "data": <str>}` dict를 yield 한다. `data`는 문자열이어야 하므로 `json.dumps(...)` 사용.

---

## 파일 구조

| 파일 | 책임 | 변경 |
|------|------|------|
| `customer-support-agent/backend/pyproject.toml` | `pytest` dev 의존성 + `[tool.pytest.ini_options]` 추가 | 수정 |
| `customer-support-agent/backend/agent/streaming.py` | 스트림 청크 판별 **순수 함수** 3종 (I/O 없음, 단위테스트 대상) | 생성 |
| `customer-support-agent/backend/tests/test_streaming.py` | 위 순수 함수 `pytest` 테스트 (네트워크/DB 불필요) | 생성 |
| `customer-support-agent/backend/routers/chat.py` | `POST /chat/stream` 추가. 기존 핸들러 불변 | 수정 |
| `customer-support-agent/frontend/` | Next.js 15 (App Router + Tailwind + TS) 초기화 | 생성 |
| `customer-support-agent/frontend/lib/chat.ts` | SSE 호출·파싱 함수 + 타입 (UI와 분리) | 생성 |
| `customer-support-agent/frontend/app/page.tsx` | 채팅 UI (`lib/chat.ts` 사용) | 생성(덮어쓰기) |
| `customer-support-agent/study/06_phase6_learning_guide.md` | 한국어 초보자 가이드 (메모리 규약) | 생성 |

테스트 전략: 가장 미묘한 **청크 판별 로직**만 `pytest`로 검증(빠르고 네트워크 불필요). `pytest`는 `uv add --dev`로 설치한다(프로젝트 첫 테스트 프레임워크). 엔드포인트 오케스트레이션과 UI는 실행 스택 기동 후 **수동 검증**(curl/브라우저) — LLM/DB를 모킹하는 것은 이 학습 프로젝트의 수동 검증 관행에 맞지 않고 비용이 큼.

---

## Task 0: 환경 준비 (워크트리에서 백엔드/프론트 실행 가능하게)

**Files:** 없음 (환경 설정만)

`.env`는 gitignore 대상이라 워크트리에 복사되지 않았다. 백엔드 `main.py`는 `customer-support-agent/.env`를 로드한다. main 체크아웃의 `.env`를 워크트리로 symlink 한다.

- [ ] **Step 1: .env symlink 생성**

Run:
```bash
ln -sf /Users/dohyunkim/Documents/langchain-for-ai-agent-project/customer-support-agent/.env \
       /Users/dohyunkim/Documents/langchain-for-ai-agent-project/.claude/worktrees/phase6-chat-streaming/customer-support-agent/.env
ls -l /Users/dohyunkim/Documents/langchain-for-ai-agent-project/.claude/worktrees/phase6-chat-streaming/customer-support-agent/.env
```
Expected: symlink이 main 체크아웃 `.env`를 가리킴.

- [ ] **Step 2: 백엔드 의존성 동기화 확인**

Run:
```bash
cd customer-support-agent/backend && uv sync 2>&1 | tail -5
```
Expected: 에러 없이 완료(이미 동기화돼 있으면 거의 즉시). `sse-starlette`는 이미 `pyproject.toml`에 있음.

> 참고: 이 Task는 커밋 없음(환경 설정). symlink는 gitignore된 `.env`라 추적되지 않음.

---

## Task 1: 스트림 청크 판별 순수 함수 (TDD)

**Files:**
- Modify: `customer-support-agent/backend/pyproject.toml` (pytest dev 의존성 + pytest 설정)
- Create: `customer-support-agent/backend/agent/streaming.py`
- Test: `customer-support-agent/backend/tests/test_streaming.py`

- [ ] **Step 1: pytest 설치 (dev 의존성)**

Run (backend 디렉토리에서):
```bash
cd customer-support-agent/backend && uv add --dev pytest
```
Expected: `pyproject.toml`에 `[dependency-groups] dev = ["pytest>=..."]` 추가, `uv.lock` 갱신, pytest가 venv에 설치됨.

- [ ] **Step 2: pytest 설정 추가 (import 경로)**

`customer-support-agent/backend/pyproject.toml` 끝에 추가한다 (backend 디렉토리를 import 루트로 인식시켜 `import agent.streaming` 가능하게):
```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

Run (설정 인식 확인):
```bash
cd customer-support-agent/backend && uv run pytest --collect-only -q
```
Expected: 에러 없이 수집(아직 테스트 0개 또는 "no tests ran"). pytest가 실행됨을 확인.

- [ ] **Step 3: 실패하는 테스트 작성**

Create `customer-support-agent/backend/tests/test_streaming.py`:
```python
"""agent/streaming.py 순수 판별 함수 테스트 (네트워크/DB 불필요).

실행 (backend 디렉토리에서):
  uv run pytest tests/test_streaming.py -v
"""
from langchain_core.messages import AIMessageChunk, ToolMessage
from langgraph.types import Interrupt

from agent.streaming import (
    extract_interrupt_action,
    is_final_answer_chunk,
    is_search_tool_result,
)


# --- is_final_answer_chunk ---
def test_text_chunk_from_model_is_final():
    chunk = AIMessageChunk(content="환불은 ")
    assert is_final_answer_chunk(chunk, {"langgraph_node": "model"}) is True


def test_tool_call_chunk_is_not_final():
    chunk = AIMessageChunk(
        content="",
        tool_call_chunks=[{
            "name": "submit_refund_request", "args": "{}",
            "id": "call_1", "index": 0, "type": "tool_call_chunk",
        }],
    )
    assert is_final_answer_chunk(chunk, {"langgraph_node": "model"}) is False


def test_empty_content_is_not_final():
    chunk = AIMessageChunk(content="")
    assert is_final_answer_chunk(chunk, {"langgraph_node": "model"}) is False


def test_non_model_node_is_not_final():
    chunk = AIMessageChunk(content="hi")
    assert is_final_answer_chunk(chunk, {"langgraph_node": "tools"}) is False


def test_tool_message_is_not_final():
    tm = ToolMessage(content="문서", name="search_documents", tool_call_id="c1")
    assert is_final_answer_chunk(tm, {"langgraph_node": "tools"}) is False


# --- is_search_tool_result ---
def test_search_documents_toolmessage():
    tm = ToolMessage(content="문서내용", name="search_documents", tool_call_id="c1")
    assert is_search_tool_result(tm) is True


def test_other_tool_is_not_search():
    tm = ToolMessage(content="ok", name="submit_refund_request", tool_call_id="c2")
    assert is_search_tool_result(tm) is False


def test_ai_chunk_is_not_search():
    assert is_search_tool_result(AIMessageChunk(content="x")) is False


# --- extract_interrupt_action ---
def test_extracts_first_action():
    itr = Interrupt(value={
        "action_requests": [{
            "name": "submit_refund_request",
            "args": {"order_id": "ORD-1", "amount": 5000},
            "description": "d",
        }],
        "review_configs": [],
    })
    action = extract_interrupt_action({"__interrupt__": (itr,)})
    assert action["name"] == "submit_refund_request"
    assert action["args"]["order_id"] == "ORD-1"


def test_no_interrupt_returns_none():
    assert extract_interrupt_action({"model": {"messages": []}}) is None
```

- [ ] **Step 4: 테스트 실행 → 실패 확인**

Run:
```bash
cd customer-support-agent/backend && uv run pytest tests/test_streaming.py -v
```
Expected: collection error / FAIL — `ModuleNotFoundError: No module named 'agent.streaming'`

- [ ] **Step 5: streaming.py 구현**

Create `customer-support-agent/backend/agent/streaming.py`:
```python
"""스트리밍 분기를 위한 순수 판별 함수.

POST /chat/stream 이 agent.astream(stream_mode=["updates","messages"]) 스트림을
관찰하며 사용한다. I/O·네트워크 없음 → 단위 테스트 대상.

판별 근거 (langgraph 1.2.2 설치본 probe 확인):
  - messages 모드 payload = (message_chunk, metadata)
  - 최종 답변 토큰: AIMessageChunk, langgraph_node=="model", tool_call_chunks 비어있음, content 있음
  - 도구 호출 청크: content="", tool_call_chunks 비어있지 않음 → 최종 답변 아님
  - search_documents 결과: ToolMessage(name="search_documents")
  - 환불 interrupt: updates payload["__interrupt__"][0].value["action_requests"][0]
"""

from langchain_core.messages import AIMessageChunk, ToolMessage


def is_final_answer_chunk(chunk, metadata) -> bool:
    """이 청크가 사용자에게 보여줄 '최종 답변' 토큰인지 판별.

    도구 호출용 AIMessageChunk(content 비고 tool_call_chunks 있음)와
    중간 노드 출력은 제외한다.
    """
    return (
        isinstance(chunk, AIMessageChunk)
        and metadata.get("langgraph_node") == "model"
        and not chunk.tool_call_chunks
        and bool(chunk.content)
    )


def is_search_tool_result(chunk) -> bool:
    """search_documents 도구 결과(ToolMessage)인지 판별 (RAG 컨텍스트 수집용)."""
    return isinstance(chunk, ToolMessage) and chunk.name == "search_documents"


def extract_interrupt_action(update_payload):
    """updates 모드 payload에서 환불 interrupt action을 추출.

    Returns:
        {"name", "args", "description"} 딕셔너리, 또는 interrupt가 없으면 None.
    """
    interrupts = update_payload.get("__interrupt__")
    if not interrupts:
        return None
    return interrupts[0].value["action_requests"][0]
```

- [ ] **Step 6: 테스트 실행 → 통과 확인**

Run:
```bash
cd customer-support-agent/backend && uv run pytest tests/test_streaming.py -v
```
Expected: PASS (10 passed)

- [ ] **Step 7: import deprecation 검사 (CLAUDE.md 규칙)**

Run:
```bash
cd customer-support-agent/backend && .venv/bin/python -W error::DeprecationWarning -c "from agent.streaming import is_final_answer_chunk, is_search_tool_result, extract_interrupt_action; print('ok')"
```
Expected: `ok` (DeprecationWarning 없음)

- [ ] **Step 8: 커밋**

```bash
cd customer-support-agent/backend
git add pyproject.toml uv.lock agent/streaming.py tests/test_streaming.py
git commit -m "feat: streaming chunk discrimination helpers for /chat/stream

Pure predicates (no I/O) to branch the astream loop: final-answer
token vs tool-call chunk, search_documents result, refund interrupt.
Verified against langgraph 1.2.2 with pytest (added as dev dependency).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `POST /chat/stream` 엔드포인트 추가

**Files:**
- Modify: `customer-support-agent/backend/routers/chat.py` (imports 추가 + 파일 끝에 엔드포인트 추가; 기존 `/chat`, `/chat/confirm` 불변)

- [ ] **Step 1: import 추가**

`routers/chat.py` 상단 import 블록을 수정한다. 기존:
```python
from langchain_core.messages import ToolMessage
from langgraph.types import Command  # interrupt된 그래프를 재개할 때 사용
from fastapi import APIRouter, HTTPException

from agent.agent import get_agent
from agent.context import AgentContext
from agent.middleware import check_hallucination, is_blocked_input
from models.chat import ChatRequest, ConfirmRequest
```
다음으로 바꾼다 (json, EventSourceResponse, streaming 헬퍼 추가):
```python
import json

from langchain_core.messages import ToolMessage
from langgraph.types import Command  # interrupt된 그래프를 재개할 때 사용
from fastapi import APIRouter, HTTPException
from sse_starlette import EventSourceResponse

from agent.agent import get_agent
from agent.context import AgentContext
from agent.middleware import check_hallucination, is_blocked_input
from agent.streaming import (
    extract_interrupt_action,
    is_final_answer_chunk,
    is_search_tool_result,
)
from models.chat import ChatRequest, ConfirmRequest
```

- [ ] **Step 2: `/chat/stream` 엔드포인트를 파일 끝에 추가**

`routers/chat.py` 맨 끝(`confirm` 함수 다음)에 추가:
```python
@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """고객 메시지를 SSE로 스트리밍 처리한다.

    단일 엔드포인트가 agent.astream 을 관찰하며 내부 분기한다:
      - 욕설 차단      → event:blocked 후 종료 (에이전트 미실행)
      - 일반 답변      → event:token 으로 토큰 실시간 전송
      - RAG 답변(검색) → 토큰 버퍼링 → 할루시네이션 검사본을 event:message 1회 전송
      - 환불 interrupt → event:confirmation_required 후 종료 (재개는 기존 POST /chat/confirm)
    종료 시 event:done, 오류 시 event:error.

    학습용 한계(설계 문서 기재): 스트리밍된 token 은 PIIMiddleware 출력 마스킹과
    할루시네이션 검사 '이전' 단계다. 출력 PII 마스킹·할루시네이션 교정의 완전한 보장은
    비스트리밍 POST /chat 경로에서만 이뤄진다. 입력 마스킹(apply_to_input)에 의존한다.

    이벤트 프로토콜 (data는 모두 JSON 문자열):
      token                 {"content": "..."}
      message               {"response": "...", "thread_id": "...", "status": "completed"}
      blocked               {"response": "...", "thread_id": "..."}
      confirmation_required {"thread_id": "...", "tool": "...", "args": {...}}
      done                  {"thread_id": "...", "status": "completed"}
      error                 {"detail": "..."}
    """

    async def event_generator():
        try:
            # [1] Before Guardrail: 욕설/부적절 입력 차단 (에이전트 실행 전)
            blocked, reason = is_blocked_input(request.message)
            if blocked:
                yield {
                    "event": "blocked",
                    "data": json.dumps(
                        {"response": reason, "thread_id": request.thread_id},
                        ensure_ascii=False,
                    ),
                }
                return

            agent = get_agent()
            config = {"configurable": {"thread_id": request.thread_id}}

            used_search = False          # search_documents 사용 여부
            search_contexts: list[str] = []  # 할루시네이션 검사용 검색 컨텍스트
            answer_buffer: list[str] = []    # 검색 사용 시 최종 답변 토큰 버퍼
            interrupt_action = None          # 환불 interrupt action {name,args}

            # [2] astream 으로 실행하며 관찰
            # stream_mode=["updates","messages"]: 토큰(messages) + interrupt(updates) 동시 수신
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
                        break  # 환불 본인 확인 필요 → 스트림 중단
                elif mode == "messages":
                    chunk, metadata = payload
                    if is_search_tool_result(chunk):
                        used_search = True
                        search_contexts.append(chunk.content)
                    elif is_final_answer_chunk(chunk, metadata):
                        if used_search:
                            # RAG 답변: 흘리지 않고 버퍼링 (검사 후 한 번에 전송)
                            answer_buffer.append(chunk.content)
                        else:
                            # 일반 답변: 토큰 실시간 전송
                            yield {
                                "event": "token",
                                "data": json.dumps(
                                    {"content": chunk.content}, ensure_ascii=False
                                ),
                            }

            # [3] 스트림 종료 후 분기
            if interrupt_action is not None:
                yield {
                    "event": "confirmation_required",
                    "data": json.dumps(
                        {
                            "thread_id": request.thread_id,
                            "tool": interrupt_action["name"],
                            "args": interrupt_action["args"],
                        },
                        ensure_ascii=False,
                    ),
                }
                return

            if used_search:
                # RAG 답변: 검색 컨텍스트로 할루시네이션 검사 후 완성본 전송
                combined_context = "\n\n---\n\n".join(search_contexts)
                answer = "".join(answer_buffer)
                checked = check_hallucination(answer, combined_context)
                yield {
                    "event": "message",
                    "data": json.dumps(
                        {
                            "response": checked,
                            "thread_id": request.thread_id,
                            "status": "completed",
                        },
                        ensure_ascii=False,
                    ),
                }

            yield {
                "event": "done",
                "data": json.dumps(
                    {"thread_id": request.thread_id, "status": "completed"},
                    ensure_ascii=False,
                ),
            }

        except Exception as e:
            # 스트림 시작 후에는 상태코드 변경 불가 → error 이벤트로 전달
            yield {
                "event": "error",
                "data": json.dumps({"detail": str(e)}, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())
```

- [ ] **Step 3: import / deprecation 검사**

Run:
```bash
cd customer-support-agent/backend && .venv/bin/python -W error::DeprecationWarning -c "import routers.chat; print('import ok')"
```
Expected: `import ok` (DeprecationWarning로 인한 실패 없음)

- [ ] **Step 4: 백엔드 기동**

Run (백그라운드):
```bash
cd customer-support-agent/backend && .venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
Expected: `Application startup complete.` (BM25 빌드 로그 후). 에러 없이 기동.

- [ ] **Step 5: 수동 검증 — 일반 답변 토큰 스트리밍**

Run (새 터미널):
```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"안녕하세요","thread_id":"t-smoke-1","user_id":"u1"}'
```
Expected: `event: token` 줄들이 연속해서 도착(글자가 나눠서 옴), 마지막에 `event: done`. `event: message` 는 없음(검색 미사용).

- [ ] **Step 6: 수동 검증 — 욕설 차단**

Run (욕설 키워드는 `agent/middleware.py`의 `is_blocked_input` 차단 목록 참조):
```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"<차단 키워드 포함 메시지>","thread_id":"t-smoke-2","user_id":"u1"}'
```
Expected: `event: blocked` 1개 (token 없음).

- [ ] **Step 7: 수동 검증 — RAG 답변(문서 업로드 후) 및 환불 흐름**

전제: `/upload`로 문서가 인덱싱돼 있어야 RAG 경로 확인 가능.
```bash
# RAG: 문서 관련 질문 → event: message (완성본 1회), token 없음
curl -N -X POST http://localhost:8000/chat/stream -H "Content-Type: application/json" \
  -d '{"message":"환불 정책 알려줘","thread_id":"t-smoke-3","user_id":"u1"}'

# 환불: event: confirmation_required
curl -N -X POST http://localhost:8000/chat/stream -H "Content-Type: application/json" \
  -d '{"message":"ORD-123 주문 50000원 환불해줘. 불량이야","thread_id":"t-smoke-4","user_id":"u1"}'
```
Expected: 1번째는 `event: message`, 2번째는 `event: confirmation_required {tool:"submit_refund_request", args:{...}}`.
(환불 확인은 기존 `POST /chat/confirm`으로 재개 — 변경 없음.)

> 검증 후 uvicorn 종료.

- [ ] **Step 8: 커밋**

```bash
cd customer-support-agent/backend
git add routers/chat.py
git commit -m "feat: add POST /chat/stream SSE endpoint

Single endpoint observes agent.astream and branches internally:
stream tokens for tool-less general answers, buffer + hallucination-
check RAG answers, emit confirmation_required on refund interrupt,
blocked on guardrail. Existing /chat and /chat/confirm unchanged.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Next.js 15 프론트엔드 초기화

**Files:**
- Create: `customer-support-agent/frontend/` (create-next-app 산출물)

- [ ] **Step 1: create-next-app 실행**

Run (frontend 디렉토리가 없어야 함):
```bash
cd customer-support-agent && npx --yes create-next-app@latest frontend \
  --ts --tailwind --app --eslint --no-src-dir --import-alias "@/*" --use-npm --yes
```
Expected: `frontend/`에 Next.js 15 + App Router + Tailwind + TypeScript 프로젝트 생성. `frontend/app/page.tsx`, `frontend/tailwind.config.*` 또는 `frontend/app/globals.css` 존재.

- [ ] **Step 2: API URL 환경변수 파일 생성**

Create `customer-support-agent/frontend/.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

- [ ] **Step 3: dev 서버 부팅 확인**

Run (백그라운드):
```bash
cd customer-support-agent/frontend && npm run dev
```
Expected: `Ready` / `Local: http://localhost:3000`. 브라우저에서 기본 Next.js 페이지 로드 확인 후 종료.

- [ ] **Step 4: 커밋**

```bash
cd customer-support-agent
git add frontend
git commit -m "chore: scaffold Next.js 15 frontend (App Router, Tailwind, TS)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> 참고: `frontend/node_modules`, `frontend/.next`는 루트 `.gitignore`(`node_modules/`, `.next/`)로 이미 제외됨. `.env.local`도 `.env*.local`로 제외됨 → 커밋 안 됨(의도된 동작, 위 .env.local은 로컬 전용).

---

## Task 4: 채팅 UI + SSE 소비

**Files:**
- Create: `customer-support-agent/frontend/lib/chat.ts` (SSE 호출·파싱 + 타입)
- Create(덮어쓰기): `customer-support-agent/frontend/app/page.tsx`

- [ ] **Step 1: SSE 클라이언트 `lib/chat.ts` 작성**

Create `customer-support-agent/frontend/lib/chat.ts`:
```typescript
// 백엔드 /chat/stream SSE 호출 + 파싱. UI(page.tsx)와 분리.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// 백엔드 이벤트 프로토콜과 1:1 대응
export type ChatEvent =
  | { type: "token"; content: string }
  | { type: "message"; response: string; status: string }
  | { type: "blocked"; response: string }
  | { type: "confirmation_required"; tool: string; args: Record<string, unknown> }
  | { type: "done"; status: string }
  | { type: "error"; detail: string };

// 한 개의 SSE 블록("event: x\ndata: {...}")을 ChatEvent로 변환
function parseSseBlock(block: string): ChatEvent | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  const data = JSON.parse(dataLines.join("\n"));
  return { type: event, ...data } as ChatEvent;
}

// /chat/stream 을 호출하고 각 이벤트를 onEvent 콜백으로 전달
export async function streamChat(
  body: { message: string; thread_id: string; user_id: string },
  onEvent: (e: ChatEvent) => void,
): Promise<void> {
  const res = await fetch(`${API_URL}/chat/stream`, {
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
    // SSE 이벤트는 빈 줄(\n\n)로 구분
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? ""; // 마지막 미완성 블록은 보관
    for (const block of blocks) {
      if (!block.trim()) continue;
      const evt = parseSseBlock(block);
      if (evt) onEvent(evt);
    }
  }
}

// 환불 확인/취소 (기존 비스트리밍 엔드포인트)
export async function confirmChat(body: {
  thread_id: string;
  decision: "approve" | "reject";
  user_id: string;
}): Promise<{ response: string; status: string }> {
  const res = await fetch(`${API_URL}/chat/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const json = await res.json();
  return { response: json.data.response, status: json.data.status };
}
```

- [ ] **Step 2: 채팅 UI `app/page.tsx` 작성(덮어쓰기)**

Create `customer-support-agent/frontend/app/page.tsx`:
```tsx
"use client";

import { useRef, useState } from "react";
import {
  ChatEvent,
  confirmChat,
  streamChat,
} from "@/lib/chat";

type Role = "user" | "assistant";
interface Message {
  role: Role;
  content: string;
}
interface Pending {
  tool: string;
  args: Record<string, unknown>;
}

const USER_ID = "demo-user"; // 학습용 고정 사용자

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const threadId = useRef<string>(crypto.randomUUID());

  // 마지막 assistant 말풍선의 content에 텍스트를 누적/설정
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

  function handleEvent(e: ChatEvent) {
    switch (e.type) {
      case "token":
        upsertAssistant((prev) => prev + e.content);
        break;
      case "message":
        upsertAssistant(() => e.response);
        break;
      case "blocked":
        upsertAssistant(() => `⚠️ ${e.response}`);
        break;
      case "confirmation_required":
        setPending({ tool: e.tool, args: e.args });
        break;
      case "error":
        upsertAssistant(() => `❌ 오류: ${e.detail}`);
        break;
      case "done":
        break;
    }
  }

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setBusy(true);
    try {
      await streamChat(
        { message: text, thread_id: threadId.current, user_id: USER_ID },
        handleEvent,
      );
    } catch (err) {
      upsertAssistant(() => `❌ 연결 오류: ${String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  async function decide(decision: "approve" | "reject") {
    if (!pending) return;
    setBusy(true);
    try {
      const { response } = await confirmChat({
        thread_id: threadId.current,
        decision,
        user_id: USER_ID,
      });
      setMessages((prev) => [...prev, { role: "assistant", content: response }]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `❌ 오류: ${String(err)}` },
      ]);
    } finally {
      setPending(null);
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex h-screen max-w-2xl flex-col p-4">
      <h1 className="mb-4 text-xl font-bold">고객 지원 챗봇</h1>

      <div className="flex-1 space-y-3 overflow-y-auto rounded-lg border border-gray-200 p-4">
        {messages.length === 0 && (
          <p className="text-sm text-gray-400">메시지를 입력해 대화를 시작하세요.</p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={m.role === "user" ? "flex justify-end" : "flex justify-start"}
          >
            <div
              className={
                "max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm " +
                (m.role === "user"
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-900")
              }
            >
              {m.content || "…"}
            </div>
          </div>
        ))}
      </div>

      {pending && (
        <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-4">
          <p className="mb-2 text-sm font-medium">
            환불 신청을 접수할까요? ({JSON.stringify(pending.args)})
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => decide("approve")}
              disabled={busy}
              className="rounded-md bg-amber-600 px-3 py-1 text-sm text-white disabled:opacity-50"
            >
              확인(접수)
            </button>
            <button
              onClick={() => decide("reject")}
              disabled={busy}
              className="rounded-md bg-gray-300 px-3 py-1 text-sm disabled:opacity-50"
            >
              취소
            </button>
          </div>
        </div>
      )}

      <div className="mt-3 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          disabled={busy}
          placeholder="메시지를 입력하세요"
          className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
        />
        <button
          onClick={send}
          disabled={busy}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50"
        >
          전송
        </button>
      </div>
    </main>
  );
}
```

- [ ] **Step 3: 타입체크 / 빌드 검증**

Run:
```bash
cd customer-support-agent/frontend && npx tsc --noEmit
```
Expected: 타입 에러 없음.

- [ ] **Step 4: 수동 검증 — 브라우저 E2E**

전제: 백엔드(8000)와 프론트(3000) 모두 기동, `.env` symlink 완료(Task 0), 문서 1개 업로드.
Run:
```bash
# 터미널 A
cd customer-support-agent/backend && .venv/bin/uvicorn main:app --reload --port 8000
# 터미널 B
cd customer-support-agent/frontend && npm run dev
```
브라우저 `http://localhost:3000`에서 확인:
1. "안녕하세요" → 답변 글자가 **실시간으로 흘러나옴**(token 스트리밍).
2. "환불 정책 알려줘"(문서 업로드 시) → 답변이 **한 번에** 표시(message, 검사 거침).
3. "ORD-123 50000원 환불해줘" → **환불 확인 카드** 표시 → [확인] → 접수 응답.
4. 욕설 입력 → ⚠️ 차단 메시지.

Expected: 4가지 흐름 모두 화면에 올바르게 반영.

- [ ] **Step 5: 커밋**

```bash
cd customer-support-agent
git add frontend/lib/chat.ts frontend/app/page.tsx
git commit -m "feat: streaming chat UI consuming /chat/stream SSE

lib/chat.ts handles fetch + SSE parsing (token/message/blocked/
confirmation_required/done/error); page.tsx renders streaming
tokens, refund confirmation card (POST /chat/confirm), and blocked
notices. Plain Tailwind.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Phase 6 학습 가이드 (메모리 규약)

**Files:**
- Create: `customer-support-agent/study/06_phase6_learning_guide.md`

- [ ] **Step 1: 한국어 초보자 가이드 작성**

`study/`의 기존 가이드(예: `05_phase5_learning_guide.md`) 형식·톤을 먼저 읽고 맞춘다. `06_phase6_learning_guide.md`에 다음을 포함:
- SSE/스트리밍이 무엇인지 (비유: 음식이 다 되기 전에 나오는 대로 내어주기)
- 왜 일반 답변만 스트리밍하고 RAG/환불/차단은 다르게 처리하는지 (할루시네이션 검사·interrupt와의 충돌)
- `astream(stream_mode=["updates","messages"])` 의 `(mode, payload)` 구조와 분기 로직
- 프론트의 `fetch` + `ReadableStream` SSE 파싱 흐름
- PII 출력 마스킹 빈틈을 학습용 한계로 둔 이유
- 검증 방법(curl, 브라우저)

설계 문서 `docs/superpowers/specs/2026-05-31-phase6-chat-streaming-design.md`의 결정 표를 근거로 작성.

- [ ] **Step 2: 커밋**

```bash
cd customer-support-agent
git add study/06_phase6_learning_guide.md
git commit -m "docs: phase 6 chat-streaming learning guide (Korean)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review (작성자 체크 결과)

**Spec coverage:** 설계 문서 섹션별 매핑 —
- §3 백엔드 `/chat/stream` 분기 → Task 1(판별 함수) + Task 2(엔드포인트) ✅
- §3 SSE 이벤트 프로토콜 6종(token/message/blocked/confirmation_required/done/error) → Task 2 코드에 모두 구현 ✅
- §4 프론트 `page.tsx` + SSE 소비 + thread_id UUID + 환불 카드 → Task 4 ✅
- §2 결정: 일반만 스트리밍 / 단일 엔드포인트 / 순수 Tailwind / PII 한계 / app.state 리팩터링 제외 → 반영(Task 2·3·4, app.state 미포함) ✅
- §6 검증(일반/RAG/차단/환불) → Task 2 Step5-7, Task 4 Step4 ✅
- §8 학습 가이드 → Task 5 ✅
- 범위 밖(admin/approve/app.state/LangSmith) → 포함 안 함 ✅

**Placeholder scan:** 코드 스텝은 모두 실제 코드 포함. "차단 키워드 포함 메시지"는 `is_blocked_input` 구현 의존 값이라 실행자가 해당 파일을 참조하도록 명시(코드 placeholder 아님). 학습 가이드(Task 5)는 산문 문서라 내용 항목을 구체 지시.

**Type consistency:** 백엔드 헬퍼명(`is_final_answer_chunk`, `is_search_tool_result`, `extract_interrupt_action`)이 Task 1 정의 ↔ Task 2 import ↔ 테스트에서 일치. 프론트 `ChatEvent` 타입과 `streamChat`/`confirmChat` 시그니처가 Task 4 내부에서 일치. 이벤트명이 백엔드(Task 2)와 프론트(Task 4) 간 일치(token/message/blocked/confirmation_required/done/error).
