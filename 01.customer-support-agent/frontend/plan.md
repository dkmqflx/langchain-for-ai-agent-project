# Frontend Implementation Plan — Next.js + AI SDK + AI Elements

## Context

`01.customer-support-agent/backend`(FastAPI)에 대한 프론트엔드를 Next.js 16(App Router) + Tailwind로 구축한다.
스트리밍 채팅이 핵심이며, **AI SDK의 `useChat` + AI Elements 컴포넌트**를 풀스택으로 활용한다.

### 채택 방식: C안 (FastAPI가 AI SDK 프로토콜을 직접 emit)

AI Elements(`elements.ai-sdk.dev`)는 독립 UI 라이브러리가 아니라 **AI SDK의 `useChat` 위에 얹힌 shadcn/ui 컴포넌트**다.
따라서 `useChat`이 이해하는 스트림 형식으로 데이터가 와야 한다. 세 가지 연동 방식 중:

| 방식 | 백엔드 | useChat | 비고 |
|------|--------|---------|------|
| A. 직접 SSE 소비 | 그대로 | ❌ | 커스텀 훅 직접 작성, AI SDK 미사용 |
| B. Next.js 프록시 변환 | 그대로 | ✅ | Route Handler가 형식 변환 |
| **C. FastAPI 직접 emit** ★채택 | **수정** | ✅ | 공식 권장, 프록시 불필요 |

C를 택한 이유:
- **공식 문서 표준**: AI SDK는 "다른 언어 백엔드는 Data Stream Protocol을 직접 emit하고 `useChat`을 그 엔드포인트로 가리키라"고 안내한다. Vercel 공식 FastAPI 템플릿도 존재. → 레포 `CLAUDE.md`의 "공식 문서만" 표준에 가장 부합.
- 프록시/변환 레이어가 없어 구조가 단순하다.

### 전체 아키텍처

```
Browser (Next.js + AI Elements)
   │  useChat({ transport: DefaultChatTransport({ api: FASTAPI/chat/stream }) })
   ▼
FastAPI /chat/stream                ← Phase 1에서 출력 "형식만" 변환 (로직 유지)
   │  헤더: x-vercel-ai-ui-message-stream: v1
   │  data: {"type":"text-delta","id":"0","delta":"..."}   ← 토큰
   │  data: {"type":"data-blocked","data":{...}}            ← 욕설 차단
   │  data: {"type":"data-confirmation","data":{...}}       ← 환불 본인확인
   │  data: {"type":"finish"}  /  data: [DONE]
   ▼
기존 에이전트 파이프라인 (가드레일·HITL·할루시네이션·PII) — 그대로 유지
```

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
- 모든 코드는 각 라이브러리 **공식 문서**에 따라 작성한다(`CLAUDE.md` 표준). 아래 명시한 type/필드/컴포넌트명은 작성 시 공식 문서로 한 번 더 검증한다.

### 공식 문서 레퍼런스

- AI SDK UI (`useChat`, 스트림 프로토콜): https://ai-sdk.dev/docs/ai-sdk-ui
- Data Stream Protocol: https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol
- AI Elements: https://elements.ai-sdk.dev/
- Next.js App Router: https://nextjs.org/docs/app
- shadcn/ui: https://ui.shadcn.com/docs

---

## Phase 0 — 프로젝트 셋업 & 기반 ✅ 완료

**목표**: 빈 `frontend/`에 Next.js 16 + Tailwind + shadcn/ui + AI SDK + AI Elements를 설치하고, FastAPI를 가리키는 환경변수·폴더 구조를 만든다.

> **설치된 실제 버전**: Next.js `16.2.7`, React `19.2`, Tailwind `v4`, `ai@6`, `@ai-sdk/react@3`. (Node 20.17 — Next 16은 20.19+ 권장이라 `EBADENGINE` 경고가 뜨지만 dev/실행은 정상.)
>
> **알려진 이슈 / 다음 단계 입력값** (검증으로 확인된 실제 상태):
> - 🔴 **`next build` 현재 실패**: dev 서버는 뜨지만(타입에러 무시) **프로덕션 빌드는 깨진 상태**다. 원인은 AI Elements 컴포넌트들이 구 Base UI API(`openDelay`/`closeDelay`, `preventBaseUIHandler` 등)로 작성됐는데 설치된 `@base-ui/react@1.5.0`엔 해당 prop이 없는 **버전 드리프트**. 영향 파일: `inline-citation`, `attachments`, `prompt-input`, `context`, `schema-display`, `voice-selector` 등 — **우리가 쓸 `prompt-input` 포함**. → **Phase 2 착수 전 선결 과제**. 해결 후보: ① Base UI 호환 버전 핀, ② 해당 컴포넌트 수동 패치, ③ ai-elements 레지스트리 갱신 대기. (`typescript.ignoreBuildErrors`로 덮는 건 '공식 문서대로' 표준에 어긋나므로 지양.)
> - ⏩ **[Phase 1 선행 입력]** AI SDK가 **v6**다. 백엔드가 emit할 형식은 "v6 `useChat`이 받기를 기대하는 Data Stream Protocol"이어야 하므로, **Phase 1 착수 전** 이 문서 상단 'Data Stream Protocol' 표와 `DefaultChatTransport`를 **v6 공식 문서로 재확인**한다(v5 기준 표기일 수 있음). 이건 Phase 2가 아니라 Phase 1의 입력값.
> - 📄 `frontend/AGENTS.md` 지시: "이 Next는 네가 알던 Next가 아니다 — 코드 작성 전 `node_modules/next/dist/docs/`의 해당 가이드를 먼저 읽어라." Phase 1~2 구현 시 준수.
>
> **권장 다음 micro-step (Phase 1 전)**: AI Elements가 이 스택(Next16/React19/AI SDK v6)에서 *런타임에 실제로 렌더되는지* 15분 스파이크로 확인 — mock `useChat`으로 `Conversation`+`PromptInput`만 띄워본다. 백엔드를 통째로 갈아엎는 Phase 1 전에 UI 라이브러리 생존을 먼저 검증.

### 작업

1. **Next.js 생성** (현재 `frontend/`에서):
   - `npx create-next-app@latest .` — App Router, TypeScript, Tailwind, ESLint 선택.
2. **shadcn/ui 초기화**: `npx shadcn@latest init` (AI Elements가 shadcn 위에 설치되므로 선행 필수).
3. **AI SDK 설치**: `npm i ai @ai-sdk/react`.
4. **AI Elements 설치**: `npx ai-elements@latest`
   - 또는 컴포넌트별: `npx shadcn@latest add https://elements.ai-sdk.dev/api/registry/all.json`
   - 컴포넌트는 `@/components/ai-elements/`에 코드로 설치됨(직접 커스터마이즈 가능).
5. **환경변수**: `.env.local`에 `NEXT_PUBLIC_API_URL=http://localhost:8000`.
6. **공통 API 헬퍼**: `lib/api.ts` — `NEXT_PUBLIC_API_URL` 기반 fetch 래퍼(에러 처리, JSON 파싱). 백엔드 응답 봉투(`{ data, isSuccess, code, message }`)를 다루는 타입도 여기 정의.

### 검증 ✅
- `npm run dev` → 기본 페이지가 뜬다(3000 사용 중이라 3001, HTTP 200 확인).
- `.env.local` 로드 확인, `turbopack.root` 고정으로 lockfile 워크스페이스 경고 해소.
- shadcn 초기화로 `components/ui/button.tsx`·`lib/utils.ts` 생성됨.

### 커밋
`chore(frontend): scaffold next.js + tailwind + ai sdk + ai elements`

---

## Phase 1 — 백엔드 `/chat/stream`을 AI SDK Data Stream Protocol로 변환 (C의 핵심) ⚠️

**목표**: FastAPI가 내보내는 **스트림 출력 형식**을 AI SDK가 이해하는 형식으로 바꾼다. **에이전트 로직·미들웨어·가드레일·HITL·할루시네이션 검사는 그대로 둔다.**

> 이 Phase만 백엔드(`backend/routers/chat.py`, `backend/agent/streaming.py`)를 수정한다. 가장 novel하고 위험한 단계이므로 단독 Phase로 분리.
>
> ⏩ **선행 입력**: 착수 전 AI SDK **v6**의 Data Stream Protocol/`useChat` 수신 형식을 공식 문서로 확정할 것(Phase 0 메모 참조). 백엔드는 "v6가 받기를 기대하는 형식"만 emit하면 된다.

### 작업 (출력 형식 매핑)

기존 커스텀 SSE → AI SDK 파트 변환:

| 기존 이벤트 | → AI SDK 파트 |
|------------|---------------|
| 응답 시작 | `{"type":"start"}` → `{"type":"text-start","id":"0"}` |
| `event: token` `{content}` | `{"type":"text-delta","id":"0","delta":"..."}` |
| 답변 끝 | `{"type":"text-end","id":"0"}` |
| `event: blocked` | `{"type":"data-blocked","data":{"reason":"..."}}` (커스텀 data part) |
| `event: confirmation_required` | `{"type":"data-confirmation","data":{"tool":"...","args":{...},"thread_id":"..."}}` |
| `event: done` | `{"type":"finish"}` → `data: [DONE]` |
| 예외 | `{"type":"error","errorText":"..."}` |

- **응답 헤더**: `x-vercel-ai-ui-message-stream: v1` 추가.
- **RAG 답변 버퍼링 처리 유지**: 현재 코드는 검색(RAG) 답변일 때 토큰을 버퍼링했다가 할루시네이션 검사 후 한 번에 보낸다. 프로토콜에서는 → 일반 답변은 `text-delta`를 실시간 emit, RAG 답변은 deltas를 보류했다가 **검사 완료본을 `text-start`→`text-delta`(전체)→`text-end`로 1회 emit**.
- **알려진 한계 유지**(설계 문서에 이미 기재): 스트리밍 경로의 출력 PII 마스킹·할루시네이션 교정 보장은 비스트리밍 `POST /chat`에서만. 이 한계는 그대로 둔다(별도 개선 아님).

### 검증
- `curl -N -H "Content-Type: application/json" -d '{"message":"안녕"}' http://localhost:8000/chat/stream` →
  - 응답 헤더에 `x-vercel-ai-ui-message-stream: v1`.
  - 본문이 `data: {"type":"text-delta",...}` 형식으로 흐르고 `data: [DONE]`로 끝남.
- 욕설 입력 → `data-blocked` 파트가 나온다.
- 환불 요청 입력 → `data-confirmation` 파트가 나온다.
- 비스트리밍 `POST /chat`은 영향 없음(기존 테스트 통과).
- CORS: `localhost:3000` Origin 허용 확인(`backend/main.py`에 CORS 이미 설정됨 — origin 목록만 점검).

### 커밋
`feat(backend): emit ai sdk data stream protocol on /chat/stream`

---

## Phase 2 — 채팅 UI 기본 스트리밍

> 🔴 **선결 과제**: Phase 0에서 확인된 `next build` 실패(AI Elements ↔ `@base-ui/react@1.5.0` 타입 드리프트)를 먼저 해결할 것. 우리가 쓸 `prompt-input`이 영향 파일에 포함된다. (Phase 0 메모의 해결 후보 참조.)

**목표**: `useChat`으로 `/chat/stream`에 연결하고, 일반 답변 토큰이 실시간으로 화면에 흐르게 한다.

### 작업
1. **`app/page.tsx`** (채팅 화면) — 클라이언트 컴포넌트.
2. `useChat`(`@ai-sdk/react`) + `DefaultChatTransport({ api: ${NEXT_PUBLIC_API_URL}/chat/stream })`.
3. AI Elements 조합:
   - `Conversation` — 메시지 스크롤 영역
   - `Message` / `MessageContent` / `Response` — 말풍선 + 마크다운 렌더
   - `PromptInput` — 입력창 + 전송
   - `Loader` — 스트리밍 대기 표시
4. **요청 바디 매핑**: 백엔드는 `{ message, thread_id, user_id }`를 받는다. `useChat`의 전송 바디를 백엔드 스키마에 맞게 구성(transport의 body/prepare 옵션 활용). `thread_id`(대화 단위), `user_id`(임시 상수/입력값) 관리.

### 검증
- 일반 질문 입력 → 토큰이 한 글자씩 실시간으로 누적 렌더된다.
- 새로고침 후 동일 `thread_id`로 대화 맥락이 이어지는지(단기 기억) 확인.

### 커밋
`feat(frontend): streaming chat ui with usechat + ai elements`

---

## Phase 3 — 커스텀 data part 처리 (욕설 차단 + 환불 본인확인) ⚠️

**목표**: Phase 1에서 만든 `data-blocked` / `data-confirmation` 파트를 UI에서 처리한다. 이 프로젝트 고유의 도메인 흐름이라 가장 까다로운 단계.

### 작업
1. **`data-blocked`**: `useChat`의 data parts(`message.parts` 중 `data-blocked`)를 감지 → 차단 안내 메시지를 말풍선/배너로 표시.
2. **`data-confirmation`** (환불 본인확인):
   - AI Elements **`Confirmation`** 컴포넌트로 "환불 신청을 진행할까요?"(tool/args 표시) 렌더.
   - **승인/취소 → `POST /chat/confirm`** 호출(`{ thread_id, decision: "approve"|"reject", user_id }`). 이건 `useChat` 스트림이 아니라 별도 fetch.
   - 응답(`status: "submitted"|"cancelled"`)을 채팅에 후속 메시지로 반영.
3. **상태 관리**: `data-confirmation`에서 받은 `thread_id`를 confirm 호출에 그대로 사용. confirm 이후 다시 채팅 흐름 복귀.

> 참고: `args.user_id`를 클라이언트가 다시 보내는 알려진 한계는 백엔드와 동일하게 유지(학습용).

### 검증
- 욕설 입력 → 차단 메시지 표시(모델 호출 없이 단락).
- "환불해줘 ORD-123" 류 입력 → `Confirmation` UI 표시 →
  - 승인 → "신청 접수(submitted)" 반영
  - 취소 → "취소(cancelled)" 반영
- 승인 시 백엔드 `GET /pending`에 신청이 쌓이는지 교차 확인(Phase 5와 연결).

### 커밋
`feat(frontend): handle blocked + refund confirmation data parts`

---

## Phase 4 — 관리자 문서 업로드 화면

**목표**: PDF/TXT 업로드 → RAG 인덱싱, 업로드된 문서 목록 표시. (스트리밍 없음 — 단순 폼.)

### 작업
1. **`app/admin/documents/page.tsx`**.
2. 파일 선택 + 업로드 폼 → `POST /upload` (multipart/form-data).
3. `GET /documents` → 업로드된 문서 목록 테이블.
4. 업로드 진행/성공/실패 상태 표시(shadcn `Toast`/`Button` 활용).

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
프론트엔드도 동일하게 Phase별 학습 가이드를 남길지는 진행하며 결정한다.

---

## 진행 체크리스트

- [x] Phase 0 — 셋업
- [ ] Phase 1 — 백엔드 프로토콜 변환 ⚠️
- [ ] Phase 2 — 채팅 스트리밍 UI
- [ ] Phase 3 — 차단 + 환불 확인 data part ⚠️
- [ ] Phase 4 — 문서 업로드
- [ ] Phase 5 — 환불 승인 큐
- [ ] Phase 6 — 내 환불 조회
- [ ] Phase 7 — 마무리(선택)
