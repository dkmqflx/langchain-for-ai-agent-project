"""
Phase 5: 환불 신청 관리 라우터 (관리자 승인 + 사용자 상태 조회)

이 라우터는 LangGraph interrupt와 무관한 일반 CRUD입니다.
환불 신청 레코드(refund_store)를 대상으로 동작합니다.

  GET  /pending  → (관리자) 승인 대기 중인 신청 목록
  POST /approve  → (관리자) 신청 승인/거절 → 레코드 상태 변경
  GET  /refunds  → (사용자) 본인 신청 상태 조회 (마이페이지용)

사용자 본인 확인(HITL interrupt/resume)은 여기가 아니라 chat 라우터(/chat, /chat/confirm)에
있습니다. 두 "승인"을 분리한 이유:
  - 사용자 확인: 동기, 채팅 중 즉시 (관리자를 기다리지 않음)
  - 관리자 승인: 비동기, 백오피스에서 나중에 처리
"""

from fastapi import APIRouter, HTTPException

from agent.refund_store import (
    RefundRequest,
    get_request,
    list_by_user,
    list_pending,
    set_decision,
)
from models.refund import AdminDecisionRequest

router = APIRouter()


def _to_item(req: RefundRequest) -> dict:
    """RefundRequest dataclass → 응답용 dict."""
    return {
        "id": req.id,
        "user_id": req.user_id,
        "order_id": req.order_id,
        "amount": req.amount,
        "reason": req.reason,
        "status": req.status,
        "created_at": req.created_at,
        "decided_at": req.decided_at,
    }


@router.get("/pending")
async def list_pending_refunds():
    """(관리자) 승인 대기(pending) 중인 환불 신청 목록."""
    pending = [_to_item(r) for r in list_pending()]
    return {
        "success": True,
        "message": "Pending refund requests retrieved successfully",
        "data": {"pending": pending},
    }


@router.post("/approve")
async def decide_refund(request: AdminDecisionRequest):
    """
    (관리자) 환불 신청을 승인 또는 거절한다.

    LangGraph 재개가 아니라 refund_store의 레코드 상태만 변경한다.
    사용자는 이 결정을 GET /refunds로 나중에 확인한다.
    """
    req = get_request(request.refund_id)
    if req is None:
        raise HTTPException(status_code=404, detail="해당 신청번호를 찾을 수 없습니다.")
    if req.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"이미 처리된 신청입니다 (현재 상태: {req.status}).",
        )

    updated = set_decision(request.refund_id, request.decision)
    return {
        "success": True,
        "message": "Refund decision applied successfully",
        "data": _to_item(updated),
    }


@router.get("/refunds")
async def my_refunds(user_id: str):
    """(사용자) 본인이 신청한 환불 목록과 상태를 조회한다 (마이페이지용)."""
    refunds = [_to_item(r) for r in list_by_user(user_id)]
    return {
        "success": True,
        "message": "Refund requests retrieved successfully",
        "data": {"refunds": refunds},
    }
