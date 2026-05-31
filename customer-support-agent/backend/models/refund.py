from typing import Literal

from pydantic import BaseModel


class AdminDecisionRequest(BaseModel):
    """POST /approve 요청 바디 (관리자가 환불 신청을 승인/거절)."""
    refund_id: str
    decision: Literal["approve", "reject"]
