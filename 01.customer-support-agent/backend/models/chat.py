from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field


# ── Request models ────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"
    user_id: str = "anonymous"


class ConfirmRequest(BaseModel):
    """POST /chat/confirm 요청 바디 (사용자 본인이 환불 신청을 확인/취소)."""
    thread_id: str
    decision: Literal["approve", "reject"]
    user_id: str = "anonymous"


# ── Response data models (discriminated by `status`) ─────────────────────────

class CompletedChatData(BaseModel):
    status: Literal["completed"]
    response: str
    thread_id: str


class BlockedChatData(BaseModel):
    status: Literal["blocked"]
    response: str
    thread_id: str


class ConfirmationInfo(BaseModel):
    tool: str
    args: dict[str, Any]


class ConfirmationRequiredData(BaseModel):
    status: Literal["confirmation_required"]
    thread_id: str
    confirmation: ConfirmationInfo


ChatData = Annotated[
    Union[CompletedChatData, BlockedChatData, ConfirmationRequiredData],
    Field(discriminator="status"),
]


# ── Response models ───────────────────────────────────────────────────────────

class ChatResponse(BaseModel):
    success: bool
    message: str
    data: ChatData


class ConfirmData(BaseModel):
    status: Literal["submitted", "cancelled"]
    response: str
    thread_id: str


class ConfirmResponse(BaseModel):
    success: bool
    message: str
    data: ConfirmData
