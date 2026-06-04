# Phase 1 학습 가이드 — NextAuth 구글 로그인 + 공유 토큰 DB + 백엔드 JWT 검증

이 가이드는 Phase 1에서 만든 파일들을 **역할 순서대로** 읽으며, "프론트(NextAuth)가 구글 로그인을 처리하고 → 구글 토큰을 공유 DB에 저장하고 → 백엔드가 그 토큰을 빌려 실제 Gmail을 호출하는" 전체 흐름을 이해하도록 구성했습니다.

> **Phase 1의 목표 한 줄**: NextAuth로 **구글 로그인 + Gmail/캘린더 권한 위임** → 구글 토큰을 **공유 Postgres에 저장** → 백엔드는 **앱 JWT로 사용자를 식별**하고 그 토큰으로 **실제 Gmail 호출**까지. (AI 기능은 Phase 2부터)

---

## 0. 먼저: 누가 무엇을 하나 (역할 분담)

이 프로젝트는 **프론트(Next.js)** 와 **백엔드(FastAPI)** 가 따로 있습니다. Phase 1에서 가장 먼저 이해할 것은 "**인증을 누가 처리하는가**"입니다.

```
프론트(NextAuth)  →  구글 OAuth2 전담 (로그인/동의/콜백/토큰 교환)
                    + 구글 토큰을 공유 Postgres에 저장
                    + 백엔드용 "앱 JWT" 발급

백엔드(FastAPI)   →  앱 JWT 검증으로 "누구인지" 확인
                    + 공유 DB에서 그 사람의 구글 토큰을 읽어 Gmail 호출
                    + 구글 access_token 갱신은 백엔드가 전담
```

### OAuth2가 왜 필요한가 (호텔 카드키 비유)

사용자의 구글 비밀번호를 우리가 직접 받는 건 위험하고 구글이 막아둡니다. 대신 표준 방식 **OAuth2**를 씁니다.

```
사용자  = 투숙객
구글    = 호텔 프런트 (열쇠 발급처)
NextAuth = 프런트와 협상하는 컨시어지   ← 이번 프로젝트에선 "프론트"가 이 역할
```

- 투숙객(사용자)이 **프런트(구글)** 에 직접 가서 "이 앱이 내 메일/일정에 접근해도 됨"을 **동의**
- 프런트는 **마스터키가 아니라 제한된 카드키(토큰)** 를 발급
- 우리 앱은 **비밀번호를 전혀 모름**. 토큰만 보유

### 이번 Phase의 "토큰"은 3종류 — 가장 헷갈리는 부분

| 토큰 | 누가 만드나 | 수명 | 용도 |
|------|------------|------|------|
| **구글 access token** | 구글 | 약 1시간 | 실제로 Gmail/캘린더를 열 때 |
| **구글 refresh token** | 구글 | 거의 영구 | access token 만료 시 새로 발급 |
| **앱 JWT** | NextAuth(우리) | 짧게(예: 분~시간) | **프론트→백엔드** 요청 시 "나 누구야"를 증명 |

핵심 구분:
- **구글 토큰**은 "구글에게 무엇을 할 수 있는가"(Gmail 열기). 공유 DB `accounts`에 저장.
- **앱 JWT**는 "백엔드에게 내가 누구인가"(`sub` = 우리 DB의 `users.id`). 프론트가 `Authorization: Bearer`로 전달.

> ⚠️ **왜 앱 JWT를 따로 만드나? (이번 설계의 핵심)**
> NextAuth의 기본 세션 토큰은 그냥 서명된 JWT가 아니라 **암호화된 JWE**입니다. 그래서 파이썬 백엔드에서 `pyjwt`로 바로 검증할 수 없습니다. 그래서 NextAuth가 **별도의 서명(HS256) JWT**를 `APP_JWT_SECRET`로 만들어주고, 백엔드는 같은 시크릿으로 그것만 검증합니다. (NextAuth 버전이 올라가도 안 깨지는 표준 방식)

---

## 학습 흐름도

```
[프론트] 사용자가 "구글 로그인" 클릭 → signIn("google")
        ↓
[프론트/NextAuth]  구글 동의 화면 (scope: gmail.modify/send, calendar / access_type=offline)
        ↓ (사용자 동의)
[프론트/NextAuth]  /api/auth/callback/google → code→token 교환
        ↓
[@auth/pg-adapter]  공유 Postgres에 저장
        users(id, email)  /  accounts(refresh_token, access_token, providerAccountId=구글 sub)
        ↓
[프론트/NextAuth]  session.strategy="jwt" → jwt/session 콜백에서 앱 JWT(sub=users.id) 발급
        ↓
[프론트 → 백엔드]  GET /auth/me   (헤더: Authorization: Bearer <앱 JWT>)
        ↓
[백엔드/security.py]  앱 JWT 검증 → users.id 추출
        ↓
[백엔드/google_auth.py]  accounts에서 refresh_token 읽기 → access_token 갱신 → Gmail 호출 (검증)
```

| 파일 | 위치 | 한 줄 역할 |
|------|------|-----------|
| `auth.ts` | 프론트 | NextAuth 설정: Google Provider + pg-adapter + 앱 JWT 발급 |
| `app/api/auth/[...nextauth]/route.ts` | 프론트 | NextAuth HTTP 핸들러 (로그인/콜백/세션) |
| `login/page.tsx` | 프론트 | `signIn("google")` 버튼 |
| `lib/api.ts` | 프론트 | 백엔드 호출 시 `Bearer <앱 JWT>` 자동 첨부 |
| `config.py` | 백엔드 | `.env`의 비밀값을 타입과 함께 로딩 |
| `db/session.py` | 백엔드 | DB 연결 + 요청별 세션(`get_db`) |
| `db/models.py` | 백엔드 | NextAuth가 만든 `users`/`accounts` **읽기 매핑** |
| `security.py` | 백엔드 | 앱 JWT 검증 + `get_current_user` 의존성 |
| `integrations/google_auth.py` | 백엔드 | 저장된 토큰 복원 + access_token 갱신 + Gmail 호출 |
| `routers/auth.py` | 백엔드 | `GET /auth/me` (검증용 엔드포인트) |
| `main.py` | 백엔드 | 조각 조립 + 서버 기동 |

---

## Part A — 프론트 (NextAuth)

### Step 1: `auth.ts` 읽기 (20분, 가장 중요)

#### 목표
NextAuth가 구글 OAuth를 전담하고, 구글 토큰을 공유 DB에 저장하고, 앱 JWT를 발급하는 설정을 이해

#### 핵심 개념

```ts
import NextAuth from "next-auth"
import Google from "next-auth/providers/google"
import PostgresAdapter from "@auth/pg-adapter"
import { Pool } from "pg"
import { SignJWT } from "jose"

const pool = new Pool({ connectionString: process.env.DATABASE_URL })

export const { handlers, auth, signIn, signOut } = NextAuth({
  adapter: PostgresAdapter(pool),       // ① 구글 토큰을 공유 Postgres에 저장
  session: { strategy: "jwt" },         // ② adapter 쓸 때 반드시 명시!
  providers: [
    Google({
      authorization: {
        params: {
          access_type: "offline",       // ③ refresh_token 받기 필수
          prompt: "consent",
          scope: "openid email profile " +
            "https://www.googleapis.com/auth/gmail.modify " +
            "https://www.googleapis.com/auth/gmail.send " +
            "https://www.googleapis.com/auth/calendar",
        },
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user }) {
      if (user) token.uid = user.id     // ④ 최초 로그인 때 users.id 보관
      return token
    },
    async session({ session, token }) {
      // ⑤ 백엔드에 보낼 "앱 JWT"를 HS256으로 서명해 세션에 노출
      const secret = new TextEncoder().encode(process.env.APP_JWT_SECRET)
      session.appToken = await new SignJWT({ sub: token.uid as string })
        .setProtectedHeader({ alg: "HS256" })
        .setExpirationTime("1h")
        .sign(secret)
      return session
    },
  },
})
```

**왜 이렇게 하나 — 네 가지 못 박기**

- **① adapter**: `@auth/pg-adapter`가 로그인 시 `users`/`accounts`/`sessions` 테이블에 자동 저장. 구글 `refresh_token`은 `accounts.refresh_token`에 들어갑니다.
- **② `session.strategy: "jwt"` 필수**: adapter를 붙이면 기본값이 `"database"`가 되는데, 그러면 **`jwt` 콜백이 실행되지 않아** 앱 JWT를 만들 수 없습니다. `jwt` 전략 + adapter 조합이면 → `jwt` 콜백도 돌고(앱 JWT 발급 가능), `linkAccount`로 구글 토큰도 `accounts`에 저장됩니다. **양쪽을 모두 얻는 유일한 조합**입니다.
- **③ `access_type="offline"`**: 없으면 access_token만 받고 **refresh_token을 못 받습니다**(자동 갱신 불가). 초보자가 가장 많이 하는 실수.
- **⑤ 앱 JWT는 서명 토큰**: NextAuth 기본 세션은 JWE(암호화)라 백엔드가 못 읽으므로, 검증 가능한 별도 HS256 JWT를 만들어 `session.appToken`으로 노출합니다.

> 🔐 **보안 메모(학습 단계 단순화)**: `@auth/pg-adapter`는 `accounts.refresh_token`을 **평문**으로 저장합니다. 학습 단계라 그대로 둡니다. 실서비스에서는 컬럼 암호화(pgcrypto) 또는 암호화 커스텀 adapter를 적용하세요.

#### 학습 질문
- [ ] adapter를 붙였는데 `session.strategy`를 안 바꾸면 `jwt` 콜백이 왜 안 도나?
- [ ] `access_type="offline"`을 빼면 백엔드 `/auth/me`에서 무슨 일이 생길까?
- [ ] 왜 NextAuth 기본 세션 토큰을 그대로 백엔드에 보내면 안 될까? (힌트: JWE)

---

### Step 2: `route.ts` + `login/page.tsx` + `lib/api.ts` (10분)

#### 핵심 개념

**`app/api/auth/[...nextauth]/route.ts`** — NextAuth를 HTTP로 노출
```ts
import { handlers } from "@/auth"
export const { GET, POST } = handlers
```

**`login/page.tsx`** — 로그인 버튼
```tsx
import { signIn } from "@/auth"
export default function Login() {
  return <form action={async () => { "use server"; await signIn("google") }}>
    <button>구글로 로그인</button>
  </form>
}
```

**`lib/api.ts`** — 백엔드 호출 시 앱 JWT 첨부
```ts
import { auth } from "@/auth"
export async function apiFetch(path: string, init: RequestInit = {}) {
  const session = await auth()
  return fetch(`${process.env.NEXT_PUBLIC_API_URL}${path}`, {
    ...init,
    headers: { ...init.headers, Authorization: `Bearer ${session?.appToken}` },
  })
}
```

#### 학습 질문
- [ ] 백엔드는 어떻게 "이 요청이 누구 것"인지 알까? (힌트: Bearer)
- [ ] `appToken`이 만료되면 어떻게 새로 받을까? (힌트: session 콜백이 매번 재서명)

---

## Part B — 백엔드 (FastAPI)

### Step 3: `config.py` 읽기 (5분)

#### 목표
환경변수(비밀값)를 타입 있게 한 곳에서 관리

```python
class Settings(BaseSettings):
    database_url: str                 # 공유 Postgres (NextAuth와 동일 DB)
    app_jwt_secret: str               # NextAuth와 공유 (앱 JWT 검증)
    google_client_id: str             # access_token 갱신에 필요
    google_client_secret: str         # access_token 갱신에 필요
```

> **왜 백엔드도 구글 client_id/secret가 필요한가**: 구글 access_token을 refresh_token으로 갱신하려면, 갱신 요청에 **클라이언트 자격증명(client_id + client_secret)** 이 함께 들어가야 합니다(웹 클라이언트). 그래서 프론트(NextAuth)와 백엔드가 같은 구글 자격증명을 공유합니다.

- `@lru_cache`로 `.env`를 한 번만 읽어 재사용(FastAPI 공식 권장).
- `.env` 위치: `backend/`의 상위(`02.personal-assitant-agent/.env`).

#### 학습 질문
- [ ] `app_jwt_secret`이 프론트와 다르면 무슨 일이 생길까?
- [ ] 백엔드가 구글 토큰을 "갱신"하려면 왜 client_secret이 필요할까?

---

### Step 4: `db/session.py` + `db/models.py` 읽기 (15분)

#### 목표
공유 DB에 연결하고, **NextAuth가 만든 테이블을 읽는** 매핑을 이해

#### `db/session.py` — 연결 3대 구성요소
```python
engine = create_engine(DATABASE_URL)        # 커넥션 풀 (앱당 1개)
SessionLocal = sessionmaker(bind=engine)    # 요청마다 세션 팩토리
class Base(DeclarativeBase): ...
```
`get_db()`는 `yield` 의존성으로 요청마다 열고 `finally`에서 닫습니다(누수 방지).

**커넥션 문자열**: `postgresql+psycopg://...` ✅ (psycopg3 명시) / `postgresql://...` 🔴

#### `db/models.py` — **읽기 매핑** (가장 중요한 차이점)

```python
class User(Base):
    __tablename__ = "users"           # NextAuth가 만든 테이블
    id: Mapped[str]                   # PK (cuid/uuid) — 앱 JWT의 sub가 이 값
    email: Mapped[str]

class Account(Base):
    __tablename__ = "accounts"
    userId: Mapped[str]               # users.id 참조
    provider: Mapped[str]             # "google"
    providerAccountId: Mapped[str]    # ← 구글의 sub (불변 ID)
    refresh_token: Mapped[str | None]
    access_token: Mapped[str | None]
    expires_at: Mapped[int | None]    # epoch seconds
```

> ⚠️ **`create_all` 금지**: 이 `users`/`accounts` 테이블은 **NextAuth(adapter)가 소유·생성**합니다. 백엔드가 `Base.metadata.create_all`로 또 만들면 두 쪽이 스키마를 두고 충돌합니다. 백엔드는 **읽기만** 합니다. (백엔드 고유 테이블인 선호도 테이블만 백엔드가 생성)

> **식별자 정리**: 앱 JWT의 `sub` = `users.id`(우리 DB). 구글의 sub = `accounts.providerAccountId`. 백엔드는 `users.id`로 `accounts` 행을 찾아 구글 토큰을 얻습니다.

#### 학습 질문
- [ ] 왜 백엔드는 `users`/`accounts`를 `create_all` 하면 안 될까?
- [ ] 앱 JWT의 `sub`는 구글 sub일까, 우리 DB의 `users.id`일까?

---

### Step 5: `security.py` 읽기 (10분)

#### 목표
프론트가 보낸 앱 JWT를 검증해 "현재 사용자"를 도출하는 의존성 이해

```python
import jwt                                     # pyjwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import get_settings

bearer = HTTPBearer()

def get_current_user_id(
    cred: HTTPAuthorizationCredentials = Depends(bearer),
) -> str:
    try:
        payload = jwt.decode(
            cred.credentials,
            get_settings().app_jwt_secret,
            algorithms=["HS256"],              # 프론트와 동일 알고리즘/시크릿
        )
    except jwt.PyJWTError:
        raise HTTPException(401, "유효하지 않은 토큰")
    return payload["sub"]                       # = users.id
```

- `HTTPBearer`로 `Authorization: Bearer <앱 JWT>` 헤더를 꺼냅니다(FastAPI 공식 보안 유틸).
- 검증 성공 → `sub`(=`users.id`) 반환. 엔드포인트는 `Depends(get_current_user_id)`로 주입받습니다.
- **NextAuth 기본 JWE를 검증하는 게 아니라**, 우리가 서명한 HS256 JWT만 검증합니다.

#### 학습 질문
- [ ] 프론트가 NextAuth 기본 세션 토큰을 그대로 보냈다면 이 코드는 왜 실패할까?
- [ ] `algorithms=["HS256"]`을 빼거나 시크릿이 다르면?

---

### Step 6: `integrations/google_auth.py` 읽기 (15분)

#### 목표
저장된 구글 토큰을 복원하고, 만료 시 **백엔드가 직접 갱신**해 Gmail을 호출하는 흐름 이해

```python
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from config import get_settings

SCOPES = ["https://www.googleapis.com/auth/gmail.modify", ...]

def build_credentials(account) -> Credentials:
    s = get_settings()
    return Credentials(
        token=account.access_token,
        refresh_token=account.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=s.google_client_id,          # ← 갱신에 필요
        client_secret=s.google_client_secret,  # ← 갱신에 필요
        scopes=SCOPES,
    )

def ensure_fresh(creds: Credentials) -> Credentials:
    if not creds.valid:                         # 만료/없음
        creds.refresh(Request())                # refresh_token으로 새 access_token
    return creds
```

**왜 백엔드가 갱신을 전담하나 (이중 갱신 레이스 방지)**: NextAuth와 백엔드가 둘 다 갱신하면 토큰 회전(rotation) 경쟁이 생깁니다. 그래서 **NextAuth는 최초 1회 캡처만, 이후 갱신은 백엔드만** 합니다. 갱신 후 새 `access_token`/`expires_at`을 DB `accounts`에 다시 저장하면 다음 호출이 빨라집니다.

```python
service = build("gmail", "v1", credentials=creds)
profile = service.users().getProfile(userId="me").execute()
```

#### 학습 질문
- [ ] 백엔드가 `client_secret` 없이 `creds.refresh()`를 부르면 어떻게 될까?
- [ ] 왜 NextAuth와 백엔드가 동시에 갱신하면 안 될까?

---

### Step 7: `routers/auth.py` + `main.py` 읽기 (10분)

#### `GET /auth/me` — E2E 검증 엔드포인트
```python
@router.get("/auth/me")
def me(user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    account = db.query(Account).filter_by(userId=user_id, provider="google").one()
    creds = ensure_fresh(build_credentials(account))
    # 갱신됐으면 account.access_token/expires_at 다시 저장
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    return {"user_id": user_id, "email": profile["emailAddress"],
            "messages_total": profile["messagesTotal"]}
```
이 호출이 성공하면 **로그인(NextAuth) → 토큰 저장(DB) → JWT 검증(백엔드) → 갱신 → 실제 Gmail 사용** 전 과정이 동작한다는 증거입니다.

#### `main.py`
```python
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"])
app.include_router(auth.router)
```
- **SessionMiddleware 불필요**: OAuth state는 프론트 NextAuth가 관리합니다(백엔드는 쿠키 세션을 쓰지 않음).
- **인증 테이블 `create_all` 안 함**: NextAuth가 소유. lifespan에서는 백엔드 고유 테이블(선호도 등)만 생성.

> 엔드포인트가 `def`(동기)인 이유: google-api-python-client·SQLAlchemy는 블로킹 I/O. `def`로 선언하면 FastAPI가 threadpool에서 실행해 이벤트 루프를 막지 않습니다(FastAPI 공식: async-def-vs-def).

#### 학습 질문
- [ ] 백엔드에서 SessionMiddleware가 더 이상 필요 없는 이유는?
- [ ] lifespan에서 `users`/`accounts`를 만들면 안 되는 이유는?

---

## 실습: 처음부터 끝까지 동작시키기 (30분)

### A. Google Cloud Console 설정 (최초 1회)

1. https://console.cloud.google.com → 프로젝트 생성/선택
2. **API 및 서비스 → 라이브러리**: **Gmail API**, **Google Calendar API** 사용 설정
3. **OAuth 동의 화면**: User Type **외부(External)**, 앱 이름/이메일 입력, **테스트 사용자**에 본인 계정 추가
4. **사용자 인증 정보 → OAuth 클라이언트 ID**
   - 유형: **웹 애플리케이션**
   - **승인된 리디렉션 URI**: `http://localhost:3000/api/auth/callback/google` ← **NextAuth(프론트) 콜백**
   - 클라이언트 ID / 보안 비밀 복사

> 로컬은 `http://localhost` 리다이렉트가 허용됩니다. (HTTPS는 Phase 8 배포에서.)

### B. DB 준비 (프론트·백엔드 공유)

```bash
psql -h localhost -p 5433 -U postgres -c "CREATE DATABASE assistant_db;"
```
> `users`/`accounts`/`sessions` 테이블은 **NextAuth(adapter)가 처음 로그인 때 자동 생성**(또는 adapter 마이그레이션)합니다. 백엔드는 만들지 않습니다.

### C. `.env` 작성 (공유 시크릿 주의)

**프론트 `frontend/.env.local`**
```bash
AUTH_SECRET=$(npx auth secret)        # NextAuth 세션 키
AUTH_GOOGLE_ID=<클라이언트 ID>
AUTH_GOOGLE_SECRET=<보안 비밀>
DATABASE_URL=postgresql://postgres:postgres@localhost:5433/assistant_db
APP_JWT_SECRET=<아래에서 생성>        # ★ 백엔드와 반드시 동일
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**백엔드 `02.personal-assitant-agent/.env`**
```bash
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/assistant_db
APP_JWT_SECRET=<위와 동일한 값>       # ★ 프론트와 동일해야 검증됨
GOOGLE_CLIENT_ID=<클라이언트 ID>      # 토큰 갱신용
GOOGLE_CLIENT_SECRET=<보안 비밀>
```

```bash
# APP_JWT_SECRET 생성 (양쪽에 같은 값)
python -c "import secrets; print(secrets.token_hex(32))"
```

### D. 실행 (두 개 다 켜기)

```bash
# 터미널 1 — 백엔드
cd 02.personal-assitant-agent/backend
uv run uvicorn main:app --reload --port 8000

# 터미널 2 — 프론트
cd 02.personal-assitant-agent/frontend
npm install && npm run dev   # http://localhost:3000
```

### E. E2E 테스트 (브라우저)

```
1. http://localhost:3000/login → "구글로 로그인" → 동의 [허용]
2. 로그인 성공 후 DB 확인:
     - users 에 행 1개
     - accounts 에 refresh_token 저장됨
3. 앱이 /auth/me 를 Bearer <앱 JWT>로 호출 → 실제 Gmail 프로필이 보이면 성공!
```

`/auth/me`를 직접 확인하려면, 로그인 후 세션의 `appToken`을 복사해:
```bash
curl http://localhost:8000/auth/me -H "Authorization: Bearer <appToken>"
# → {"user_id":"...", "email":"...", "messages_total": 1234}
```

### F. 자동 갱신 확인 (선택)

```sql
-- access_token 만료를 과거로 강제 → /auth/me 재호출 시 백엔드가 자동 갱신하는지 확인
UPDATE accounts SET expires_at = 0 WHERE provider = 'google';
```
이후 `/auth/me`가 정상 응답하고 `accounts.access_token`/`expires_at`이 갱신됐는지 확인하세요.

---

## 검증 체크리스트

### 개념
- [ ] OAuth를 **프론트(NextAuth)** 가 처리하고 **백엔드는 토큰을 소비**한다는 분담을 설명할 수 있다
- [ ] 구글 토큰(access/refresh)과 앱 JWT의 차이·용도를 구분할 수 있다
- [ ] NextAuth 기본 세션이 JWE라 백엔드가 못 읽고, 그래서 별도 서명 JWT를 쓰는 이유를 안다
- [ ] adapter + `session.strategy="jwt"` 조합이 왜 필요한지 안다

### 코드
- [ ] `auth.ts`: provider scope/offline, adapter, jwt 전략, 앱 JWT 발급
- [ ] `config.py`: 공유 `APP_JWT_SECRET`, 갱신용 구글 client 자격증명
- [ ] `db/models.py`: `users`/`accounts` 읽기 매핑, `create_all` 금지
- [ ] `security.py`: `get_current_user_id`로 앱 JWT 검증
- [ ] `google_auth.py`: 백엔드 전담 갱신 + Gmail 호출

### 동작
- [ ] NextAuth 구글 로그인 → `accounts`에 refresh_token 저장
- [ ] 프론트가 `Bearer <앱 JWT>`로 `/auth/me` 호출 → 실제 Gmail 프로필 반환
- [ ] `expires_at`을 과거로 바꿔도 백엔드가 자동 갱신 후 동작

---

## 자주 막히는 곳 (Troubleshooting)

| 증상 | 원인/해결 |
|------|-----------|
| `redirect_uri_mismatch` | 구글 콘솔 URI와 NextAuth 콜백(`http://localhost:3000/api/auth/callback/google`)이 글자까지 일치해야 함 |
| 로그인 화면에서 차단됨 | OAuth 동의 화면 "테스트 사용자"에 본인 계정 추가 안 함 |
| `accounts.refresh_token`이 NULL | `access_type=offline`/`prompt=consent` 누락, 또는 이미 동의해 미발급 → https://myaccount.google.com/permissions 에서 앱 제거 후 재로그인 |
| `jwt` 콜백이 안 불림 / `appToken` 없음 | adapter 사용 시 `session.strategy="jwt"` 누락 (기본 `database`라 jwt 콜백 미실행) |
| 백엔드 401 (유효하지 않은 토큰) | 프론트/백엔드 `APP_JWT_SECRET` 불일치, 또는 NextAuth 기본 세션을 잘못 보냄 |
| `creds.refresh()` 실패 | 백엔드에 `GOOGLE_CLIENT_ID`/`SECRET` 누락 (갱신엔 클라이언트 자격증명 필요) |
| 백엔드가 `users`/`accounts`를 못 찾음 | NextAuth가 먼저 로그인하며 테이블을 생성해야 함 (백엔드는 읽기만) |
| DB 연결 오류 | `assistant_db` 생성 여부, 백엔드는 `postgresql+psycopg://` 형식 확인 |

---

## 다음 단계

Phase 1을 완료했으면 (토큰을 안전하게 확보 + 사용자 식별):
- **Phase 2**: Gmail / Calendar Tool 연결 — 저장한 토큰으로 에이전트가 실제 메일·일정 조회/조작 (`ToolRuntime[AgentContext]`로 `user_id` 접근)
- **Phase 3**: Structured Output (EmailAnalysis) — 메일을 의도·우선순위 스키마로 파싱

Phase 1에서 "누가 토큰을 얻고 누가 소비하는가"를 이해했으니, Phase 2는 그 토큰을 **도구(Tool)로 감싸 에이전트에 쥐여주는** 단계입니다.
