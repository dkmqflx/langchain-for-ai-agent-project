"""
users 테이블 (SQLAlchemy 2.0 Mapped 스타일)

설계: "표 1개" 방식 (한 사용자 = 한 구글 계정 = 한 토큰셋, 1:1 관계).
  사용자 식별 정보와 OAuth 토큰을 한 테이블에 통합. Phase 1 학습용으로 가장 단순.
  (실서비스에서 토큰 이력/다중 제공자가 필요하면 oauth_tokens 테이블로 분리 가능.)

컬럼:
  - google_sub:        구글이 주는 변하지 않는 사용자 고유 ID (id_token의 'sub' 클레임).
                       이메일은 바뀔 수 있으므로 sub를 진짜 식별자로 사용.
  - email:             표시/조회용 이메일.
  - refresh_token_enc: Fernet으로 암호화된 refresh token (절대 평문 저장 X).
  - access_token:      현재 access token (1시간짜리, 만료되면 갱신해 덮어씀).
  - token_expiry:      access token 만료 시각 (naive UTC — 구글 라이브러리와 동일 포맷).
"""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.session import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    google_sub: Mapped[str] = mapped_column(String, unique=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)

    refresh_token_enc: Mapped[str] = mapped_column(String)
    access_token: Mapped[str | None] = mapped_column(String, nullable=True)
    token_expiry: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
