# Phase 5 학습 가이드 — 관리자 환불 승인 큐

**목표**: 승인 대기(pending) 환불 신청 목록을 보고 승인/거절한다.

> 중요: 이건 **LangGraph 재개가 아니라 일반 CRUD**입니다.
> (LangGraph HITL 재개는 Phase 3의 `/chat/confirm`이 담당. 여기 `/approve`는 환불 저장소 상태를 바꾸는 별개 흐름.)

---

## 학습 흐름도

```
app/admin/refunds/page.tsx
   ├── GET /pending → 대기 목록 테이블 (user_id, order_id, amount, reason, created_at)
   └── 각 행: 승인/거절 → POST /approve { refund_id, decision } → 목록 갱신
```

---

## Step 1: 대기 목록 불러오기 (5분)

```ts
import { apiFetch } from "@/lib/api";
const data = await apiFetch<{ pending: PendingRefund[] }>("/pending");
```
- 필드(`user_id`, `order_id`, `amount`, `reason`, `created_at`)와 응답 형태는
  백엔드 `routers/refund.py` + `agent/refund_store.py`의 모델로 확인.
- 상태/열거 타입은 백엔드 단일 출처(`RefundStatus`)와 의미를 맞춥니다.

---

## Step 2: 승인/거절 (POST /approve) (10분)

```ts
await apiFetch("/approve", {
  method: "POST",
  body: JSON.stringify({ refund_id, decision: "approve" /* | "reject" */ }),
});
```
- **이미 처리된 신청을 다시 승인하면 백엔드 400** → `apiFetch`가 `ApiError`를 던짐 → 안내 메시지로 처리.
- 처리 후: 목록 refetch 또는 해당 행을 낙관적 업데이트.

### Phase 3의 `/chat/confirm`과 헷갈리지 말 것
| | Phase 3 `/chat/confirm` | Phase 5 `/approve` |
|---|---|---|
| 주체 | 고객(본인확인) | 관리자(승인) |
| 키 | `thread_id` (LangGraph 상태 재개) | `refund_id` (환불 저장소 레코드) |
| 성격 | 에이전트 흐름 재개 | 일반 상태 변경 CRUD |

### 학습 질문
- [ ] `/chat/confirm`과 `/approve`가 둘 다 "승인"인데 왜 별개 엔드포인트인가?
- [ ] 이미 처리된 신청을 또 승인하면? (400 → 사용자에게 어떻게 알릴까)

---

## 검증

- [ ] Phase 3에서 승인(본인확인 통과)한 신청이 `/pending` 목록에 보인다.
- [ ] 승인/거절 → 상태가 바뀌고 목록에서 사라지거나 상태 표시.
- [ ] 이미 처리된 항목 재처리 시도 → 400 안내.

---

## 검증 체크리스트 (개념)
- [ ] `/approve`(refund_id)와 `/chat/confirm`(thread_id)의 차이를 안다.
- [ ] 400(중복 처리) 같은 에러를 `ApiError`로 처리하는 법을 안다.
- [ ] 처리 후 목록 갱신 전략(refetch vs 낙관적 업데이트)을 안다.

---

## 커밋
```
feat(frontend): admin refund approval queue
```

## 다음 단계
- **Phase 6**: 사용자가 본인 환불 상태를 조회하는 마이페이지.
