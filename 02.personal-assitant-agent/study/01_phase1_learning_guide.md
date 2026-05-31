# Phase 1 학습 가이드 — Google OAuth2 인증

이 가이드는 Phase 1에서 만든 파일들을 **의존성 순서대로** 읽으며, "우리 앱이 사용자 대신 Gmail/캘린더에 접근할 토큰을 받아 안전하게 보관하는 과정"을 이해하도록 구성했습니다.

> **Phase 1의 목표 한 줄**: 사용자의 비밀번호 없이, **제한된 권한의 토큰**을 받아 → **암호화해 DB에 저장** → **만료되면 자동 갱신**까지. (AI 기능은 Phase 2부터)

---

## 0. 먼저: OAuth2가 왜 필요한가 (호텔 카드키 비유)

사용자의 구글 비밀번호를 우리가 직접 받는 건 위험하고, 구글이 막아둡니다. 대신 표준 방식인 **OAuth2**를 씁니다.

```
사용자  = 투숙객
구글    = 호텔 프런트 (열쇠 발급처)
우리 앱 = 벨보이
```

- 투숙객(사용자)이 **프런트(구글)** 에 직접 가서 "이 벨보이가 내 방에 들어가도 됨"을 **동의**
- 프런트는 벨보이에게 **마스터키가 아니라 제한된 카드키(토큰)** 를 발급
- 벨보이(우리 앱)는 **비밀번호를 전혀 모름**. 카드키만 보유

**토큰은 2종류** — 이게 OAuth에서 가장 헷갈리는 부분:

| 토큰 | 비유 | 수명 | 용도 |
|------|------|------|------|
| **access token** | 카드키 | 약 1시간 | 실제로 Gmail/캘린더를 열 때 사용 |
| **refresh token** | 카드키 재발급 쿠폰 | 거의 영구 | access token이 만료되면 새로 발급 |

→ access token이 유출돼도 1시간 뒤 무효화되어 안전. refresh token은 절대 평문 저장 금지.

---

## 학습 흐름도

```
사용자가 "구글 로그인" 클릭
        ↓
[routers/auth.py]  GET /auth/login   → 구글 동의 화면으로 리다이렉트
        ↓ (사용자가 동의)
[routers/auth.py]  GET /auth/callback → 임시 code 수신
        ↓
[integrations/oauth.py]  code → access_token + refresh_token 교환
        ↓
[security.py]  refresh_token 암호화 (Fernet)
        ↓
[db/models.py + session.py]  users 테이블에 저장
        ↓
[routers/auth.py]  GET /auth/me → 저장된 토큰으로 실제 Gmail 호출 (검증)
```

| 파일 | 한 줄 역할 |
|------|-----------|
| `config.py` | `.env`의 비밀값을 타입과 함께 한 곳에서 로딩 |
| `security.py` | refresh_token 암호화/복호화 (Fernet) |
| `db/session.py` | DB 연결 + 요청별 세션(`get_db`) |
| `db/models.py` | `users` 테이블 설계도 |
| `integrations/oauth.py` | 구글과 실제로 대화 (URL 생성/토큰 교환/갱신) |
| `routers/auth.py` | 사용자가 드나드는 문 (`/login`, `/callback`, `/me`) |
| `main.py` | 위 조각들을 조립해 서버로 기동 |

---

## Step 1: `config.py` 읽기 (5분)

### 목표
환경변수(비밀값)를 안전하고 타입 있게 관리하는 방식 이해

### 핵심 개념

**pydantic-settings** — `os.getenv()`를 코드 곳곳에 뿌리는 대신, 한 클래스에 모읍니다.
```python
class Settings(BaseSettings):
    database_url: str          # 필수 (없으면 시작 시 에러)
    google_client_id: str
    token_encryption_key: str
    oauth_redirect_uri: str = "http://localhost:8000/auth/callback"  # 기본값
```

**왜 좋은가**
- 필수 값이 빠지면 **런타임이 아니라 서버 시작 시 즉시** 에러 → 빨리 발견
- `@lru_cache`로 `.env`를 한 번만 읽어 재사용 (FastAPI 공식 권장 패턴)

**`.env` 위치**: `backend/`의 **상위 폴더**(`02.personal-assitant-agent/.env`)에서 읽습니다. (코드와 비밀값 분리)

### 학습 질문
- [ ] 필수 값(타입만 선언)과 선택 값(기본값 있음)의 차이는?
- [ ] `@lru_cache`가 없으면 매 요청마다 무슨 일이 생길까?
- [ ] `extra="ignore"`는 왜 넣었을까? (힌트: 미래 Phase에서 쓸 키)

---

## Step 2: `security.py` 읽기 (5분)

### 목표
refresh_token을 왜, 어떻게 암호화하는지 이해

### 핵심 개념

**Fernet** = 대칭키 암호화. 같은 키로 잠그고(encrypt) 연다(decrypt).
```python
enc = security.encrypt("1//0g...refresh...")  # DB 저장 직전
dec = security.decrypt(enc)                     # API 호출 직전
```

**왜 암호화하나**: refresh_token은 사실상 "영구 출입증". DB가 유출돼도 평문이면 공격자가 사용자의 Gmail에 **무기한** 접근. 암호화하면 키(`TOKEN_ENCRYPTION_KEY`) 없이는 무용지물.

**키 생성**:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 학습 질문
- [ ] access_token은 왜 굳이 암호화하지 않아도 상대적으로 덜 위험할까? (힌트: 수명)
- [ ] `TOKEN_ENCRYPTION_KEY`를 잃어버리면 저장된 토큰은 어떻게 될까?

---

## Step 3: `db/session.py` 읽기 (10분)

### 목표
SQLAlchemy로 DB에 연결하고, 요청마다 안전하게 세션을 열고 닫는 패턴 이해

### 핵심 개념

**3대 구성요소**
```python
engine = create_engine(DATABASE_URL)   # DB로 가는 커넥션 풀 (앱당 1개)
SessionLocal = sessionmaker(bind=engine)  # 요청마다 만들 세션 팩토리
class Base(DeclarativeBase): ...         # 모든 테이블 모델의 부모
```

**`get_db()` — yield 의존성** (FastAPI 공식: di-yield-cleanup)
```python
def get_db():
    db = SessionLocal()
    try:
        yield db        # ← 여기가 엔드포인트로 주입됨
    finally:
        db.close()      # ← 요청이 끝나면(에러가 나도) 반드시 닫힘
```
요청 처리 중 예외가 터져도 `finally`에서 커넥션을 반납 → **누수 방지**.

**커넥션 문자열 주의** (프로젝트 1과 동일):
```
postgresql+psycopg://...   ✅ (psycopg3 드라이버 명시)
postgresql://...           🔴 (psycopg2로 오해 → 오류 가능)
```

**동기(sync)로 쓰는 이유**: psycopg/SQLAlchemy 호출은 블로킹 I/O. 그래서 이걸 쓰는 엔드포인트는 `async def`가 아니라 `def`로 선언해 FastAPI가 threadpool에서 돌립니다 (다음 Step에서 다시 등장).

### 학습 질문
- [ ] engine은 앱당 1개인데 session은 왜 요청마다 새로 만들까?
- [ ] `yield` 대신 `return db`를 쓰면 무엇이 문제일까?
- [ ] `pool_pre_ping=True`는 무엇을 막아줄까? (힌트: 끊긴 커넥션)

---

## Step 4: `db/models.py` 읽기 (5분)

### 목표
토큰을 어떤 표(테이블)에 저장할지 — `users` 단일 테이블 설계 이해

### 핵심 개념

**"표 1개" 설계** (한 사용자 = 한 구글 계정 = 한 토큰셋, 1:1)
```python
class User(Base):
    __tablename__ = "users"
    id: Mapped[int]               # PK
    google_sub: Mapped[str]       # 구글의 변하지 않는 고유 ID (진짜 식별자)
    email: Mapped[str]            # 표시/조회용 (바뀔 수 있음)
    refresh_token_enc: Mapped[str]      # 암호화된 refresh token
    access_token: Mapped[str | None]    # 1시간짜리, 갱신 시 덮어씀
    token_expiry: Mapped[datetime | None]
    created_at / updated_at
```

**왜 email이 아니라 `google_sub`로 사용자를 식별하나**: 이메일은 변경될 수 있지만 `sub`(구글 고유 ID)는 불변. 그래서 upsert 기준은 `google_sub`.

**SQLAlchemy 2.0 스타일**: `Mapped[...]` + `mapped_column(...)`은 최신 공식 표기(타입 힌트 친화적). 구식 `Column(...)` 아님.

**트레이드오프**: 실서비스에서 토큰 이력/다중 제공자(구글+다른 서비스)가 필요하면 `oauth_tokens` 테이블로 분리. Phase 1은 학습용이라 1개로 단순화.

### 학습 질문
- [ ] 왜 `token_expiry`는 timezone 없는 DateTime일까? (힌트: 구글 라이브러리 포맷)
- [ ] `unique=True, index=True`를 email/google_sub에 둔 이유는?

---

## Step 5: `integrations/oauth.py` 읽기 (15분, 가장 중요)

### 목표
구글과의 OAuth2 4단계 대화를 코드로 이해

### 핵심 개념 — 4개의 함수

**① `authorization_url()` — 동의 화면 URL 만들기**
```python
url, state = flow.authorization_url(
    access_type="offline",   # ← refresh_token을 받기 위해 필수!
    prompt="consent",        # ← 매번 동의 → refresh_token 확실히 수령
)
```
`access_type="offline"`가 없으면 access_token만 받고 **refresh_token을 못 받습니다** (자동 갱신 불가). 이게 초보자가 가장 많이 하는 실수.

**② `exchange_code(code, state)` — 임시 코드 → 진짜 토큰**
```python
flow.fetch_token(code=code)
return flow.credentials   # access_token + refresh_token + id_token + expiry
```

**③ `user_info_from_credentials(creds)` — 누구인지 알아내기**
```python
info = id_token.verify_oauth2_token(creds.id_token, request, CLIENT_ID)
return {"sub": info["sub"], "email": info["email"]}
```
`id_token`은 사용자 정보가 담긴 서명된 JWT. 검증하면 별도 API 호출 없이 email/sub를 얻습니다.

**④ `build_user_credentials()` + `ensure_fresh()` — 저장된 토큰 복원 & 자동 갱신**
```python
creds = build_user_credentials(access_token, refresh_token, expiry)
if not creds.valid:            # 만료됐거나 access_token이 없으면
    creds.refresh(Request())   # refresh_token으로 새 access_token 발급
```
**Phase 1 검증의 핵심**: `expiry`를 넣어줘야 `creds.valid`가 실제 만료 여부를 정확히 판단합니다.

**알아두면 좋은 함정** — `OAUTHLIB_RELAX_TOKEN_SCOPE=1`:
구글이 돌려주는 scope 순서가 요청과 달라 `"Scope has changed"` 오류가 날 수 있어, 파일 상단에서 이 환경변수를 미리 설정해 막았습니다.

### 학습 질문
- [ ] `access_type="offline"`을 빼면 `/auth/me`에서 무슨 일이 생길까?
- [ ] `id_token`(누구인지)과 `access_token`(무엇을 할 수 있는지)의 차이는?
- [ ] 이 파일은 왜 DB를 import하지 않을까? (힌트: 책임 분리)

---

## Step 6: `routers/auth.py` 읽기 (15분)

### 목표
3개 엔드포인트로 OAuth 흐름을 사용자에게 노출하는 방식 이해

### 핵심 개념

**`GET /auth/login`** — 시작
```python
url, state = oauth.authorization_url()
request.session["oauth_state"] = state   # CSRF 방어용으로 세션에 보관
return RedirectResponse(url)
```

**`GET /auth/callback`** — 돌아옴 + 저장
```python
if request.session.get("oauth_state") != state:   # CSRF 검증
    raise HTTPException(400, "유효하지 않은 state")
creds = oauth.exchange_code(code, state)
if not creds.refresh_token:                         # 안전장치
    raise HTTPException(400, "권한 해제 후 재로그인 안내")
info = oauth.user_info_from_credentials(creds)
# google_sub 기준 upsert → refresh_token 암호화 저장
```

**`GET /auth/me`** — 검증 (E2E)
```python
creds = oauth.build_user_credentials(access_token, decrypt(refresh_token_enc), expiry)
creds = oauth.ensure_fresh(creds)   # 만료 시 자동 갱신
# 갱신된 토큰 다시 저장
service = build("gmail", "v1", credentials=creds)
profile = service.users().getProfile(userId="me").execute()
```
이 호출이 성공하면 **로그인 → 저장 → 갱신 → 실제 사용** 전 과정이 동작한다는 증거.

**엔드포인트가 `def`인 이유** (FastAPI 공식: async-def-vs-def):
google-api-python-client와 SQLAlchemy(sync)는 블로킹. `def`로 선언하면 FastAPI가 threadpool에서 실행해 이벤트 루프를 막지 않습니다.

> ⚠️ **`/auth/me`의 보안 한계 (학습용)**: 사용자를 `email` 쿼리 파라미터로 식별하므로,
> 이 주소를 아는 사람은 누구나 그 사람의 Gmail 프로필을 조회할 수 있습니다. Phase 1은
> **로컬 단일 사용자 검증용**이라 의도적으로 단순화한 것입니다. 실서비스에서는 앱 자체의
> 로그인 세션/인증 토큰에서 "현재 사용자"를 도출해야 하며, 이메일을 클라이언트가 직접
> 보내게 하면 안 됩니다.

### 학습 질문
- [ ] `state`를 세션에 저장했다가 콜백에서 비교하는 이유(CSRF)는?
- [ ] callback에서 refresh_token이 없을 때 굳이 막는 이유는?
- [ ] upsert 기준이 email이 아니라 google_sub인 이유는? (Step 4 복습)

---

## Step 7: `main.py` 읽기 (5분)

### 목표
조각들을 조립해 서버로 기동하는 방식 이해

### 핵심 개념

```python
@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(bind=engine)   # 시작 시 테이블 생성
    yield

app.add_middleware(SessionMiddleware, secret_key=...)   # OAuth state 보관
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"])
app.include_router(auth.router)
```

- **lifespan**: 시작/종료 훅 (FastAPI 공식, 구식 `@app.on_event` 아님). 여기선 테이블 생성.
  - ⚠️ 학습용 간이 방식. 실서비스는 **Alembic 마이그레이션** 사용.
- **SessionMiddleware**: `request.session`을 쓰려면 필수. `itsdangerous`로 서명된 쿠키.
- **`from db import models`**: `create_all` 전에 User 모델을 Base에 등록하기 위한 import.

### 학습 질문
- [ ] `from db import models`를 빼면 테이블이 안 생기는 이유는?
- [ ] SessionMiddleware를 빼면 `/auth/login`에서 무슨 에러가 날까?

---

## 실습: 처음부터 끝까지 동작시키기 (20분)

### A. Google Cloud Console 설정 (최초 1회)

1. https://console.cloud.google.com → 프로젝트 생성(또는 선택)
2. **API 및 서비스 → 라이브러리** 에서 **Gmail API**, **Google Calendar API** 사용 설정
3. **OAuth 동의 화면** 구성
   - User Type: **외부(External)**
   - 앱 이름/이메일 입력
   - **테스트 사용자(Test users)** 에 본인 구글 계정 추가 (게시 전엔 테스트 사용자만 로그인 가능)
   - 범위(scope)는 코드가 요청하므로 여기선 추가 안 해도 됨
4. **사용자 인증 정보 → 사용자 인증 정보 만들기 → OAuth 클라이언트 ID**
   - 유형: **웹 애플리케이션**
   - **승인된 리디렉션 URI**: `http://localhost:8000/auth/callback` (코드의 `OAUTH_REDIRECT_URI`와 정확히 일치!)
   - 생성 후 **클라이언트 ID / 클라이언트 보안 비밀** 복사

> 로컬은 `http://localhost` 리다이렉트가 허용되어 HTTPS 없이 테스트 가능합니다. (HTTPS는 Phase 8 배포에서.)

### B. DB 준비

```bash
# 프로젝트 1과 동일 PostgreSQL(localhost:5433)에 DB만 새로 생성
psql -h localhost -p 5433 -U postgres -c "CREATE DATABASE assistant_db;"
```

### C. `.env` 작성

```bash
cd 02.personal-assitant-agent
cp .env.example .env
```
`.env`를 열어 채웁니다:
```bash
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/assistant_db
GOOGLE_CLIENT_ID=<복사한 클라이언트 ID>
GOOGLE_CLIENT_SECRET=<복사한 보안 비밀>
OAUTH_REDIRECT_URI=http://localhost:8000/auth/callback

# 아래 두 키 생성해서 붙여넣기
TOKEN_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
SESSION_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
```

### D. 서버 실행

```bash
cd 02.personal-assitant-agent/backend
uv run uvicorn main:app --reload --port 8000
```

### E. E2E 테스트 (브라우저)

```
1. http://localhost:8000/auth/login  접속
       → 구글 동의 화면 → [허용]
2. 자동으로 /auth/callback 로 돌아오며 "로그인 성공 ✅" 표시
3. 표시된 링크 /auth/me?email=<your@gmail.com> 클릭
       → {"email": "...", "messages_total": 1234, ...} 가 보이면 성공!
```

### F. 자동 갱신 확인 (선택)

```sql
-- DB에서 만료시각을 과거로 강제 → /auth/me 재호출 시 자동 갱신되는지 확인
UPDATE users SET token_expiry = '2000-01-01 00:00:00';
```
이후 `/auth/me`를 다시 열면, 만료된 access_token이 refresh_token으로 **자동 갱신**되어 정상 응답해야 합니다. DB의 `access_token`/`token_expiry`가 갱신됐는지 확인하세요.

---

## 검증 체크리스트

### 개념
- [ ] access token / refresh token의 차이와 수명을 설명할 수 있다
- [ ] `access_type="offline"`이 refresh_token 수령에 왜 필수인지 안다
- [ ] refresh_token을 암호화 저장하는 이유를 설명할 수 있다

### 코드
- [ ] `config.py`: 필수/선택 설정 구분, `@lru_cache`의 역할
- [ ] `security.py`: Fernet 암복호화 왕복
- [ ] `db/session.py`: engine/session/Base 역할, `get_db` yield 패턴
- [ ] `db/models.py`: google_sub로 식별하는 이유
- [ ] `integrations/oauth.py`: 4개 함수의 흐름
- [ ] `routers/auth.py`: login→callback→me 흐름, `def`인 이유

### 동작
- [ ] `/auth/login` → 구글 동의 → `/auth/callback` "로그인 성공"
- [ ] DB `users` 테이블에 행이 생기고 `refresh_token_enc`가 **암호문**이다
- [ ] `/auth/me` 가 실제 Gmail 프로필을 반환한다
- [ ] 만료시각을 과거로 바꿔도 `/auth/me`가 자동 갱신 후 동작한다

---

## 자주 막히는 곳 (Troubleshooting)

| 증상 | 원인/해결 |
|------|-----------|
| `redirect_uri_mismatch` | 구글 콘솔의 리디렉션 URI와 `OAUTH_REDIRECT_URI`가 글자까지 일치해야 함 |
| 로그인 화면에서 차단됨 | OAuth 동의 화면 "테스트 사용자"에 본인 계정 추가 안 함 |
| `refresh_token`이 None | 이미 동의한 적 있어 미발급 → https://myaccount.google.com/permissions 에서 앱 제거 후 재로그인 |
| `Scope has changed` | 코드가 `OAUTHLIB_RELAX_TOKEN_SCOPE=1`을 설정해 방지함 (재확인) |
| `can't compare offset-naive and offset-aware datetimes` | `token_expiry` 컬럼을 naive DateTime으로 둔 이유(구글 expiry가 naive UTC). DB가 tz-aware로 돌려주도록 설정돼 있으면 발생 가능 → 컬럼/세션 tz 설정 확인 |
| DB 연결 오류 | `assistant_db` 생성 여부, `postgresql+psycopg://` 형식 확인 |

---

## 다음 단계

Phase 1을 완료했으면 (토큰을 안전하게 확보):
- **Phase 2**: Gmail / Calendar Tool 연결 — 저장한 토큰으로 에이전트가 실제 메일·일정 조회/조작
- **Phase 3**: Structured Output (EmailAnalysis) — 메일을 의도·우선순위 스키마로 파싱

Phase 1에서 "토큰을 어떻게 얻고 보관하는가"를 이해했으니, Phase 2는 그 토큰을 **도구(Tool)로 감싸 에이전트에 쥐여주는** 단계입니다.
