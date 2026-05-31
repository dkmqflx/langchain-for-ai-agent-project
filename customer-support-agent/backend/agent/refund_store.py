"""
Phase 5: 환불 신청 레코드 저장소

LangGraph의 checkpointer(대화 일시정지/재개)와는 완전히 별개의 저장소입니다.
  - checkpointer: 사용자 본인 확인을 위한 대화 일시정지 (동기, thread_id 기반)
  - refund_store: 접수된 환불 "신청" 레코드 (비동기 관리자 승인 대상)

흐름:
  ① 사용자가 환불 요청 → 본인 확인(HITL) → 확인 시 submit_refund_request 도구가
     create_request()로 레코드 생성 (status="pending")
  ② 관리자가 list_pending()으로 대기 목록 검토 → set_decision()으로 승인/거절
  ③ 사용자가 list_by_user()로 본인 신청 상태 조회

학습용이라 모듈 레벨 dict를 사용합니다 (서버 재시작 시 사라짐).
프로덕션에서는 DB 테이블(refund_requests)로 교체해야 합니다.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

RefundStatus = Literal["pending", "approved", "rejected"]


@dataclass
class RefundRequest:
    """환불 신청 1건."""
    id: str
    user_id: str
    order_id: str
    amount: float
    reason: str
    status: RefundStatus = "pending"
    created_at: str = ""
    decided_at: str | None = None


# [모듈 레벨 저장소] 신청번호(rf-N) → 레코드
_refunds: dict[str, RefundRequest] = {}
_counter = 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_request(user_id: str, order_id: str, amount: float, reason: str) -> RefundRequest:
    """새 환불 신청을 접수한다 (status="pending")."""
    global _counter
    _counter += 1
    refund_id = f"rf-{_counter}"
    req = RefundRequest(
        id=refund_id,
        user_id=user_id,
        order_id=order_id,
        amount=amount,
        reason=reason,
        status="pending",
        created_at=_now(),
    )
    _refunds[refund_id] = req
    return req


def get_request(refund_id: str) -> RefundRequest | None:
    """신청번호로 레코드 조회 (없으면 None)."""
    return _refunds.get(refund_id)


def list_pending() -> list[RefundRequest]:
    """승인 대기(pending) 중인 신청 목록 (관리자용)."""
    return [r for r in _refunds.values() if r.status == "pending"]


def list_by_user(user_id: str) -> list[RefundRequest]:
    """특정 사용자의 모든 신청 목록 (사용자 상태 조회용)."""
    return [r for r in _refunds.values() if r.user_id == user_id]


def set_decision(refund_id: str, decision: Literal["approve", "reject"]) -> RefundRequest:
    """
    관리자의 승인/거절을 레코드에 반영한다.

    호출 전에 get_request로 존재 + pending 여부를 확인할 것
    (이 함수는 단순히 상태만 갱신).
    """
    req = _refunds[refund_id]
    req.status = "approved" if decision == "approve" else "rejected"
    req.decided_at = _now()
    return req
