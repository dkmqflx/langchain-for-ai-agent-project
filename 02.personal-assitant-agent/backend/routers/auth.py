"""
사용자가 드나드는 "문" — OAuth2 라우터

엔드포인트 (prefix="/auth"):
  GET /auth/login    : 구글 동의 화면으로 리다이렉트 (state를 세션에 저장)
  GET /auth/callback : 구글이 돌려보낸 code를 토큰으로 교환 → users 테이블 upsert
  GET /auth/me       : 저장된 토큰(만료 시 자동 갱신)으로 실제 Gmail 프로필 조회 (E2E 검증)

엔드포인트가 async def가 아니라 def인 이유:
  google-api-python-client와 SQLAlchemy(sync)는 블로킹 I/O다.
  def로 선언하면 FastAPI가 threadpool에서 실행해 이벤트 루프를 막지 않는다
  (FastAPI 공식: async-def-vs-def).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from googleapiclient.discovery import build as build_google_service
from sqlalchemy import select
from sqlalchemy.orm import Session

import security
from db.models import User
from db.session import get_db
from integrations import oauth
from models.auth import GmailProfile

router = APIRouter(prefix="/auth", tags=["auth"])

# 반복되는 DB 의존성을 타입 별칭으로 (FastAPI 공식: di-reusable-type-alias)
DbDep = Annotated[Session, Depends(get_db)]


@router.get("/login")
def login(request: Request) -> RedirectResponse:
    """① 구글 로그인 시작 → 동의 화면으로 보냄."""
    url, state = oauth.authorization_url()
    # state를 서버 세션에 보관 → 콜백에서 위조 요청(CSRF)인지 검증
    request.session["oauth_state"] = state
    return RedirectResponse(url)


@router.get("/callback")
def callback(
    request: Request,
    db: DbDep,
    code: str = Query(..., description="구글이 발급한 임시 인증 코드"),
    state: str = Query(..., description="CSRF 방어용 state"),
) -> HTMLResponse:
    """② 구글이 돌아옴 → code를 토큰으로 교환하고 DB에 저장."""
    # CSRF 검증: 우리가 보냈던 state와 일치해야 함
    saved_state = request.session.get("oauth_state")
    if not saved_state or saved_state != state:
        raise HTTPException(status_code=400, detail="유효하지 않은 OAuth state입니다.")

    creds = oauth.exchange_code(code, state)

    # refresh_token이 없으면 이후 자동 갱신이 불가능 → 명확히 안내
    if not creds.refresh_token:
        raise HTTPException(
            status_code=400,
            detail=(
                "refresh_token을 받지 못했습니다. "
                "https://myaccount.google.com/permissions 에서 이 앱 접근을 제거한 뒤 "
                "다시 로그인하세요."
            ),
        )

    info = oauth.user_info_from_credentials(creds)

    # upsert: 같은 google_sub가 있으면 갱신, 없으면 신규 생성
    user = db.scalar(select(User).where(User.google_sub == info["sub"]))
    if user is None:
        user = User(
            google_sub=info["sub"],
            email=info["email"],
            refresh_token_enc=security.encrypt(creds.refresh_token),
        )
        db.add(user)
    else:
        user.email = info["email"]
        user.refresh_token_enc = security.encrypt(creds.refresh_token)

    user.access_token = creds.token
    user.token_expiry = creds.expiry
    db.commit()

    # 세션의 state는 1회용 → 정리
    request.session.pop("oauth_state", None)

    return HTMLResponse(
        f"""
        <h2>로그인 성공 ✅</h2>
        <p><b>{info['email']}</b> 의 토큰을 저장했습니다.</p>
        <p>아래 링크로 토큰이 실제로 동작하는지 확인하세요:</p>
        <p><a href="/auth/me?email={info['email']}">/auth/me?email={info['email']}</a></p>
        """
    )


@router.get("/me", response_model=GmailProfile)
def me(db: DbDep, email: str = Query(..., description="조회할 사용자 이메일")) -> GmailProfile:
    """③ 검증: 저장된 토큰으로 실제 Gmail 프로필을 가져온다 (만료 시 자동 갱신).

    ⚠️ 알려진 한계(학습용): 사용자를 email 쿼리 파라미터로 식별하므로, 이 주소를
    아는 사람은 누구나 그 사람의 Gmail 프로필을 조회할 수 있다. Phase 1은 로컬
    단일 사용자 검증용이라 의도적으로 단순화했다. 실서비스에서는 앱 자체의 로그인
    세션/인증 토큰에서 현재 사용자를 도출해야 한다(이메일을 클라이언트가 보내면 안 됨).
    """
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        raise HTTPException(
            status_code=404,
            detail="등록된 사용자가 없습니다. 먼저 /auth/login 으로 로그인하세요.",
        )

    # 저장값으로 Credentials 복원 → 만료됐으면 refresh_token으로 자동 갱신
    creds = oauth.build_user_credentials(
        access_token=user.access_token,
        refresh_token=security.decrypt(user.refresh_token_enc),
        expiry=user.token_expiry,
    )
    creds = oauth.ensure_fresh(creds)

    # 갱신됐을 수 있으니 최신 access_token/만료시각을 다시 저장
    user.access_token = creds.token
    user.token_expiry = creds.expiry
    db.commit()

    # 실제 Gmail API 호출 — 이게 성공하면 전체 OAuth 루프가 동작하는 것
    service = build_google_service("gmail", "v1", credentials=creds, cache_discovery=False)
    profile = service.users().getProfile(userId="me").execute()

    return GmailProfile(
        email=profile["emailAddress"],
        messages_total=int(profile.get("messagesTotal", 0)),
        threads_total=int(profile.get("threadsTotal", 0)),
        history_id=str(profile.get("historyId", "")),
    )
