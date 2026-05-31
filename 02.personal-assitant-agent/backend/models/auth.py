"""
auth 라우터의 요청/응답 Pydantic 모델

FastAPI 공식 권장(model-response-model): 엔드포인트마다 응답 모델을 선언해
  - 자동 문서화(/docs)와 응답 검증을 받고
  - 의도치 않은 필드(토큰 등)가 새어 나가지 않게 한다.
"""

from pydantic import BaseModel


class GmailProfile(BaseModel):
    """GET /auth/me 응답 — 저장된 토큰으로 실제 Gmail에서 가져온 프로필."""

    email: str
    messages_total: int
    threads_total: int
    history_id: str
