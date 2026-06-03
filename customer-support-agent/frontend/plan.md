# Phase 6.5 — AI SDK UI + AI Elements 전환 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 수제 SSE 프로토콜/파서를 AI SDK v6 "UI Message Stream"으로 교체한다 — FastAPI가 프로토콜을 직접 emit하고 `useChat` + AI Elements가 소비한다. 백엔드 에이전트/미들웨어는 변경하지 않는다.

**Architecture:** `backend/agent/ui_stream.py`가 `agent.astream(stream_mode=["updates","messages"])` 이벤트를 UI Message Stream 파트로 번역하고, `routers/chat.py`의 `/chat/stream`·`/chat/confirm`이 이를 `StreamingResponse`(`text/event-stream`, 헤더 `x-vercel-ai-ui-message-stream: v1`)로 반환한다. 프론트는 `lib/chat.ts`의 `DefaultChatTransport`(엔드포인트 라우팅·바디 reshape) + `app/page.tsx`의 `useChat` + AI Elements 컴포넌트로 재작성한다.

**Tech Stack:** FastAPI / LangGraph (백엔드, 변경 없음) · `ai@6.0.195` · `@ai-sdk/react@3.0.197` · `react@19.2.7` · AI Elements(shadcn 레지스트리) · Tailwind v4 · TypeScript.

**Spec:** `docs/superpowers/specs/2026-06-04-phase6.5-ai-sdk-ui-migration-design.md`

**검증된 사실(번들 문서 `node_modules/ai/docs/`):**
- UI Message Stream wire 파트(SSE `data: <json>\n\n`): `{"type":"start","messageId":..}`, `{"type":"text-start","id":..}`, `{"type":"text-delta","id":..,"delta":..}`, `{"type":"text-end","id":..}`, `{"type":"data-<name>","data":{..}}`, `{"type":"error","errorText":..}`, `{"type":"finish"}`, 그리고 종료 `data: [DONE]\n\n`. 필수 헤더 `x-vercel-ai-ui-message-stream: v1`. (v6 = 템플릿 v5와 동일.)
- `useChat`: `import { useChat } from '@ai-sdk/react'`; `import { DefaultChatTransport } from 'ai'`. 반환 `{ messages: UIMessage[], sendMessage, status, stop, error, regenerate, setMessages }`. `UIMessage = { id, role, parts, metadata? }`, 텍스트 파트 `{ type:'text', text }`.
- `DefaultChatTransport({ api, headers?, credentials?, prepareSendMessagesRequest? })`. `prepareSendMessagesRequest: ({ id, messages, requestMetadata, body, api, trigger, messageId }) => ({ api?, headers?, body?, credentials? })` — **반환 객체의 `api`로 엔드포인트 오버라이드 가능**.
- 커스텀 data 파트: 서버가 `{"type":"data-blocked","data":{..}}` emit → 클라이언트 `message.parts`에 `{ type:'data-blocked', data }`로 등장(persistent). `useChat({ onData })`는 transient 파트용.
- `sendMessage(message?, options?)`: `message` 생략 시 "현재 메시지 재제출"(새 user 메시지 없이 API 호출). `options.metadata` → `requestMetadata`로 전달, `options.body` → 요청 바디 병합.

---

## 파일 구조

**백엔드 (생성/수정):**
- Create: `customer-support-agent/backend/agent/ui_stream.py` — astream 이벤트 → UI Message Stream 파트 번역기(순수, 테스트 대상) + SSE 포매터.
- Create: `customer-support-agent/backend/tests/test_ui_stream.py` — 번역기 단위 테스트(네트워크 없음).
- Modify: `customer-support-agent/backend/routers/chat.py` — `/chat/stream`·`/chat/confirm`을 UI Message Stream으로 재작성. 기존 커스텀 `event_generator` 제거. `/chat`(비스트리밍)은 유지.
- 재사용(수정 없음): `agent/streaming.py`(판별 헬퍼), `agent/middleware.py`(`is_blocked_input`, `check_hallucination`), `agent/agent.py`, `agent/context.py`, `models/chat.py`.

**프론트엔드 (생성/수정/삭제):**
- Modify: `customer-support-agent/frontend/package.json` — 의존성(Task 0에서 커밋).
- Rewrite: `customer-support-agent/frontend/lib/chat.ts` — 수제 SSE 파서 삭제, transport 설정 + 타입만.
- Create: `customer-support-agent/frontend/components/ai-elements/*` — `npx ai-elements add`로 생성.
- Create: `customer-support-agent/frontend/components/blocked-notice.tsx`, `components/refund-confirm-card.tsx` — 커스텀 data 파트 렌더러.
- Rewrite: `customer-support-agent/frontend/app/page.tsx` — `useChat` + AI Elements.

---

## Task 0: 의존성 핀 + 커밋

**Files:**
- Modify: `customer-support-agent/frontend/package.json`, `package-lock.json`

> 참고: 계획 작성 중 이미 설치됨(`react@19.2.7`, `react-dom@19.2.7`, `ai@6.0.195`, `@ai-sdk/react@3.0.197`). `@ai-sdk/react@3`의 peer 범위 `^18 || ~19.0.1 || ~19.1.2 || ^19.2.1` 때문에 react를 19.1.0 → 19.2.x로 올려야 했다. 이 단계는 그 상태를 검증·커밋한다.

- [ ] **Step 1: 설치 버전 검증**

Run:
```bash
cd customer-support-agent/frontend
node -e "for (const p of ['ai','@ai-sdk/react','react','react-dom']) console.log(p, require(p+'/package.json').version)"
```
Expected: `ai 6.0.195`, `@ai-sdk/react 3.0.197`, `react 19.2.7`, `react-dom 19.2.7`.

- [ ] **Step 2: 타입체크 통과 확인 (기존 코드 기준)**

Run: `cd customer-support-agent/frontend && npx tsc --noEmit`
Expected: 출력 없음(통과). 출력이 있으면 react 19.2 타입 변화에 따른 것 — 멈추고 보고.

- [ ] **Step 3: 커밋**

```bash
cd /Users/dohyunkim/Documents/langchain-for-ai-agent-project
git add customer-support-agent/frontend/package.json customer-support-agent/frontend/package-lock.json
git commit -m "chore(frontend): add ai@6 + @ai-sdk/react@3, bump react to 19.2"
```

---

## Task 1: 백엔드 번역기 — 일반 답변 스트리밍 (start/text/finish)

가장 단순하고 입증 가능한 경로부터. 검색·차단·환불은 이후 태스크에서 추가한다.

**Files:**
- Create: `customer-support-agent/backend/agent/ui_stream.py`
- Test: `customer-support-agent/backend/tests/test_ui_stream.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_ui_stream.py`:
```python
"""ui_stream 번역기 단위 테스트 — 네트워크/agent 없음.

translate_stream 은 (mode, payload) 비동기 이터러블을 받아 UI Message Stream
파트 딕셔너리를 yield 한다. 가짜 이벤트를 주입해 파트 시퀀스를 검증한다.
(streaming.py 판별 헬퍼는 실제 메시지 객체로 동작하므로 langchain_core 메시지를 사용.)
"""
import asyncio

import pytest
from langchain_core.messages import AIMessageChunk

from agent.ui_stream import translate_stream, format_sse


async def _collect(events, **kwargs):
    return [part async for part in translate_stream(_aiter(events), **kwargs)]


async def _aiter(items):
    for it in items:
        yield it


def _text_chunk(text):
    # 최종 답변 토큰: model 노드, tool_call_chunks 없음, content 있음
    return ("messages", (AIMessageChunk(content=text), {"langgraph_node": "model"}))


def test_general_answer_emits_start_text_finish():
    events = [_text_chunk("안"), _text_chunk("녕")]
    parts = asyncio.run(_collect(events, message_id="msg-1", check_hallucination=lambda a, c: a))
    assert parts[0] == {"type": "start", "messageId": "msg-1"}
    # text-start 1회, text-delta 2회(델타 "안","녕"), text-end 1회
    types = [p["type"] for p in parts]
    assert types == ["start", "text-start", "text-delta", "text-delta", "text-end", "finish"]
    deltas = [p["delta"] for p in parts if p["type"] == "text-delta"]
    assert deltas == ["안", "녕"]
    # 같은 text 블록 id 공유
    ids = {p["id"] for p in parts if p["type"] in ("text-start", "text-delta", "text-end")}
    assert len(ids) == 1


def test_format_sse_is_single_data_line():
    line = format_sse({"type": "text-delta", "id": "t", "delta": "안녕"})
    assert line == 'data: {"type":"text-delta","id":"t","delta":"안녕"}\n\n'
    assert "\r" not in line  # LF only
```

- [ ] **Step 2: 실패 확인**

Run: `cd customer-support-agent/backend && uv run pytest tests/test_ui_stream.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.ui_stream'`

- [ ] **Step 3: 최소 구현**

`agent/ui_stream.py`:
```python
"""agent.astream 이벤트 → AI SDK v6 UI Message Stream 파트 번역기.

순수 변환: translate_stream 은 (mode, payload) 비동기 이터러블을 받아 파트 딕셔너리를
yield 한다. I/O·네트워크는 호출부(routers/chat.py)가 담당한다 → 단위 테스트 가능.

wire 포맷(번들 문서 검증): start / text-start / text-delta / text-end /
data-<name> / error / finish, 그리고 종료 [DONE]. SSE: 'data: <json>\\n\\n'.
"""
import json
import uuid
from typing import AsyncIterator, Callable

from agent.middleware import check_hallucination as _default_check_hallucination
from agent.streaming import (
    extract_interrupt_action,
    is_final_answer_chunk,
    is_search_tool_result,
)


def format_sse(part: dict) -> str:
    """파트 딕셔너리를 SSE 한 줄로 직렬화 (LF 종결, 한글 보존)."""
    return f"data: {json.dumps(part, ensure_ascii=False, separators=(',', ':'))}\n\n"


DONE = "data: [DONE]\n\n"


def new_text_id() -> str:
    return f"text-{uuid.uuid4().hex}"


async def translate_stream(
    events: AsyncIterator,
    *,
    message_id: str,
    check_hallucination: Callable[[str, str], str] = _default_check_hallucination,
) -> AsyncIterator[dict]:
    """astream (mode,payload) 이벤트 → UI Message Stream 파트 딕셔너리."""
    yield {"type": "start", "messageId": message_id}

    text_id = new_text_id()
    text_started = False

    async for mode, payload in events:
        if mode != "messages":
            continue
        chunk, metadata = payload
        if is_final_answer_chunk(chunk, metadata):
            if not text_started:
                yield {"type": "text-start", "id": text_id}
                text_started = True
            yield {"type": "text-delta", "id": text_id, "delta": chunk.content}

    if text_started:
        yield {"type": "text-end", "id": text_id}

    yield {"type": "finish"}
```

- [ ] **Step 4: 통과 확인**

Run: `cd customer-support-agent/backend && uv run pytest tests/test_ui_stream.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: import 비퇴화 검증 (CLAUDE.md)**

Run: `cd customer-support-agent/backend && uv run python -W error::DeprecationWarning -c "from agent.ui_stream import translate_stream, format_sse; print('ok')"`
Expected: `ok` (DeprecationWarning 없음; SHA-1 UserWarning은 무관)

- [ ] **Step 6: 커밋**

```bash
cd /Users/dohyunkim/Documents/langchain-for-ai-agent-project
git add customer-support-agent/backend/agent/ui_stream.py customer-support-agent/backend/tests/test_ui_stream.py
git commit -m "feat(backend): UI Message Stream translator (general answer path)"
```

---

## Task 2: 백엔드 — `/chat/stream`을 UI Message Stream으로 재작성

**Files:**
- Modify: `customer-support-agent/backend/routers/chat.py` (`chat_stream` 함수 + import)

- [ ] **Step 1: import 정리 + `/chat/stream` 재작성**

`routers/chat.py` 상단 import에서 sse_starlette·기존 streaming 헬퍼 import를 다음으로 교체:
```python
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from agent.agent import get_agent
from agent.context import AgentContext
from agent.middleware import check_hallucination, is_blocked_input
from agent.ui_stream import DONE, format_sse, new_text_id, translate_stream
from models.chat import ChatRequest, ConfirmRequest
```
> `json`·`sse_starlette`·`agent.streaming` import 제거(이 라우터에서 더 이상 직접 사용 안 함). `ToolMessage`는 기존 `/chat`이 사용하므로 유지.

`chat_stream` 함수 전체를 교체:
```python
UI_STREAM_HEADERS = {
    "x-vercel-ai-ui-message-stream": "v1",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """고객 메시지를 AI SDK UI Message Stream(SSE)으로 스트리밍 처리한다.

    - 욕설 차단 → data-blocked 파트 후 종료(에이전트 미실행)
    - 일반/RAG 답변 → text 파트, 환불 interrupt → data-confirmation 파트
    재개는 POST /chat/confirm (useChat transport가 라우팅).
    """

    async def event_generator():
        message_id = f"msg-{uuid.uuid4().hex}"
        try:
            blocked, reason = is_blocked_input(request.message)
            if blocked:
                yield format_sse({"type": "start", "messageId": message_id})
                yield format_sse({"type": "data-blocked", "data": {"reason": reason}})
                yield format_sse({"type": "finish"})
                yield DONE
                return

            agent = get_agent()
            events = agent.astream(
                {"messages": [("human", request.message)]},
                config={"configurable": {"thread_id": request.thread_id}},
                context=AgentContext(user_id=request.user_id),
                stream_mode=["updates", "messages"],
            )
            async for part in translate_stream(
                events,
                message_id=message_id,
                thread_id=request.thread_id,
            ):
                yield format_sse(part)
            yield DONE
        except Exception as e:  # 스트림 시작 후 상태코드 변경 불가 → error 파트
            yield format_sse({"type": "error", "errorText": str(e)})
            yield DONE

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=UI_STREAM_HEADERS,
    )
```

> 주의: `translate_stream`은 Task 1에서 `message_id`, `check_hallucination`만 받았다. Task 4에서 `thread_id` 파라미터(환불/차단 분기용)를 추가하므로, **이 단계에서는 위 호출의 `thread_id=...` 인자를 추가하기 전에 Task 4를 먼저 적용하거나**, 임시로 `thread_id` 인자를 빼고 호출한다. → 실행 순서상 충돌을 피하려 Step 2에서 명시한다.

- [ ] **Step 2: 이 태스크 범위 조정 — 일반 답변만 우선**

Task 1의 `translate_stream`은 아직 `thread_id`/interrupt/검색을 모른다. 이 태스크에서는 **일반 답변 end-to-end 입증**이 목표이므로, 위 호출에서 `thread_id=request.thread_id` 인자를 **빼고** 호출한다:
```python
            async for part in translate_stream(events, message_id=message_id):
                yield format_sse(part)
```
(차단 분기는 위 코드대로 유지 — `is_blocked_input`은 동기 함수라 그대로 동작.) 환불/RAG는 Task 4에서 `translate_stream` 확장 후 인자를 추가한다.

- [ ] **Step 3: 백엔드 기동 + 일반 답변 curl 검증**

Run (백엔드가 안 떠 있으면):
```bash
cd customer-support-agent/backend && uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
sleep 4
curl -sN -X POST http://localhost:8000/chat/stream -H "Content-Type: application/json" \
  -d '{"message":"안녕하세요","thread_id":"t-ui-1","user_id":"demo"}' --max-time 25 | head -20
```
Expected: `data: {"type":"start",...}` → `data: {"type":"text-start",...}` → 여러 `text-delta` → `text-end` → `finish` → `data: [DONE]`. 응답 헤더에 `x-vercel-ai-ui-message-stream: v1`(필요시 `curl -i`로 확인).

- [ ] **Step 4: 차단 경로 curl 검증**

Run:
```bash
curl -sN -X POST http://localhost:8000/chat/stream -H "Content-Type: application/json" \
  -d '{"message":"씨발","thread_id":"t-ui-2","user_id":"demo"}' --max-time 15 | head
```
Expected: `start` → `data-blocked {"reason":...}` → `finish` → `[DONE]`. (욕설 트리거는 `is_blocked_input` 실제 규칙에 맞춰 조정 — 차단 사유 문자열이 나오면 성공.)

- [ ] **Step 5: 커밋**

```bash
cd /Users/dohyunkim/Documents/langchain-for-ai-agent-project
git add customer-support-agent/backend/routers/chat.py
git commit -m "feat(backend): rewrite /chat/stream to emit UI Message Stream + data-blocked"
```

---

## Task 3: 프론트엔드 — transport + AI Elements + useChat (일반 답변 입증)

여기까지 오면 브라우저에서 일반 답변 스트리밍이 동작해야 한다(주요 마일스톤).

**Files:**
- Rewrite: `customer-support-agent/frontend/lib/chat.ts`
- Create: `customer-support-agent/frontend/components/ai-elements/*` (CLI 생성)
- Rewrite: `customer-support-agent/frontend/app/page.tsx`

- [ ] **Step 1: AI Elements 컴포넌트 추가**

Run:
```bash
cd customer-support-agent/frontend
npx ai-elements@latest add conversation message response prompt-input
```
shadcn 초기화 프롬프트가 뜨면 기본값 수락(`components.json` 생성, Tailwind v4 감지). 생성 위치: `components/ai-elements/`.
Expected: `components/ai-elements/conversation.tsx`, `message.tsx`, `response.tsx`, `prompt-input.tsx` 생성.

- [ ] **Step 2: 생성된 컴포넌트의 export·props 확인 (정확성 검증)**

Run:
```bash
cd customer-support-agent/frontend
grep -nE "export (function|const) (Conversation|ConversationContent|ConversationScrollButton|Message|MessageContent|Response|PromptInput|PromptInputTextarea|PromptInputSubmit|PromptInputBody)" components/ai-elements/*.tsx
```
이 단계에서 확인한 **실제 export 이름/props**로 Step 4의 page.tsx를 맞춘다(아래 코드는 AI Elements 표준 구성 기준 — export 이름이 다르면 그에 맞게 수정).

- [ ] **Step 3: `lib/chat.ts` 재작성 (수제 파서 삭제)**

`lib/chat.ts` 전체 교체:
```ts
// AI SDK UI Message Stream transport 설정. 수제 SSE 파서는 더 이상 없음(useChat가 소유).
import { DefaultChatTransport, type UIMessage } from "ai";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// 커스텀 data 파트 타입 (백엔드 data-blocked / data-confirmation 와 1:1)
export type ChatDataParts = {
  blocked: { reason: string };
  confirmation: { tool: string; args: Record<string, unknown>; thread_id: string };
};
export type AppUIMessage = UIMessage<unknown, ChatDataParts>;

export type Decision = "approve" | "reject";

// 마지막 user 메시지의 텍스트를 합쳐 반환
function lastUserText(messages: AppUIMessage[]): string {
  const last = messages[messages.length - 1];
  if (!last) return "";
  return last.parts
    .filter((p): p is { type: "text"; text: string } => p.type === "text")
    .map((p) => p.text)
    .join("");
}

// 일반 전송은 /chat/stream, 환불 재개(metadata.decision)는 /chat/confirm 으로 라우팅.
// thread_id/user_id 는 서버 체크포인터 모델 유지를 위해 마지막 메시지만 전송.
export function makeChatTransport(getThreadId: () => string, userId: string) {
  return new DefaultChatTransport<AppUIMessage>({
    api: `${API}/chat/stream`,
    prepareSendMessagesRequest: ({ messages, requestMetadata }) => {
      const meta = requestMetadata as { decision?: Decision } | undefined;
      if (meta?.decision) {
        return {
          api: `${API}/chat/confirm`,
          body: { thread_id: getThreadId(), decision: meta.decision, user_id: userId },
        };
      }
      return {
        body: { message: lastUserText(messages), thread_id: getThreadId(), user_id: userId },
      };
    },
  });
}
```
> 검증: `DefaultChatTransport`의 제네릭/`prepareSendMessagesRequest` 반환 `api` 오버라이드는 번들 문서로 확인됨. 제네릭 표기가 tsc에서 거부되면 `node_modules/ai`의 `DefaultChatTransport` 타입 시그니처를 확인해 맞춘다.

- [ ] **Step 4: `app/page.tsx` 재작성 (useChat + AI Elements, 일반 답변만)**

`app/page.tsx` 전체 교체:
```tsx
"use client";

import { useRef, useState } from "react";
import { useChat } from "@ai-sdk/react";
import {
  Conversation,
  ConversationContent,
} from "@/components/ai-elements/conversation";
import { Message, MessageContent } from "@/components/ai-elements/message";
import { Response } from "@/components/ai-elements/response";
import {
  PromptInput,
  PromptInputTextarea,
  PromptInputSubmit,
} from "@/components/ai-elements/prompt-input";
import { makeChatTransport, type AppUIMessage } from "@/lib/chat";

const USER_ID = "demo-user";

export default function ChatPage() {
  const threadId = useRef<string>(crypto.randomUUID());
  const [input, setInput] = useState("");
  const { messages, sendMessage, status } = useChat<AppUIMessage>({
    transport: makeChatTransport(() => threadId.current, USER_ID),
  });

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;
    sendMessage({ text });
    setInput("");
  }

  return (
    <main className="mx-auto flex h-screen max-w-2xl flex-col p-4">
      <h1 className="mb-4 text-xl font-bold">고객 지원 챗봇</h1>
      <Conversation className="flex-1 rounded-lg border border-gray-200">
        <ConversationContent>
          {messages.map((m) => (
            <Message from={m.role} key={m.id}>
              <MessageContent>
                {m.parts.map((part, i) =>
                  part.type === "text" ? (
                    <Response key={`${m.id}-${i}`}>{part.text}</Response>
                  ) : null,
                )}
              </MessageContent>
            </Message>
          ))}
        </ConversationContent>
      </Conversation>
      <PromptInput onSubmit={onSubmit} className="mt-3">
        <PromptInputTextarea
          value={input}
          onChange={(e) => setInput(e.currentTarget.value)}
          placeholder="메시지를 입력하세요"
        />
        <PromptInputSubmit status={status} disabled={!input.trim()} />
      </PromptInput>
    </main>
  );
}
```
> `Message`의 `from` prop, `PromptInputSubmit`의 `status` prop 등 정확한 이름은 Step 2에서 확인한 생성 소스에 맞춘다.

- [ ] **Step 5: 타입체크**

Run: `cd customer-support-agent/frontend && npx tsc --noEmit`
Expected: 통과. 실패 시 Step 2에서 확인한 실제 props/제네릭으로 수정.

- [ ] **Step 6: 브라우저 E2E (일반 답변 스트리밍)**

`NEXT_PUBLIC_API_URL=http://localhost:8000` 확인(`.env.local`). 프론트(`npm run dev -- --port 3001`)·백엔드(:8000) 기동 후 http://localhost:3001 에서 "안녕하세요" 전송.
Expected: assistant 말풍선에 토큰이 실시간으로 누적되어 렌더. (CORS는 3001 허용 상태.)

- [ ] **Step 7: 커밋**

```bash
cd /Users/dohyunkim/Documents/langchain-for-ai-agent-project
git add customer-support-agent/frontend/lib/chat.ts customer-support-agent/frontend/app/page.tsx \
  customer-support-agent/frontend/components customer-support-agent/frontend/components.json \
  customer-support-agent/frontend/package.json customer-support-agent/frontend/package-lock.json \
  customer-support-agent/frontend/app/globals.css
git commit -m "feat(frontend): useChat + AI Elements chat UI (general answers stream)"
```

---

## Task 4: 백엔드 번역기 — RAG(버퍼링·할루시네이션) + 환불 interrupt(data-confirmation)

**Files:**
- Modify: `customer-support-agent/backend/agent/ui_stream.py` (`translate_stream` 확장)
- Modify: `customer-support-agent/backend/tests/test_ui_stream.py` (케이스 추가)
- Modify: `customer-support-agent/backend/routers/chat.py` (`translate_stream(..., thread_id=...)` 인자 복원)

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_ui_stream.py`에 추가:
```python
from langchain_core.messages import ToolMessage


def _search_result(text):
    return ("messages", (ToolMessage(content=text, name="search_documents", tool_call_id="c1"), {}))


def _interrupt(action):
    return ("updates", {"__interrupt__": [type("I", (), {"value": {"action_requests": [action]}})()]})


def test_rag_answer_buffers_then_emits_checked_text():
    # 검색 결과 + 최종 답변 토큰 → 할루시네이션 검사본을 text 한 블록으로
    events = [_search_result("환불은 30일 이내"), _text_chunk("환불"), _text_chunk("은 30일")]
    parts = asyncio.run(_collect(
        events, message_id="m", thread_id="t",
        check_hallucination=lambda answer, ctx: f"[검증]{answer}",
    ))
    types = [p["type"] for p in parts]
    assert types == ["start", "text-start", "text-delta", "text-end", "finish"]
    full = "".join(p["delta"] for p in parts if p["type"] == "text-delta")
    assert full == "[검증]환불은 30일"  # 토큰은 버퍼→1회 전송, 검사 적용


def test_refund_interrupt_emits_data_confirmation():
    action = {"name": "submit_refund_request", "args": {"order_id": "O-1", "amount": 5000}}
    events = [_interrupt(action)]
    parts = asyncio.run(_collect(events, message_id="m", thread_id="t-99",
                                 check_hallucination=lambda a, c: a))
    conf = [p for p in parts if p["type"] == "data-confirmation"]
    assert len(conf) == 1
    assert conf[0]["data"] == {
        "tool": "submit_refund_request",
        "args": {"order_id": "O-1", "amount": 5000},
        "thread_id": "t-99",
    }
    assert parts[-1]["type"] == "finish"
```

- [ ] **Step 2: 실패 확인**

Run: `cd customer-support-agent/backend && uv run pytest tests/test_ui_stream.py -q`
Expected: FAIL — 새 케이스에서 `translate_stream`이 `thread_id` 인자를 모름 / data-confirmation 미발생.

- [ ] **Step 3: `translate_stream` 확장**

`agent/ui_stream.py`의 `translate_stream`을 교체:
```python
async def translate_stream(
    events: AsyncIterator,
    *,
    message_id: str,
    thread_id: str = "",
    check_hallucination: Callable[[str, str], str] = _default_check_hallucination,
) -> AsyncIterator[dict]:
    """astream (mode,payload) 이벤트 → UI Message Stream 파트.

    분기:
      - 환불 interrupt → data-confirmation 후 종료
      - 검색 사용(RAG) → 답변 토큰 버퍼링 → 할루시네이션 검사본을 text 1블록으로
      - 일반 답변 → text 토큰 실시간
    """
    yield {"type": "start", "messageId": message_id}

    text_id = new_text_id()
    text_started = False
    used_search = False
    search_contexts: list[str] = []
    answer_buffer: list[str] = []
    interrupt_action = None

    async for mode, payload in events:
        if mode == "updates":
            action = extract_interrupt_action(payload)
            if action is not None:
                interrupt_action = action
                break
        elif mode == "messages":
            chunk, metadata = payload
            if is_search_tool_result(chunk):
                used_search = True
                search_contexts.append(chunk.content)
            elif is_final_answer_chunk(chunk, metadata):
                if used_search:
                    answer_buffer.append(chunk.content)
                else:
                    if not text_started:
                        yield {"type": "text-start", "id": text_id}
                        text_started = True
                    yield {"type": "text-delta", "id": text_id, "delta": chunk.content}

    if interrupt_action is not None:
        yield {
            "type": "data-confirmation",
            "data": {
                "tool": interrupt_action["name"],
                "args": interrupt_action["args"],
                "thread_id": thread_id,
            },
        }
    elif used_search and answer_buffer:
        combined = "\n\n---\n\n".join(search_contexts)
        checked = check_hallucination("".join(answer_buffer), combined)
        yield {"type": "text-start", "id": text_id}
        yield {"type": "text-delta", "id": text_id, "delta": checked}
        yield {"type": "text-end", "id": text_id}
    elif text_started:
        yield {"type": "text-end", "id": text_id}

    yield {"type": "finish"}
```

- [ ] **Step 4: 통과 확인 (기존 + 신규)**

Run: `cd customer-support-agent/backend && uv run pytest tests/test_ui_stream.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: `/chat/stream`에서 thread_id 인자 복원**

`routers/chat.py`의 `chat_stream` 내 호출을 다음으로:
```python
            async for part in translate_stream(
                events, message_id=message_id, thread_id=request.thread_id
            ):
                yield format_sse(part)
```

- [ ] **Step 6: 커밋**

```bash
cd /Users/dohyunkim/Documents/langchain-for-ai-agent-project
git add customer-support-agent/backend/agent/ui_stream.py customer-support-agent/backend/tests/test_ui_stream.py customer-support-agent/backend/routers/chat.py
git commit -m "feat(backend): RAG buffered text + data-confirmation in UI stream translator"
```

---

## Task 5: 프론트엔드 — 차단/환불 data 파트 렌더러

**Files:**
- Create: `customer-support-agent/frontend/components/blocked-notice.tsx`
- Create: `customer-support-agent/frontend/components/refund-confirm-card.tsx`
- Modify: `customer-support-agent/frontend/app/page.tsx` (파트 분기 추가)

- [ ] **Step 1: BlockedNotice 컴포넌트**

`components/blocked-notice.tsx`:
```tsx
export function BlockedNotice({ reason }: { reason: string }) {
  return (
    <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">
      ⚠️ {reason}
    </div>
  );
}
```

- [ ] **Step 2: RefundConfirmCard 컴포넌트**

`components/refund-confirm-card.tsx`:
```tsx
import type { Decision } from "@/lib/chat";

export function RefundConfirmCard({
  args,
  busy,
  onDecide,
}: {
  args: Record<string, unknown>;
  busy: boolean;
  onDecide: (d: Decision) => void;
}) {
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-4">
      <p className="mb-2 text-sm font-medium">
        환불 신청을 접수할까요? ({JSON.stringify(args)})
      </p>
      <div className="flex gap-2">
        <button
          onClick={() => onDecide("approve")}
          disabled={busy}
          className="rounded-md bg-amber-600 px-3 py-1 text-sm text-white disabled:opacity-50"
        >
          확인(접수)
        </button>
        <button
          onClick={() => onDecide("reject")}
          disabled={busy}
          className="rounded-md bg-gray-300 px-3 py-1 text-sm disabled:opacity-50"
        >
          취소
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: page.tsx 파트 분기 추가**

`app/page.tsx`의 import에 추가:
```tsx
import { BlockedNotice } from "@/components/blocked-notice";
import { RefundConfirmCard } from "@/components/refund-confirm-card";
```
`m.parts.map(...)` 내부의 텍스트 분기에 data 파트 분기를 추가(삼항을 switch 스타일로):
```tsx
                {m.parts.map((part, i) => {
                  if (part.type === "text") {
                    return <Response key={`${m.id}-${i}`}>{part.text}</Response>;
                  }
                  if (part.type === "data-blocked") {
                    return <BlockedNotice key={`${m.id}-${i}`} reason={part.data.reason} />;
                  }
                  if (part.type === "data-confirmation") {
                    return (
                      <RefundConfirmCard
                        key={`${m.id}-${i}`}
                        args={part.data.args}
                        busy={status === "streaming" || status === "submitted"}
                        onDecide={(d) => sendMessage(undefined, { metadata: { decision: d } })}
                      />
                    );
                  }
                  return null;
                })}
```
> `sendMessage(undefined, { metadata })`는 Task 6에서 정확 동작을 검증한다. 여기서는 렌더링까지만 확인.

- [ ] **Step 4: 타입체크 + 차단 흐름 확인**

Run: `cd customer-support-agent/frontend && npx tsc --noEmit`
Expected: 통과 (`part.data.reason`/`part.data.args`가 `ChatDataParts` 제네릭으로 타입됨).
브라우저에서 욕설 입력 → `BlockedNotice`(⚠️) 렌더 확인. RAG 질문 → 검증된 답변 텍스트 렌더 확인(문서 업로드돼 있을 때).

- [ ] **Step 5: 커밋**

```bash
cd /Users/dohyunkim/Documents/langchain-for-ai-agent-project
git add customer-support-agent/frontend/components/blocked-notice.tsx customer-support-agent/frontend/components/refund-confirm-card.tsx customer-support-agent/frontend/app/page.tsx
git commit -m "feat(frontend): render data-blocked and data-confirmation parts"
```

---

## Task 6: HITL 스트리밍 재개 — `/chat/confirm` 재작성 + 승인 흐름 (최고 위험, 마지막)

**Files:**
- Modify: `customer-support-agent/backend/routers/chat.py` (`confirm` 함수 재작성)
- 검증/조정: `customer-support-agent/frontend/app/page.tsx`, `lib/chat.ts`

- [ ] **Step 1: `/chat/confirm`을 UI Message Stream 스트리밍 재개로 재작성**

`routers/chat.py`의 `confirm` 함수 전체 교체:
```python
@router.post("/chat/confirm")
async def confirm(request: ConfirmRequest):
    """환불 신청을 확인(approve)/취소(reject)하여 에이전트를 재개하고,
    재개된 답변을 UI Message Stream(SSE)으로 스트리밍한다.

    useChat transport가 metadata.decision 감지 시 이 엔드포인트로 라우팅한다.
    """

    async def event_generator():
        message_id = f"msg-{uuid.uuid4().hex}"
        try:
            agent = get_agent()
            events = agent.astream(
                Command(resume={"decisions": [{"type": request.decision}]}),
                config={"configurable": {"thread_id": request.thread_id}},
                context=AgentContext(user_id=request.user_id),
                stream_mode=["updates", "messages"],
            )
            async for part in translate_stream(
                events, message_id=message_id, thread_id=request.thread_id
            ):
                yield format_sse(part)
            yield DONE
        except Exception as e:
            yield format_sse({"type": "error", "errorText": str(e)})
            yield DONE

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=UI_STREAM_HEADERS,
    )
```
> 기존 `confirm`의 JSON 반환·`ConfirmRequest` import는 유지(모델 재사용). `Command` import는 상단에 이미 추가됨(Task 2).

- [ ] **Step 2: 백엔드 재개 스트림 curl 검증**

먼저 환불 요청으로 interrupt를 만들고 thread_id를 얻은 뒤(=/chat/stream에서 data-confirmation의 thread_id), 같은 thread_id로:
```bash
# 1) interrupt 유발
curl -sN -X POST http://localhost:8000/chat/stream -H "Content-Type: application/json" \
  -d '{"message":"주문 O-1 환불해줘","thread_id":"t-refund-1","user_id":"demo"}' --max-time 25 | head
# → data-confirmation 파트가 나오는지 확인
# 2) 승인 재개 (스트리밍)
curl -sN -X POST http://localhost:8000/chat/confirm -H "Content-Type: application/json" \
  -d '{"thread_id":"t-refund-1","decision":"approve","user_id":"demo"}' --max-time 25 | head
```
Expected: 2)에서 `start`→`text-*`(재개된 접수 확인 답변)→`finish`→`[DONE]`.

- [ ] **Step 3: 프론트 승인 흐름 검증 — `sendMessage(undefined, {metadata})` 동작 확인**

브라우저에서 환불 요청 → `RefundConfirmCard` 표시 → "확인(접수)" 클릭.
Expected: `/chat/confirm`으로 요청이 가고(네트워크 탭), 재개된 답변이 **새 assistant 메시지**로 스트리밍됨. 가짜 user 버블이 생기지 않아야 함.

만약 `sendMessage(undefined, ...)`가 (a) 빈 user 메시지를 만들거나 (b) 요청을 안 보내면, 대안으로 전환:
- `lib/chat.ts`에서 `regenerate` 대신, 명시적으로 마지막 사용자 메시지 텍스트 없이 트리거가 필요하면 `sendMessage({ text: "" }, { metadata: { decision } })`를 쓰고, `prepareSendMessagesRequest`는 `requestMetadata.decision`만으로 `/chat/confirm` 바디를 구성(텍스트 무시)한다. 빈 user 버블이 보이면 렌더에서 `part.text === ""`인 user 텍스트 파트를 숨긴다.
- 이 분기 선택은 Step 3 실제 동작 관찰 후 확정한다(번들 문서만으로는 `sendMessage(undefined)`의 UI 반영이 모호).

- [ ] **Step 4: 타입체크 + 전체 백엔드 테스트**

Run:
```bash
cd customer-support-agent/frontend && npx tsc --noEmit
cd ../backend && uv run pytest -q
```
Expected: tsc 통과, pytest 전부 통과(기존 + ui_stream 4).

- [ ] **Step 5: 커밋**

```bash
cd /Users/dohyunkim/Documents/langchain-for-ai-agent-project
git add customer-support-agent/backend/routers/chat.py customer-support-agent/frontend/app/page.tsx customer-support-agent/frontend/lib/chat.ts
git commit -m "feat: streaming HITL refund resume via /chat/confirm UI Message Stream"
```

---

## Task 7: 정리 + 전체 E2E 검증

**Files:**
- 삭제 대상 확인: 더 이상 쓰지 않는 `agent/streaming.py`? → **유지**(`ui_stream`이 재사용). 구 `tests/test_streaming.py` → 유지(헬퍼 여전히 사용).
- 확인: `routers/chat.py`에서 `sse_starlette`·`json` 미사용 import 제거됨.

- [ ] **Step 1: 죽은 import/코드 스캔**

Run:
```bash
cd customer-support-agent/backend
grep -nE "sse_starlette|import json" routers/chat.py || echo "clean"
uv run python -W error::DeprecationWarning -c "import routers.chat; print('ok')"
```
Expected: chat.py에 `sse_starlette` 없음, import 비퇴화 통과.

- [ ] **Step 2: 4흐름 브라우저 E2E**

http://localhost:3001 에서:
1. 일반 질문 → 토큰 스트리밍
2. 욕설 → ⚠️ BlockedNotice
3. (문서 업로드 후) 문서 질문 → 검증된 RAG 답변
4. 환불 요청 → 확인 카드 → 승인 → 재개 답변 스트리밍
Expected: 4흐름 모두 정상.

- [ ] **Step 3: 최종 테스트 + 커밋(필요 시)**

Run: `cd customer-support-agent/backend && uv run pytest -q`
Expected: 전부 통과. 정리 변경이 있으면:
```bash
cd /Users/dohyunkim/Documents/langchain-for-ai-agent-project
git add -A customer-support-agent
git commit -m "chore: phase 6.5 cleanup (remove unused imports)"
```

---

## 자체 검토 메모

- **스펙 커버리지:** 매핑 표(Task 1·4), thread_id transport(Task 3), HITL 스트리밍 재개(Task 6), 테스트(Task 1·4·7), 엔드포인트 변경(Task 2·6) — 스펙 전 항목 대응. 스펙의 "별도 `/chat/confirm` 유지"는 transport `api` 오버라이드로 충족(스펙 이탈 없음).
- **위험 순서:** 일반 답변(1–3) → 데이터 파트(4–5) → HITL 재개(6). 입증 가능한 것부터.
- **잔여 검증(실행 중):** AI Elements 컴포넌트 export/props(Task 3 Step 2), `sendMessage(undefined)` UI 반영(Task 6 Step 3), `DefaultChatTransport` 제네릭 타입(Task 3 Step 3). 각 태스크에 검증 스텝 내장.
