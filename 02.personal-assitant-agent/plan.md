# 프로젝트 2. AI 개인 비서 에이전트 (이메일/캘린더 자동화)

> Gmail, Google Calendar와 연동해 이메일 분류·답장 초안 작성, 일정 관리, 할 일 자동 추출을 수행하는 개인 비서.
> Multi-Tool Agent + Human-in-the-loop + 실제 외부 API(OAuth2) 연동을 결합한 풀스택 AI 자동화 에이전트.

> **구조 원칙**: 프로젝트 1(`customer-support-agent`)의 실제 코드 컨벤션을 그대로 따른다.
> - 라우트는 `routers/`(APIRouter 그룹화), 요청·응답 Pydantic 모델은 `models/`로 분리한다.
> - 에이전트 컨텍스트는 `AgentContext` dataclass, Tool은 `ToolRuntime[AgentContext]`로 접근한다.
> - 미들웨어는 `create_agent(middleware=[...])`에 순서대로 전달한다.
> - **모든 코드는 각 라이브러리의 공식 문서 패턴만 사용한다** (deprecated 금지, `langchain-community` 미사용). 루트 `CLAUDE.md`의 "Official Documentation Only" 규칙을 따른다.

---

## 1. 최종 목표 (완성 시 동작)

1. 사용자가 구글 계정으로 OAuth2 로그인한다. (Gmail·Calendar 권한 위임)
2. 사용자가 "오늘 안 읽은 메일 정리해줘" 같은 자연어 요청을 입력한다.
3. 에이전트가 복잡한 요청을 TodoList Middleware로 단계별 분해한다.
4. 필요한 Tool(메일 읽기/쓰기, 캘린더 조회/생성, 웹 검색)을 스스로 선택해 호출한다.
5. 각 이메일을 `EmailAnalysis` 스키마(의도·감정·요약·우선순위)로 구조화 파싱한다.
6. 답장 초안을 작성하되, **이메일 발송·일정 생성은 반드시 사용자 본인 확인 후 실행**(Human-in-the-loop: interrupt/resume)한다.
7. 개인정보(메일 주소, 전화번호 등)는 Before/After Guardrail로 마스킹·검증한다.
8. "이 사람한테는 짧게 답해", "회의는 오전 선호" 같은 선호도는 Long-term Memory로 유지된다.

---

## 2. 기술 스택

| 영역 | 기술 |
| :--- | :--- |
| **LLM** | OpenAI GPT-4o (메인), GPT-4o-mini (분류·Guardrail 감시자) |
| **Agent 프레임워크** | LangChain (`create_agent` + middleware) |
| **외부 API** | Gmail API, Google Calendar API (google-api-python-client) |
| **로그인 인증** | NextAuth(Auth.js v5) Google Provider — 프론트가 OAuth2 전담, 세션 전략 `jwt` |
| **API 인증** | 앱 전용 서명 JWT(HS256, 공유 `APP_JWT_SECRET`) → FastAPI가 `pyjwt`로 검증 |
| **구글 토큰 갱신** | NextAuth `@auth/pg-adapter`가 `accounts`에 저장 → FastAPI가 읽어 `google-auth`로 갱신·호출 |
| **웹 검색** | Tavily Search API |
| **데이터 저장소** | PostgreSQL (NextAuth 인증 테이블 `users`/`accounts`/`sessions` + 대화 맥락 + 선호도 통합) |
| **백엔드** | FastAPI + Python (APIRouter / Pydantic / Depends / lifespan) |
| **프론트엔드** | Next.js 15 (App Router) + Tailwind CSS + NextAuth(Auth.js v5) |
| **배포 - 백엔드** | AWS EC2 + RDS PostgreSQL |
| **배포 - 프론트엔드** | Vercel |
| **모니터링** | LangSmith + CloudWatch |
| **CI/CD** | GitHub Actions |

> 프로젝트 1과 달리 RAG가 핵심이 아니므로 pgvector는 선택 사항(이메일 의미 검색을 붙일 경우에만 활성화). 기본은 일반 PostgreSQL 테이블로 토큰·메모리를 관리한다.

---

## 3. 프로젝트 폴더 구조

> 프로젝트 1의 실제 구조와 동일한 컨벤션: 라우트=`routers/`, API 모델=`models/`, 에이전트 로직=`agent/`. 외부 연동(`integrations/`)과 DB(`db/`)만 이 프로젝트 고유로 추가된다.

```
personal-assistant-agent/
├── backend/
│   ├── main.py                  # FastAPI 진입점 (lifespan + CORS + 라우터 등록) ※SessionMiddleware 불필요(OAuth는 프론트)
│   ├── config.py                # pydantic-settings (DATABASE_URL, APP_JWT_SECRET 등)
│   ├── security.py              # 앱 JWT 검증 + get_current_user 의존성 (Depends)
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── agent.py             # create_agent 설정 (middleware 순서: inject_memory → HITL → PII)
│   │   ├── tools.py             # Gmail/Calendar/웹검색 + 메모리 Tool (ToolRuntime[AgentContext])
│   │   ├── schemas.py           # EmailAnalysis 등 LLM 구조화 출력 스키마 (Pydantic)
│   │   ├── middleware.py        # inject_memory(@wrap_model_call async), Guardrail 헬퍼, SYSTEM_PROMPT
│   │   ├── context.py           # AgentContext dataclass (user_id, email)
│   │   └── approval_store.py    # (선택) 발송/일정 처리 이력 감사 로그 저장소
│   ├── integrations/
│   │   ├── __init__.py
│   │   ├── gmail.py             # Gmail API 래퍼 (목록/읽기/초안/발송)
│   │   ├── calendar.py          # Calendar API 래퍼 (조회/생성)
│   │   └── google_auth.py      # accounts의 refresh_token 복원 + access_token 갱신 (google-auth) ※OAuth 플로우는 프론트 NextAuth 담당
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py            # NextAuth 소유 users/accounts 읽기 매핑 + 선호도 테이블 (인증 테이블 create_all 금지)
│   │   └── session.py           # DB 세션 (Depends로 주입)
│   ├── models/                  # ← 요청·응답 Pydantic 모델 (프로젝트 1의 models/ 컨벤션과 일치)
│   │   ├── __init__.py
│   │   ├── chat.py              # ChatRequest, ConfirmRequest
│   │   └── auth.py              # 현재 사용자(/auth/me) 응답 모델
│   ├── routers/                 # ← 기존 api/ 를 routers/ 로 변경 (APIRouter 그룹화)
│   │   ├── __init__.py
│   │   ├── auth.py              # GET /auth/me (Bearer 앱 JWT 검증 → 현재 사용자) ※login/callback 없음(NextAuth 담당)
│   │   ├── chat.py              # POST /chat, POST /chat/confirm
│   │   └── approval.py          # (선택) GET /pending — 처리 이력 조회용
│   └── requirements.txt
├── frontend/
│   ├── auth.ts                  # NextAuth(Auth.js v5) 설정: Google Provider + pg-adapter + callbacks(앱 JWT 발급), session.strategy="jwt"
│   ├── middleware.ts            # 보호 라우트 접근 제어
│   ├── app/
│   │   ├── api/auth/[...nextauth]/route.ts  # NextAuth 핸들러 (로그인/콜백/세션)
│   │   ├── page.tsx             # 채팅 + 비서 메인 화면 (발송 전 인라인 승인 UI 포함)
│   │   └── login/page.tsx       # signIn("google") 구글 로그인 화면
│   ├── lib/
│   │   └── api.ts               # fetch 래퍼 (Authorization: Bearer <앱 JWT> 자동 첨부)
│   └── ...
└── README.md
```

> **변경 요약 (기존 plan 대비)**
> - `api/` → `routers/` : 프로젝트 1의 실제 컨벤션(APIRouter 그룹화)과 일치.
> - `models/` 디렉터리 신설 : 요청·응답 Pydantic 모델을 라우터에서 분리(프로젝트 1과 동일).
> - `Context` → `AgentContext` : 클래스명 통일(`ToolRuntime[AgentContext]`, `context_schema=AgentContext`).
> - `approve.py`(관리자 승인) 제거 → `chat.py`의 `POST /chat/confirm`(본인 확인)으로 대체. 이유는 §5 Phase 5 참고.
> - **인증을 NextAuth(프론트)로 이동** : 백엔드 `GET /auth/login`·`/auth/callback` 제거. OAuth2 플로우는 NextAuth Google Provider가 전담하고, 구글 `refresh_token`은 `@auth/pg-adapter`가 공유 Postgres `accounts`에 저장. **인증 테이블(`users`/`accounts`/`sessions`)은 NextAuth가 소유·생성**하므로 백엔드는 읽기만 하고 `create_all` 하지 않는다.
> - **API 인증은 앱 JWT** : NextAuth가 발급한 서명 JWT(HS256, `sub`=`users.id`)를 프론트가 `Authorization: Bearer`로 전달 → FastAPI가 `pyjwt`로 검증(`get_current_user`). 기존 `?email=` 식별 제거.
> - `integrations/oauth.py` → `google_auth.py` : OAuth 플로우 코드 삭제, **구글 토큰 갱신은 백엔드가 전담**(`accounts`의 refresh_token 복원 + access_token 갱신). NextAuth는 최초 1회 캡처만 담당해 이중 갱신 레이스를 피한다.

---

## 4. 시스템 아키텍처 (데이터 흐름)

### 4.1 인증 흐름 (NextAuth + 앱 JWT)

OAuth2 플로우는 **프론트의 NextAuth**가 전담한다. 백엔드는 NextAuth가 발급한 앱 JWT를 검증하고, `accounts`에 저장된 구글 `refresh_token`을 읽어 Gmail/Calendar를 호출한다.

```
[최초 1회 — 로그인 & 권한 위임]
구글 로그인 클릭 (프론트)
  ↓
NextAuth signIn("google") → 구글 동의 화면
   scope: openid email profile + gmail.modify + gmail.send + calendar
   access_type=offline, prompt=consent  ← refresh_token 수령 필수
  ↓
사용자 동의 → /api/auth/callback/google (NextAuth가 code→token 교환)
  ↓
@auth/pg-adapter 가 공유 Postgres에 저장
   users(id, email, name) / accounts(refresh_token, access_token, expires_at, providerAccountId=구글 sub)
  ↓
session.strategy="jwt" → jwt 콜백에서 앱 JWT(HS256, sub=users.id) 발급해 세션에 노출

[이후 매 API 요청]
프론트 → FastAPI:  Authorization: Bearer <앱 JWT>
  ↓
FastAPI get_current_user: APP_JWT_SECRET 로 pyjwt 검증 → users.id 추출
  ↓
accounts 에서 해당 사용자 refresh_token 읽기
  ↓
google-auth로 access_token 갱신(만료 시) → Gmail/Calendar 호출
```

> **설계 못 박기 (advisor 점검 반영)**
> - **adapter 사용 시 `session.strategy`를 반드시 `"jwt"`로 명시**한다. adapter를 붙이면 기본값이 `"database"`가 되고, 그러면 `jwt` 콜백이 실행되지 않아 앱 JWT를 만들 수 없다. `jwt` 전략 + adapter 조합이면 `jwt` 콜백도 돌고, `linkAccount`로 구글 토큰도 `accounts`에 저장돼 양쪽을 모두 얻는다.
> - **구글 access_token 갱신은 백엔드가 전담**한다. NextAuth는 최초 1회 캡처만, 이후 갱신은 FastAPI가 `refresh_token`으로 수행 — 양쪽이 동시에 갱신하면 토큰 회전 레이스가 난다.
> - **앱 JWT는 암호화가 아닌 서명(HS256) 토큰**이다. NextAuth 기본 세션 JWT는 JWE(암호화)라 `pyjwt`로 직접 검증할 수 없으므로, 검증 가능한 별도 서명 JWT를 발급해 백엔드에 전달한다.
> - **인증 테이블 스키마는 NextAuth가 소유**한다. 백엔드는 `users`/`accounts`를 읽기만 하고 생성(`create_all`)하지 않는다.
> - **토큰 보관 보안(학습 단계 단순화)**: `@auth/pg-adapter`는 `accounts.refresh_token`을 평문 저장한다. 학습 단계라 그대로 두되, 실서비스에서는 컬럼 암호화(pgcrypto)나 암호화 커스텀 adapter를 적용한다.

### 4.2 사용자 요청 처리 흐름 (런타임)

```
사용자 요청 입력 ("오늘 메일 정리하고 중요한 건 답장 초안 써줘")
  ↓
Before Agent Guardrail (욕설/PII 입력 차단)
  ↓
TodoList Middleware (복잡 요청을 단계로 분해)
  ├── 1) 안 읽은 메일 목록 조회
  ├── 2) 각 메일 EmailAnalysis로 분석
  └── 3) 중요 메일에 답장 초안 작성
  ↓
에이전트 추론 + Multi-Tool 호출 (agent.ainvoke)
  ├── 정보 조회 (읽기 전용) → 즉시 실행
  │     ├── list_emails / read_email
  │     ├── list_calendar_events
  │     └── web_search (외부 사실 확인)
  └── 부수효과 작업 (쓰기) → HumanInTheLoopMiddleware가 발송 직전 일시정지(interrupt)
        ├── send_email
        └── create_calendar_event
  ↓
[interrupt 발생 시]
  result.get("__interrupt__") 감지  ← result["messages"][-1] 접근보다 먼저 분기
  → action_requests[0]["args"]에서 발송 내용 추출
  → status: "confirmation_required" 로 사용자에게 미리보기 반환
  → 사용자가 POST /chat/confirm {thread_id, decision} 호출
  → Command(resume={"decisions": [{"type": decision}]}) 로 에이전트 재개
       (approve=실제 발송, edit=수정 후 발송, reject=건너뜀)
  ↓
After Agent Guardrail (할루시네이션·부적절 발송 검증, GPT-4o-mini 감시자)
  ↓
PII 마스킹 (메일 주소, 전화번호)
  ↓
최종 응답 반환 (status: "completed")
```

> **핵심**: 이 프로젝트의 승인자는 "사용자 본인"이다. 사용자는 채팅창 앞에 있으므로
> 관리자 비동기 큐가 아니라 **동기 interrupt/resume** 한 흐름이면 충분하다.
> (프로젝트 1의 "사용자 본인 확인" 절반과 동일한 메커니즘. 거기서 추가로 있던
> "관리자 승인(비동기 refund_store)" 단계는 이 프로젝트엔 해당 사항이 없다.)

---

## 5. 구현 단계별 계획

### Phase 1. NextAuth 구글 로그인 + 공유 토큰 DB + 백엔드 JWT 검증

**목표**: NextAuth로 구글 로그인 → 구글 토큰을 공유 Postgres에 저장 → 백엔드가 앱 JWT를 검증하고 그 토큰으로 실제 Gmail 호출까지 완성

**프론트 (NextAuth / Auth.js v5)**
- [ ] Google Cloud Console에서 OAuth 동의 화면 + 웹 클라이언트 ID 생성
  - 스코프: `openid email profile`, `gmail.modify`, `gmail.send`, `calendar`
  - **승인된 리디렉션 URI**: `http://localhost:3000/api/auth/callback/google` (NextAuth 콜백)
- [ ] `auth.ts` 작성: Google Provider + `@auth/pg-adapter`(공유 Postgres) + `session.strategy="jwt"`
  - `authorization.params`: `access_type=offline`, `prompt=consent` (refresh_token 수령)
  - `callbacks.jwt`/`callbacks.session`: 앱 JWT(HS256, `sub`=`users.id`)를 `APP_JWT_SECRET`로 서명해 세션에 노출
- [ ] `app/api/auth/[...nextauth]/route.ts` + `login/page.tsx`(`signIn("google")`)
- [ ] `lib/api.ts`: FastAPI 호출 시 `Authorization: Bearer <앱 JWT>` 자동 첨부

**백엔드 (FastAPI)**
- [ ] `config.py`(pydantic-settings): `DATABASE_URL`, `APP_JWT_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`(토큰 갱신용)
- [ ] `db/models.py`: NextAuth가 만든 `users`/`accounts`에 대한 **읽기 매핑** (인증 테이블은 `create_all` 금지 — NextAuth가 소유) + 세션 주입(`db/session.py`, `Depends`)
- [ ] `security.py`: `get_current_user` 의존성 — `APP_JWT_SECRET`로 `pyjwt` 검증 → `users.id` 추출
- [ ] `integrations/google_auth.py`: `accounts`의 refresh_token 복원 → `google-auth`로 access_token 갱신(백엔드 전담) → `build("gmail",...)`
- [ ] `routers/auth.py`: `GET /auth/me` — Bearer JWT 검증 후 저장된 토큰으로 Gmail 프로필 호출(E2E 검증)
- **검증**:
  - 구글 로그인 후 `accounts`에 refresh_token 저장 확인
  - 프론트가 `Bearer <앱 JWT>`로 `/auth/me` 호출 → 실제 Gmail 프로필 반환
  - access_token 만료를 강제해도 백엔드가 자동 갱신 후 정상 응답

---

### Phase 2. Gmail / Calendar Tool 연결

**목표**: 에이전트가 메일·캘린더를 실제로 조회/조작

- [ ] Gmail 래퍼 구현 (`integrations/gmail.py`)
  - `list_emails`, `read_email`, `create_draft`, `send_email`
- [ ] Calendar 래퍼 구현 (`integrations/calendar.py`)
  - `list_calendar_events`, `create_calendar_event`
- [ ] Tool로 래핑 (`agent/tools.py`) — 사용자별 토큰 접근은 `ToolRuntime[AgentContext]` 사용
  ```python
  from langchain.tools import tool, ToolRuntime
  from agent.context import AgentContext

  @tool
  def list_emails(query: str, runtime: ToolRuntime[AgentContext]) -> str:
      """Gmail에서 조건에 맞는 이메일 목록을 조회합니다. (예: is:unread)"""
      user_id = runtime.context.user_id
      ...
  ```
- [ ] 웹 검색 Tool 추가 (Tavily)
- [ ] `create_agent` 기본 설정 (`agent/agent.py`) — `ChatOpenAI(model="gpt-4o", temperature=0, streaming=True)`
- **검증**: "안 읽은 메일 3개 제목 알려줘" 요청 시 실제 Gmail에서 조회되는지 확인

---

### Phase 3. Structured Output (EmailAnalysis)

**목표**: 이메일을 구조화 스키마로 일관 파싱

- [ ] `EmailAnalysis` 스키마 정의 (`agent/schemas.py`)
  ```python
  class EmailAnalysis(BaseModel):
      intent: Literal["문의", "회의요청", "스팸", "업무지시", "기타"]
      sentiment: Literal["긍정", "중립", "부정"]
      summary: str
      priority: Literal["높음", "중간", "낮음"]
      action_required: bool
  ```
- [ ] 구조화 출력 강제 (LangChain 공식 structured output / `response_format`)
- [ ] 분류는 비용 절감 위해 GPT-4o-mini 사용
- **검증**: 임의 메일 입력 시 항상 스키마 형태로 분석 결과 반환 확인

---

### Phase 4. TodoList Middleware + Memory

**목표**: 복잡 요청 자동 분해 + 선호도 기억

- [ ] TodoList Middleware 적용
  - "메일 정리하고 답장까지" → 단계별 todo로 분해/추적
- [ ] Short-term Memory: `InMemorySaver`(개발) → `PostgresSaver`(배포)
- [ ] Long-term Memory: `InMemoryStore`(개발) → Redis/Postgres Store(배포)
  - `checkpointer`·`store`는 반드시 **모듈 레벨 싱글톤**으로 생성 (요청마다 새로 만들면 상태 유실)
- [ ] `save_preference` / `get_preference` Tool 구현 — store 접근은 `ToolRuntime[AgentContext]`, 네임스페이스 `("user_preferences", user_id)`
  ```python
  @tool
  def save_preference(preference: str, runtime: ToolRuntime[AgentContext]) -> str:
      """사용자의 답장 스타일/일정 선호도를 장기 기억에 저장합니다."""
  ```
- [ ] AgentContext dataclass 정의 (`agent/context.py`)
  ```python
  @dataclass
  class AgentContext:
      user_id: str
      email: str
  ```
  - `create_agent(context_schema=AgentContext, ...)` + `agent.ainvoke(..., context=AgentContext(...))`로 전달
- [ ] `inject_memory` Middleware: 선호도를 system prompt에 자동 주입
  - **반드시 `@wrap_model_call` + `async def` + `await handler(request)`** 로 작성.
    chat.py가 `ainvoke`로 실행하므로 sync로 정의하면 `awrap_model_call`이 `NotImplementedError`를 발생시킨다.
  - `request.override(system_prompt=base + 선호도)` 로 주입하되 **base 프롬프트 보존 필수**.
- **검증**: "이 사람한텐 짧게 답해" 저장 후 다음 답장 초안이 실제로 짧아지는지 확인

---

### Phase 5. Human-in-the-loop (발송/일정 사용자 본인 확인)

**목표**: 부수효과 작업(메일 발송, 일정 생성)은 실행 직전 일시정지 → 사용자 본인 확인 후에만 실행

> **설계 핵심 — 승인자는 "사용자 본인" 한 명**: 프로젝트 1은 "사용자 본인 확인(동기) +
> 관리자 승인(비동기)"의 두 사람 구조였지만, 이 프로젝트의 발송 승인자는 사용자 자신이다.
> 사용자는 채팅창 앞에 있으므로 **동기 interrupt/resume** 한 흐름이면 충분하고,
> 관리자용 비동기 큐(`/pending` + `/approve` + 별도 store)는 필요 없다.

- [ ] `HumanInTheLoopMiddleware` 설정 (`agent/agent.py`) — 미들웨어 순서 `[inject_memory, HITL, PII]`
  ```python
  middleware=[
      inject_memory,
      HumanInTheLoopMiddleware(
          interrupt_on={
              "send_email": {"allowed_decisions": ["approve", "edit", "reject"]},
              "create_calendar_event": {"allowed_decisions": ["approve", "reject"]},
          },
      ),
      PIIMiddleware(...),
  ]
  ```
- [ ] 요청·응답 모델 정의 (`models/chat.py`): `ChatRequest`, `ConfirmRequest {thread_id, decision, edited_content?, user_id}`
- [ ] 본인 확인 흐름 (`routers/chat.py`)
  - `POST /chat`: `result.get("__interrupt__")`로 일시정지 감지 (**`result["messages"][-1]` 접근 전에 분기** — interrupt 시 마지막 메시지는 빈 AIMessage)
    → `action_requests[0]["args"]`에서 발송 내용 추출 → `status: "confirmation_required"` + `thread_id` 반환
    (interrupt 상태는 checkpointer가 thread_id로 보관하므로 별도 큐에 저장하지 않는다)
  - `POST /chat/confirm`: `Command(resume={"decisions": [{"type": decision}]})`로 에이전트 재개
    (approve=실제 발송, edit=`edited_content`로 수정 후 발송, reject=건너뜀)
- [ ] (선택) `approval_store.py` — 실제 발송/생성 이력을 감사 로그로 남기고 싶을 때만 추가. 승인 흐름 자체에는 불필요.
- **검증**:
  - "김부장님께 답장 보내줘" → `confirmation_required` (아직 발송 안 됨)
  - `POST /chat/confirm {decision: approve}` → 실제 발송 + `completed`
  - `POST /chat/confirm {decision: edit, edited_content}` → 수정본 발송
  - `POST /chat/confirm {decision: reject}` → 미발송 확인

---

### Phase 6. Guardrail (PII + 부적절 발송 방지)

**목표**: 안전한 외부 발송 보장

- [ ] PII Masking: `langchain.agents.middleware.PIIMiddleware` 공식 내장 미들웨어 사용
  - 이메일: 커스텀 regex detector → `[REDACTED_EMAIL]`
  - 전화번호: 커스텀 regex detector → `mask`
  - `apply_to_input=True, apply_to_output=True`로 에이전트 내부 입출력 모두 처리
- [ ] Before Agent Guardrail: `is_blocked_input()` — 키워드 기반 욕설/부적절 입력 차단. 탐지 시 `agent.ainvoke()` 호출 없이 즉시 거절 반환.
- [ ] After Agent Guardrail: `check_hallucination()` — 감시자 모델(GPT-4o-mini)이 답장 초안의 톤/사실/PII 점검
  - 위험 감지 시 초안 교정 또는 발송 차단
- [ ] chat.py 파이프라인: 입력 차단 체크 → 에이전트 실행(내부 PIIMiddleware 자동 실행) → 발송 직전 검증
- **검증**: 부적절한 표현이 포함된 초안 작성 시 교정/차단되는지, 메일주소/전화번호 마스킹되는지 확인

---

### Phase 7. 프론트엔드 + LangSmith 연동

**목표**: 배포 가능한 UI + 모니터링

- [ ] **Agent 초기화 패턴** (`agent/agent.py` + `main.py`)
  - 기준(프로젝트 1 실제 코드): 모듈 레벨 싱글톤 `_agent = create_agent(...)` + `def get_agent(): return _agent`.
    `checkpointer`/`store`도 같은 모듈에서 싱글톤으로 생성. `routers/chat.py`는 `from agent.agent import get_agent`로 사용.
  - `main.py`의 `lifespan`은 시작 시 초기화 작업(예: 토큰 워밍업, 인덱스 빌드)에 사용.
  - (선택 개선) 테스트 시 Mock 교체를 쉽게 하려면 `app.state.agent` + `Depends(get_agent)`로 전환 가능.
    프로젝트 1 plan에도 권장안으로 적혀 있으나 실제 코드는 아직 모듈 싱글톤을 사용한다.
- [ ] 구글 로그인 화면 (`frontend/app/login/page.tsx`)
- [ ] 채팅/비서 메인 화면 (`frontend/app/page.tsx`)
  - 스트리밍 응답 (SSE, `sse-starlette` + `agent.astream(stream_mode="messages")`)
  - 메일 분석 결과 카드(의도·우선순위) 표시
  - **발송 전 인라인 승인 UI**: `confirmation_required` 응답 시 초안 미리보기 + [승인/수정/거절] 버튼 → `POST /chat/confirm` 호출 (별도 폴링 화면 불필요)
- [ ] LangSmith 연동 (환경변수만으로 자동 추적, 코드 변경 불필요)
  - Tool 호출 추적, Human-in-the-loop 발동 횟수 모니터링
- **검증**: 로그인 → 메일 정리 → 답장 인라인 승인 → 실제 발송 전체 플로우 E2E 테스트

---

### Phase 8. AWS 인프라 구축 (EC2 + RDS)

**목표**: EC2에 FastAPI 배포, RDS PostgreSQL 연동, OAuth 콜백 HTTPS 처리

#### 8-1. AWS 사전 준비

- [ ] AWS 계정 + IAM 사용자 생성 (EC2, RDS, VPC, CloudWatch 권한)

#### 8-2. VPC 및 네트워크 설정

- [ ] 기본 VPC 사용 또는 신규 생성 (퍼블릭 + 프라이빗 서브넷)
- [ ] Internet Gateway 연결, Route Table에 `0.0.0.0/0 → IGW` 추가

#### 8-3. 보안그룹 생성

- [ ] **FastAPI 보안그룹** (EC2용)
  ```
  Inbound:
    - HTTP (80): 0.0.0.0/0
    - HTTPS (443): 0.0.0.0/0   ← OAuth 콜백은 HTTPS 필수
    - SSH (22): Your_IP/32
  Outbound: 모든 트래픽 허용 (구글 API 호출)
  ```
- [ ] **RDS 보안그룹**
  ```
  Inbound:
    - PostgreSQL (5432): FastAPI 보안그룹만 허용
  ```

#### 8-4. RDS PostgreSQL 인스턴스 생성

- [ ] PostgreSQL 15+ 생성
  ```
  인스턴스 클래스: t3.micro (프리티어)
  스토리지: 20GB
  DB 이름: assistant_db
  퍼블릭 액세스: OFF
  백업: 7일 / Multi-AZ: OFF
  ```
- [ ] (이메일 의미 검색을 붙일 경우에만) pgvector extension 활성화
  ```sql
  CREATE EXTENSION IF NOT EXISTS vector;
  ```

#### 8-5. EC2 인스턴스 생성

- [ ] Ubuntu 22.04 LTS, t3.micro, RDS와 동일 VPC, 퍼블릭 서브넷
- [ ] 키페어 생성 (`chmod 400 your-key.pem`)
- [ ] Elastic IP 할당 (고정 IP → 구글 OAuth 리다이렉트 URI 등록에 필요)

#### 8-6. 도메인 + HTTPS 설정

- [ ] 백엔드 도메인 연결 (Route 53 또는 외부 도메인) — Bearer 토큰을 TLS로 보호
- [ ] Nginx 리버스 프록시 + Let's Encrypt(certbot)로 HTTPS 인증서 발급 (`https://api.your-domain.com`)
- [ ] **OAuth 콜백은 프론트(NextAuth)** : Google Cloud Console의 **승인된 리디렉션 URI**에 Vercel 프론트 도메인 등록
  ```
  https://your-app.vercel.app/api/auth/callback/google
  ```
  (Vercel은 기본 HTTPS이므로 별도 인증서 작업 불필요)

#### 8-7. EC2에 FastAPI 배포

- [ ] SSH 접속 후 패키지 설치 (`python3.11`, `git`, `nginx`)
- [ ] 프로젝트 클론 및 `pip install -r requirements.txt`
- [ ] 환경변수 설정 (백엔드도 구글 토큰 **갱신**을 위해 client_id/secret 필요 — 갱신 요청에 클라이언트 자격증명이 들어간다)
  ```bash
  export OPENAI_API_KEY="sk-..."
  export DATABASE_URL="postgresql+psycopg://postgres:password@rds-endpoint:5432/assistant_db"
  export APP_JWT_SECRET="..."         # NextAuth와 공유 (JWT 서명/검증 동일 키)
  export GOOGLE_CLIENT_ID="..."       # access_token 갱신 시 필요
  export GOOGLE_CLIENT_SECRET="..."   # access_token 갱신 시 필요
  export TAVILY_API_KEY="..."
  export LANGSMITH_API_KEY="ls_..."
  ```

#### 8-8. systemd로 자동 실행 설정

- [ ] `/etc/systemd/system/fastapi.service` 생성 (Uvicorn `--port 8000`, Nginx가 443 → 8000 프록시)
- [ ] `sudo systemctl enable --now fastapi`

#### 8-9. GitHub Actions CI/CD

- [ ] `.github/workflows/deploy.yml` (push 시 EC2 SSH → git pull → 의존성 설치 → 서비스 재시작)
- [ ] GitHub Secrets: `EC2_HOST`, `EC2_KEY`

#### 8-10. 프론트엔드 Vercel 배포 (NextAuth)

- [ ] 환경변수
  ```bash
  NEXT_PUBLIC_API_URL=https://api.your-domain.com
  AUTH_SECRET=...                 # NextAuth 세션 암호화 키
  AUTH_GOOGLE_ID=...              # 구글 OAuth 클라이언트 ID
  AUTH_GOOGLE_SECRET=...          # 구글 OAuth 시크릿
  APP_JWT_SECRET=...              # 백엔드와 공유 (앱 JWT 서명)
  DATABASE_URL=postgresql://...   # @auth/pg-adapter용 (백엔드와 동일 RDS)
  ```
- [ ] Google Console 승인된 리디렉션 URI에 `https://your-app.vercel.app/api/auth/callback/google` 등록
- [ ] `vercel --prod`

#### 8-11. CloudWatch 모니터링

- [ ] EC2 CPU/네트워크, RDS 스토리지 알람 설정

#### 8-12. 검증 및 테스트

- [ ] Vercel 프론트에서 NextAuth 구글 로그인 → `accounts`에 토큰 저장 → 앱 JWT 발급 확인
- [ ] 메일 조회 → 분석 → 답장 초안 → 본인 확인 → 실제 발송 E2E
- [ ] Vercel 프론트 → EC2 백엔드 통신 확인

---

## 예상 월 비용 (AWS)

| 항목 | 예상 가격 |
|:---|:---|
| **EC2 t3.micro (프리티어)** | 무료 (12개월) |
| **RDS t3.micro (프리티어)** | 무료 (12개월) |
| **Elastic IP** | 무료 (사용 중) |
| **도메인** | $1~2/월 (연 $12~15) |
| **CloudWatch** | 무료 (1M 요청까지) |
| **합계** | **약 $1~5/월** (프리티어) |

프리티어 만료 후:
| 항목 | 예상 가격 |
|:---|:---|
| **EC2 t3.small** | $10/월 |
| **RDS t3.small** | $20/월 |
| **기타(도메인 등)** | $5/월 |
| **합계** | **~$35/월** |

> Gmail/Calendar API와 Google OAuth는 일반 사용량 내에서 무료. Tavily는 무료 티어로 시작 가능.

---

## 6. API 설계

> 로그인/콜백(`/api/auth/*`)은 **프론트 NextAuth가 처리**하므로 백엔드 엔드포인트가 아니다.
> 아래 백엔드 엔드포인트는 모두 `Authorization: Bearer <앱 JWT>`를 요구한다(`get_current_user`).

| Method | Endpoint | 설명 |
| :--- | :--- | :--- |
| `GET` | `/auth/me` | 앱 JWT 검증 → 현재 사용자 + 저장된 토큰으로 Gmail 프로필(E2E 검증) |
| `POST` | `/chat` | 사용자 요청 전송 → 에이전트 응답 (발송 시 `confirmation_required`) |
| `POST` | `/chat/confirm` | 사용자 본인 확인 후 에이전트 재개 (`Command(resume=...)`) |
| `GET` | `/pending` | (선택) 발송/일정 처리 이력 조회 — 감사 로그용 |

> 기존 plan의 `GET /auth/login`·`/auth/callback`(백엔드 OAuth)은 제거 → NextAuth로 이동.
> `GET /pending` + `POST /approve`(관리자 비동기 승인)도 제거 — 발송 승인자가 사용자 본인이므로 `POST /chat/confirm`(동기 재개) 한 엔드포인트로 충분하다.

### POST /chat 요청/응답 예시

```json
// Request  (헤더: Authorization: Bearer <앱 JWT> — user_id는 JWT의 sub에서 서버가 도출)
{
  "message": "오늘 안 읽은 메일 정리하고 김부장님 메일엔 답장 초안 써줘",
  "thread_id": "session-abc123"
}

// Response (확인 불필요 - 조회만)
// 프로젝트 1과 동일한 공통 응답 envelope: { success, message, data }
{
  "success": true,
  "message": "Chat completed successfully",
  "data": {
    "response": "안 읽은 메일 3건을 정리했습니다. 1) 회의요청(높음)...",
    "thread_id": "session-abc123",
    "status": "completed"
  }
}

// Response (Human-in-the-loop interrupt - 발송 전 본인 확인 대기)
{
  "success": true,
  "message": "Confirmation required",
  "data": {
    "thread_id": "session-abc123",
    "status": "confirmation_required",
    "confirmation": {
      "tool": "send_email",
      "args": {
        "to": "boss@company.com",
        "subject": "Re: 내일 회의 일정",
        "body": "안녕하세요 부장님, 말씀하신 회의는 ..."
      }
    }
  }
}
```

> 응답은 프로젝트 1 코드처럼 `{ success, message, data }` envelope로 감싼다.
> interrupt 감지 시 `data.confirmation = {tool, args}` 형태로 반환(프로젝트 1 `routers/chat.py`와 동일).

### POST /chat/confirm 요청 예시

```json
// 헤더: Authorization: Bearer <앱 JWT> (user_id는 JWT sub에서 도출)
{
  "thread_id": "session-abc123",
  "decision": "approve",          // "approve" | "edit" | "reject"
  "edited_content": null           // decision="edit"일 때만 수정된 본문
}
```

---

## 7. 핵심 구현 포인트 (면접 대비)

| 질문 | 답변 포인트 |
| :--- | :--- |
| "이 에이전트가 왜 안전한가요?" | 모든 부수효과 작업(메일 발송, 일정 생성)에 `HumanInTheLoopMiddleware`로 interrupt를 강제. 조회는 자동, 쓰기는 반드시 사용자 본인 확인(resume) 후 실행. LLM이 단독으로 외부에 영향을 줄 수 없는 구조 |
| "HITL을 어떻게 구현했나요?" | 도구 안에 `interrupt()`를 직접 쓰지 않고 미들웨어가 선언적으로 제어. `__interrupt__`를 `result["messages"][-1]` 접근 전에 감지해 `confirmation_required` 반환, `Command(resume={"decisions":[{"type": decision}]})`로 재개. interrupt 상태는 checkpointer가 thread_id로 보관 |
| "왜 관리자 승인 큐가 없나요?" | 발송 승인자가 사용자 본인이고 채팅창 앞에 있으므로 동기 interrupt/resume 한 흐름이면 충분. 프로젝트 1처럼 제3자(관리자)가 비동기로 승인하는 경우에만 별도 store + `/approve`가 필요 |
| "로그인/OAuth는 어떻게 처리하나요?" | OAuth2 플로우는 프론트 NextAuth(Auth.js v5) Google Provider가 전담. `access_type=offline`로 받은 구글 refresh_token은 `@auth/pg-adapter`가 공유 Postgres `accounts`에 저장. 백엔드는 이 토큰을 읽어 access_token을 **백엔드가 전담 갱신**(이중 갱신 레이스 방지) |
| "프론트(NextAuth)와 파이썬 백엔드 인증을 어떻게 잇나요?" | NextAuth 기본 세션 토큰은 JWE(암호화)라 `pyjwt`로 검증 불가. 그래서 NextAuth `jwt` 콜백에서 **별도 서명 JWT(HS256, `sub`=`users.id`)** 를 `APP_JWT_SECRET`로 발급해 `Authorization: Bearer`로 전달 → FastAPI가 `pyjwt`로 검증(`get_current_user`). adapter 사용 시 `session.strategy="jwt"`를 명시해야 `jwt` 콜백이 동작 |
| "왜 Structured Output(EmailAnalysis)을 쓰나요?" | 메일 분류 결과를 의도·감정·우선순위 스키마로 강제하면 후속 로직(우선순위 정렬, 자동 라벨링)이 안정적. 자유 텍스트 파싱의 깨짐을 제거 |
| "inject_memory를 왜 async로 작성하나요?" | chat.py가 `ainvoke`로 실행하므로 `@wrap_model_call`을 sync로 정의하면 `awrap_model_call`이 `NotImplementedError`를 발생. 반드시 `async def` + `await handler(request)`, base 프롬프트 보존 |
| "Agent 인스턴스는 어떻게 관리하나요?" | 모듈 레벨 싱글톤(`get_agent()`)으로 생성해 `checkpointer`/`store` 상태를 보존(요청마다 새로 만들면 단기 기억·interrupt 상태 유실). 테스트 용이성이 필요하면 `app.state.agent` + `Depends(get_agent)`로 전환 가능 |
| "비용 최적화는?" | 단순 분류는 GPT-4o-mini, 답장 생성·추론은 GPT-4o로 모델을 분리. Guardrail 감시자도 mini 사용 |
| "PII를 서버에서 처리하는 이유는?" | 클라이언트 필터는 우회 가능. `PIIMiddleware`는 LLM 호출·외부 발송 전에 반드시 실행되어 확실히 보호 |
| "AWS 배포 구조를 설명해 주세요" | EC2에서 FastAPI, RDS에서 PostgreSQL 운영. VPC·보안그룹으로 격리. Nginx + Let's Encrypt로 HTTPS 처리(OAuth 콜백 필수). systemd·GitHub Actions로 배포 자동화 |
| "왜 HTTPS가 필수인가요?" | 구글 OAuth는 보안상 HTTPS 리디렉션 URI만 허용. Nginx 리버스 프록시 + certbot으로 인증서를 발급해 콜백을 안전하게 수신 |

---

## 8. 구현 일정 (예상)

| Phase | 내용 | 예상 기간 |
| :---: | :--- | :---: |
| 1 | NextAuth 구글 로그인 + 공유 토큰 DB + 백엔드 JWT 검증 | 3일 |
| 2 | Gmail / Calendar Tool 연결 | 3일 |
| 3 | Structured Output (EmailAnalysis) | 1일 |
| 4 | TodoList Middleware + Memory | 2일 |
| 5 | Human-in-the-loop (발송 본인 확인) | 2일 |
| 6 | Guardrail (PII + 발송 검증) | 2일 |
| 7 | 프론트엔드 + LangSmith | 3일 |
| 8 | AWS 인프라 구축 (EC2 + RDS + HTTPS) | **4일** |
|   | - VPC/보안그룹 설정 | 1일 |
|   | - RDS + EC2 + 도메인/HTTPS | 1.5일 |
|   | - 배포 + GitHub Actions CI/CD | 1.5일 |
| **합계** | | **약 20일** |

**추가 학습**: NextAuth(Auth.js v5) Google Provider + adapter, 앱 JWT(HS256) 발급/검증, Gmail/Calendar API 스코프, Nginx + Let's Encrypt HTTPS 설정 포함
