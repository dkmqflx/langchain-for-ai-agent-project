# Frontend Implementation Plan — Next.js + 커스텀 SSE 클라이언트

## Context

`01.customer-support-agent/backend`(FastAPI)에 대한 프론트엔드를 Next.js 16(App Router) + Tailwind로 구축한다.
스트리밍 채팅이 핵심이며, **백엔드가 내보내는 커스텀 SSE를 프론트가 직접 `fetch` + `ReadableStream`으로 파싱**한다(AI SDK 미사용).

### 방식: FastAPI 커스텀 SSE를 프론트가 직접 소비

- 백엔드는 **그대로** 둔다(`/chat/stream`이 이미 커스텀 SSE를 emit).
- 프론트는 `fetch` + `ReadableStream`으로 SSE를 직접 파싱하는 커스텀 파서(`lib/chat.ts`)를 둔다. **AI SDK(`useChat`/`streamText`)는 쓰지 않는다.**

> **백엔드는 수정하지 않는다.** `backend/routers/chat.py`의 `/chat/stream`은 이미 커스텀 SSE를 emit하고
> `backend/agent/streaming.py`의 판별 헬퍼도 그대로다. 이 plan은 **프론트엔드만** 다룬다.

### 전체 아키텍처

```
Browser (Next.js + shadcn/ui, plain 말풍선)
   │  lib/chat.ts: fetch POST /chat/stream → res.body.getReader() → SSE 블록 파싱 → onEvent 콜백
   ▼
FastAPI /chat/stream                ← 변경 없음 (이미 커스텀 SSE emit)
   │  event: token                 {"content":"..."}                              ← 일반 답변 토큰(실시간)
   │  event: message               {"response":"...","status":"completed"}        ← RAG 검사본(1회)
   │  event: blocked               {"response":"...","thread_id":"..."}           ← 욕설 차단
   │  event: confirmation_required {"thread_id":"...","tool":"...","args":{...}}   ← 환불 본인확인
   │  event: done                  {"thread_id":"...","status":"completed"}
   │  event: error                 {"detail":"..."}
   ▼
기존 에이전트 파이프라인 (가드레일·HITL·할루시네이션·PII) — 그대로 유지
```

**핵심 주의**: 일반 답변은 `token`이 여러 번 흐르고, **RAG(검색) 답변은 `token` 없이 `message` 1회**로 온다
(할루시네이션 검사 후 완성본). 프론트 파서/UI는 두 경우를 모두 처리해야 한다.

### 화면 범위 (4개)

| 화면 | 경로(예시) | 사용 엔드포인트 |
|------|-----------|----------------|
| 채팅 (메인) | `/` | `POST /chat/stream`, `POST /chat/confirm` |
| 관리자 문서 업로드 | `/admin/documents` | `POST /upload`, `GET /documents` |
| 관리자 환불 승인 큐 | `/admin/refunds` | `GET /pending`, `POST /approve` |
| 내 환불 조회 (사용자) | `/refunds` | `GET /refunds?user_id=...` |

### 진행 원칙

- **한 단계씩(step by step)** 진행한다. 각 Phase는 독립적으로 완성·검증·커밋 가능하도록 설계했다.
- 각 Phase 끝에는 **검증 방법**과 **커밋**이 있다. 검증을 통과해야 다음 Phase로 넘어간다.
- 모든 코드는 각 라이브러리 **공식 문서**에 따라 작성한다(`CLAUDE.md` 표준).

### 공식 문서 레퍼런스

- MDN — Fetch & Streams (`ReadableStream`, `getReader`, `TextDecoder`): https://developer.mozilla.org/en-US/docs/Web/API/Streams_API
- MDN — Server-Sent Events 포맷: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events
- Next.js App Router: https://nextjs.org/docs/app
- shadcn/ui: https://ui.shadcn.com/docs
- (참고) `frontend/AGENTS.md`: "이 Next는 네가 알던 Next가 아니다 — 코드 작성 전 `node_modules/next/dist/docs/`의 해당 가이드를 먼저 읽어라."

---

## Phase 0 — 프로젝트 셋업 & 기반 ✅ 완료

**목표**: Next.js 16 + Tailwind + shadcn/ui 기반을 갖추고, FastAPI를 가리키는 환경변수·폴더 구조를 만든다.

- **버전**: Next.js `16.2.7`, React `19.2`, Tailwind `v4`.
- **포트 조합**: 프론트 dev `3100`(`next dev -p 3100`) → 백엔드 `8000`. (백엔드 CORS가 `localhost:3100` 허용.)
- **유지 의존성**: `@base-ui/react`(shadcn `components/ui/*`의 엔진 — 제거 금지), `class-variance-authority`, `clsx`, `tailwind-merge`, `cmdk`, `embla-carousel-react`, `lucide-react`, `tw-animate-css`, `shadcn`.

### 커밋
`chore(frontend): drop ai sdk / ai elements, unblock production build`

---

## Phase 1 — 프론트엔드 SSE 클라이언트 `lib/chat.ts`

**목표**: 백엔드 `/chat/stream`(이미 커스텀 SSE emit)을 호출하고, SSE 블록을 파싱해 이벤트 콜백으로 넘기는
**순수 클라이언트 모듈**을 만든다. **UI는 아직 만들지 않는다** — 통신 계층만 단독으로 완성·검증한다.

> 백엔드는 변경하지 않는다. 이 Phase의 산출물은 `frontend/lib/chat.ts` 하나다.
> 가장 깨지기 쉬운 부분(SSE 파싱·CRLF 구분자)을 UI와 분리해 먼저 안정화한다.

### 작업

1. **`lib/chat.ts`** 작성:
   - `ChatEvent` 타입 — 백엔드 이벤트와 1:1: `token` | `message` | `blocked` | `confirmation_required` | `done` | `error`.
   - `parseSseBlock(block)` — `event:` / `data:` 라인을 읽어 `{ type, ...JSON }`로 변환.
   - `streamChat(body, onEvent)` — `fetch(POST /chat/stream)` → `res.body.getReader()`로 청크를 읽으며
     **버퍼에 누적 → SSE 구분자로 분리 → 완성된 블록만 파싱**.
   - `confirmChat(body)` — 환불 확인/취소용 비스트리밍 `POST /chat/confirm` 호출(Phase 3에서 사용).
2. **⚠️ CRLF 구분자 함정**(backend/CLAUDE.md·메모리에 기록): `sse-starlette`는 이벤트 구분자를 **`\r\n\r\n`**으로
   내보낸다. `buffer.split("\n\n")`만 쓰면 블록이 영영 안 나뉘어 **화면이 빈다.** 반드시
   `buffer.split(/\r\n\r\n|\n\n/)`로 분리하고, 라인 파싱 시 `.trim()`으로 잔여 `\r`를 제거한다.

### 검증
```bash
# 백엔드 실행 중이어야 함 (OPENAI_API_KEY + DB 필요)
cd backend && uv run uvicorn main:app --reload   # 별도 터미널
```
- Node 스크립트나 임시 페이지에서 `streamChat({message:"안녕", thread_id:"t1", user_id:"u1"}, console.log)`를 호출 →
  콘솔에 `{type:"token", content:"..."}`들이 흐르고 `{type:"done", ...}`로 끝나는지 확인.
- raw 바이트 확인이 필요하면: `curl -sN -d '{"message":"안녕","thread_id":"t1","user_id":"u1"}' -H "Content-Type: application/json" http://localhost:8000/chat/stream | xxd | grep 0d0a0d0a` (CRLF 구분자 존재 확인).

### 커밋
`feat(frontend): add /chat/stream sse client (lib/chat.ts)`

---

## Phase 2 — 채팅 UI 기본 스트리밍 (plain shadcn/ui)

**목표**: `lib/chat.ts`를 써서 일반 답변 토큰이 실시간으로 화면에 흐르게 한다. AI Elements 없이
shadcn/ui + Tailwind로 말풍선/입력창을 직접 구성한다.

### 작업
1. **`app/page.tsx`** (채팅 화면) — 클라이언트 컴포넌트.
2. **상태 관리(커스텀 훅 권장 `lib/useChatStream.ts` 또는 page 내부)**:
   - `messages: { role, content }[]`, `streaming: boolean`, `input: string`.
   - 전송 시 `streamChat({message, thread_id, user_id}, onEvent)` 호출.
   - `onEvent` 처리:
     - `token` → 진행 중인 assistant 메시지에 `content` **누적**(append).
     - `message` → assistant 메시지를 `response`로 **교체/확정**(RAG 검사본은 토큰 없이 한 번에 옴).
     - `done` → 스트리밍 종료.
     - `blocked` / `confirmation_required` → Phase 3에서 처리(지금은 임시로 무시 또는 텍스트 표시).
     - `error` → 에러 메시지 표시.
3. **UI**: shadcn `Button`/`Input` + 직접 만든 말풍선(`role`에 따라 정렬/색). 스트리밍 중 표시(점멸 커서/spinner).
   - 마크다운 렌더가 필요하면 `react-markdown` 등 **경량 라이브러리만** 추가(선택).
4. **`thread_id`(대화 단위), `user_id`(임시 상수/입력값) 관리.**

### 검증
- 일반 질문 → 토큰이 실시간 누적 렌더된다.
- 문서 기반 질문(RAG) → `message`로 완성본이 한 번에 뜬다(토큰 흐름 없이).
- 같은 `thread_id` 유지 시 대화 맥락이 이어진다(단기 기억).

### 커밋
`feat(frontend): streaming chat ui consuming /chat/stream sse`

---

## Phase 3 — 차단 + 환불 본인확인 이벤트 처리 ⚠️

**목표**: `blocked` / `confirmation_required` 이벤트를 UI에서 처리한다. 이 프로젝트 고유 도메인 흐름이라 가장 까다롭다.

### 작업
1. **`blocked`**: `{response}`(차단 안내)를 말풍선/배너로 표시. 모델 호출 없이 단락된 흐름.
2. **`confirmation_required`** (환불 본인확인):
   - `{tool, args, thread_id}`로 "환불 신청을 진행할까요?"(주문/금액/사유 표시) 카드 렌더 — shadcn `Card`/`Button`.
   - **승인/취소 → `confirmChat({ thread_id, decision: "approve"|"reject", user_id })`** 호출(`POST /chat/confirm`, 별도 fetch).
   - 응답(`status: "submitted"|"cancelled"` + `response`)을 채팅 후속 메시지로 반영.
3. **상태 관리**: `confirmation_required`에서 받은 `thread_id`를 confirm 호출에 그대로 사용. confirm 이후 채팅 흐름 복귀.

> 참고: `user_id`를 클라이언트가 다시 보내는 알려진 한계는 백엔드와 동일하게 유지(학습용).

### 검증
- 욕설 입력 → 차단 메시지 표시(모델 호출 없이 단락).
- "환불해줘 ORD-123" 류 → 확인 카드 표시 → 승인="submitted" / 취소="cancelled" 반영.
- 승인 시 `GET /pending`에 신청이 쌓이는지 교차 확인(Phase 4와 연결).

### 커밋
`feat(frontend): handle blocked + refund confirmation sse events`

---

## Phase 4 — 관리자 문서 업로드 화면

**목표**: PDF/TXT 업로드 → RAG 인덱싱, 업로드된 문서 목록 표시. (스트리밍 없음 — 단순 폼.)

### 작업
1. **`app/admin/documents/page.tsx`**.
2. 파일 선택 + 업로드 폼 → `POST /upload` (multipart/form-data).
3. `GET /documents` → 업로드된 문서 목록 테이블.
4. 업로드 진행/성공/실패 상태 표시(shadcn `Toast`/`Button`).

### 검증
- PDF 업로드 → 성공 응답 → 목록에 나타남.
- 업로드한 문서 내용을 채팅(`/`)에서 질문 → RAG 검색으로 답변됨(전 Phase와 연결).

### 커밋
`feat(frontend): admin document upload + list`

---

## Phase 5 — 관리자 환불 승인 큐

**목표**: 승인 대기(pending) 환불 신청 목록을 보고 승인/거절한다. (LangGraph 재개가 아닌 일반 CRUD.)

### 작업
1. **`app/admin/refunds/page.tsx`**.
2. `GET /pending` → 대기 목록 테이블(user_id, order_id, amount, reason, created_at).
3. 각 행에 승인/거절 → `POST /approve` (`{ refund_id, decision }`).
4. 처리 후 목록 갱신(이미 처리된 신청은 400 → 안내).

### 검증
- Phase 3에서 승인한 신청이 목록에 보인다.
- 승인/거절 → 상태가 바뀌고 목록에서 사라지거나 상태 표시.

### 커밋
`feat(frontend): admin refund approval queue`

---

## Phase 6 — 내 환불 조회 (사용자)

**목표**: 사용자가 본인 환불 신청 상태를 조회하는 마이페이지.

### 작업
1. **`app/refunds/page.tsx`**.
2. `GET /refunds?user_id=...` → 본인 신청 목록과 상태(pending/approved/rejected).
3. `user_id` 입력 또는 채팅에서 쓰던 값 재사용.

### 검증
- 신청한 `user_id`로 조회 → 신청 내역과 현재 상태가 보인다.
- Phase 5에서 관리자가 바꾼 상태가 반영된다.

### 커밋
`feat(frontend): user refund status page`

---

## Phase 7 — 마무리 (선택)

**목표**: 화면을 하나의 앱으로 묶고 다듬는다.

### 작업
- 공통 레이아웃/네비게이션(채팅 · 관리자 · 내 환불).
- 로딩/에러/빈 상태 처리, 반응형, 기본 접근성.
- (선택) 운영 점검: LangSmith 트레이스 연동 확인 등.

### 검증
- 4개 화면을 네비게이션으로 오가며 전체 플로우(업로드 → 채팅 → 환불 신청 → 승인 → 조회)가 끊김 없이 동작.

### 커밋
`feat(frontend): app shell, navigation, polish`

---

## 학습 가이드 관례 (참고)

이 레포는 각 Phase 완료 후 `study/NN_phaseN_learning_guide.md`(한국어 초심자용 해설)를 작성하는 관례가 있다.
프론트엔드도 동일하게 `frontend/study/`에 Phase별 학습 가이드를 남긴다.

---

## 진행 체크리스트

- [x] Phase 0 — 셋업·정리 완료 (AI SDK/AI Elements 제거, 포트 정리, 빌드 성공)
- [ ] Phase 1 — SSE 클라이언트 `lib/chat.ts`
- [ ] Phase 2 — 채팅 스트리밍 UI (plain)
- [ ] Phase 3 — 차단 + 환불 확인 이벤트 ⚠️
- [ ] Phase 4 — 문서 업로드
- [ ] Phase 5 — 환불 승인 큐
- [ ] Phase 6 — 내 환불 조회
- [ ] Phase 7 — 마무리(선택)
