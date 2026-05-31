"""
환경변수(설정) 로딩 — pydantic-settings 공식 패턴

왜 pydantic-settings를 쓰는가:
  - os.getenv()를 흩뿌리는 대신, 한 곳(Settings)에 타입과 함께 모아 관리.
  - 필수 값이 빠지면 서버 시작 시 즉시 에러 → 런타임에 None으로 터지는 일 방지.
  - @lru_cache로 한 번만 읽어 재사용 (FastAPI 공식 권장: config-pydantic-settings).

.env 위치:
  backend/ 의 상위 폴더(02.personal-assitant-agent/.env)에서 읽는다.
  (프로젝트 1과 동일하게 .env를 backend 밖에 두는 컨벤션)
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/config.py → parent(backend/) → parent(02.personal-assitant-agent/) / .env
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """앱 전역 설정. 모든 값은 .env 또는 환경변수에서 주입된다."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",  # 미래 Phase에서 쓸 다른 키가 .env에 있어도 무시
    )

    # DB — SQLAlchemy + psycopg3 드라이버 (postgresql+psycopg://)
    database_url: str

    # Google OAuth2 (Google Cloud Console에서 발급)
    google_client_id: str
    google_client_secret: str
    oauth_redirect_uri: str = "http://localhost:8000/auth/callback"

    # refresh_token 암호화용 Fernet 키
    token_encryption_key: str

    # SessionMiddleware 서명 키 (OAuth state CSRF 방어)
    session_secret: str


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤. 최초 1회만 .env를 읽고 이후 캐시 재사용."""
    return Settings()  # type: ignore[call-arg]
