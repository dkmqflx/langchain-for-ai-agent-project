from typing import Literal

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"
    user_id: str = "anonymous"


class ConfirmRequest(BaseModel):
    """POST /chat/confirm 요청 바디 (사용자 본인이 환불 신청을 확인/취소)."""
    thread_id: str
    decision: Literal["approve", "reject"]
    user_id: str = "anonymous"
