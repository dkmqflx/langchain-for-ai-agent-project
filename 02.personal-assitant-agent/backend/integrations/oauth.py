"""
구글과 실제로 대화하는 모듈 — google-auth-oauthlib (구글 공식)

이 파일은 4가지 일을 한다 (DB는 모른다 — 순수 토큰 로직):
  1. authorization_url() : 사용자를 보낼 "구글 동의 화면 URL" 생성
  2. exchange_code()     : 콜백으로 받은 임시 code → 진짜 토큰(Credentials)으로 교환
  3. user_info_from_credentials() : id_token에서 email/sub(고유ID) 추출
  4. build_user_credentials()/ensure_fresh() : 저장된 토큰 복원 + 만료 시 자동 갱신

access_token / refresh_token:
  - access_token : Gmail/Calendar를 실제로 열 때 쓰는 1시간짜리 키
  - refresh_token: access_token이 만료되면 새로 발급받는 "재발급 쿠폰" (거의 영구)
  refresh_token을 받으려면 access_type="offline" + prompt="consent"가 필수.
"""

import os

# 구글이 돌려주는 scope의 순서/openid 자동 추가 때문에 발생하는
# "Scope has changed" 오류를 방지 (requests-oauthlib 동작 완화).
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

from google.auth.transport import requests as google_requests  # noqa: E402
from google.oauth2 import id_token as google_id_token  # noqa: E402
from google.oauth2.credentials import Credentials  # noqa: E402
from google_auth_oauthlib.flow import Flow  # noqa: E402

from config import get_settings  # noqa: E402

# 비서가 요청하는 권한 범위
#   openid + userinfo.email : 누가 로그인했는지(이메일/고유ID) 알기 위함
#   gmail.modify / gmail.send : 메일 읽기·라벨·초안 / 발송 (Phase 2+에서 사용)
#   calendar : 일정 조회·생성 (Phase 2+에서 사용)
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
]

TOKEN_URI = "https://oauth2.googleapis.com/token"


def _client_config() -> dict:
    """client_secret.json 파일 대신, .env 값으로 구성한 클라이언트 설정."""
    s = get_settings()
    return {
        "web": {
            "client_id": s.google_client_id,
            "client_secret": s.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": TOKEN_URI,
            "redirect_uris": [s.oauth_redirect_uri],
        }
    }


def _build_flow(state: str | None = None) -> Flow:
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, state=state)
    flow.redirect_uri = get_settings().oauth_redirect_uri
    return flow


def authorization_url() -> tuple[str, str]:
    """구글 동의 화면 URL과 CSRF 방어용 state를 생성해 반환."""
    flow = _build_flow()
    url, state = flow.authorization_url(
        access_type="offline",          # refresh_token을 받기 위함
        include_granted_scopes="true",
        prompt="consent",               # 매번 동의 → refresh_token 확실히 수령
    )
    return url, state


def exchange_code(code: str, state: str) -> Credentials:
    """콜백으로 받은 code를 토큰으로 교환."""
    flow = _build_flow(state=state)
    flow.fetch_token(code=code)
    return flow.credentials


def user_info_from_credentials(creds: Credentials) -> dict[str, str]:
    """id_token(JWT)을 검증하고 그 안의 sub(고유ID)/email을 꺼낸다."""
    request = google_requests.Request()
    info = google_id_token.verify_oauth2_token(
        creds.id_token,
        request,
        get_settings().google_client_id,
        clock_skew_in_seconds=10,  # 로컬 시계 오차 허용
    )
    return {"sub": info["sub"], "email": info["email"]}


def build_user_credentials(
    access_token: str | None,
    refresh_token: str,
    expiry=None,
) -> Credentials:
    """DB에 저장돼 있던 값으로 Credentials 객체를 복원."""
    s = get_settings()
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=TOKEN_URI,
        client_id=s.google_client_id,
        client_secret=s.google_client_secret,
        scopes=SCOPES,
    )
    # expiry를 넣어줘야 creds.valid가 "실제 만료 여부"를 정확히 판단한다.
    if expiry is not None:
        creds.expiry = expiry
    return creds


def ensure_fresh(creds: Credentials) -> Credentials:
    """만료(또는 access_token 없음)면 refresh_token으로 새 access_token 발급."""
    if not creds.valid:
        creds.refresh(google_requests.Request())
    return creds
