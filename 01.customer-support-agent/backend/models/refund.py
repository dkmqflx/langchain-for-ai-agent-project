from typing import Literal

from pydantic import BaseModel, Field

from agent.refund_store import RefundStatus


class AdminDecisionRequest(BaseModel):
    """POST /approve 요청 바디 (관리자가 환불 신청을 승인/거절)."""
    refund_id: str
    decision: Literal["approve", "reject"]


# ── Response data models ──────────────────────────────────────────────────────

class RefundItem(BaseModel):
    """환불 신청 1건 (routers.refund._to_item 의 출력과 동일한 구조)."""
    id: str = Field(examples=["rf-1"])
    user_id: str = Field(examples=["user-123"])
    order_id: str = Field(examples=["ORD-2026-0042"])
    amount: float = Field(examples=[49900.0])
    reason: str = Field(examples=["제품 불량으로 환불 요청"])
    status: RefundStatus = Field(examples=["pending"])
    created_at: str = Field(examples=["2026-06-04T09:30:00+00:00"])
    decided_at: str | None = Field(default=None, examples=["2026-06-04T10:15:00+00:00"])


class PendingData(BaseModel):
    pending: list[RefundItem]


class RefundsData(BaseModel):
    refunds: list[RefundItem]


# ── Response models (envelope: {data, isSuccess, code, message}) ──────────────

class PendingResponse(BaseModel):
    data: PendingData
    isSuccess: bool = True
    code: str = "SUCCESS"
    message: str = Field(examples=["Pending refund requests retrieved successfully"])


class RefundDecisionResponse(BaseModel):
    data: RefundItem
    isSuccess: bool = True
    code: str = "SUCCESS"
    message: str = Field(examples=["Refund decision applied successfully"])


class RefundsResponse(BaseModel):
    data: RefundsData
    isSuccess: bool = True
    code: str = "SUCCESS"
    message: str = Field(examples=["Refund requests retrieved successfully"])
