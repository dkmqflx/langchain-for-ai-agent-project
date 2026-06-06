# Phase 6 학습 가이드 — 내 환불 조회 (사용자)

**목표**: 사용자가 본인 환불 신청 상태를 조회하는 마이페이지.

> 가장 단순한 읽기 전용 화면. Phase 5(관리자가 상태 변경) 결과를 사용자 입장에서 확인.

---

## 학습 흐름도

```
app/refunds/page.tsx
   └── GET /refunds?user_id=... → 본인 신청 목록 + 상태(pending/approved/rejected)
```

---

## Step 1: 쿼리 파라미터로 본인 신청 조회 (5분)

```ts
import { apiFetch } from "@/lib/api";
const data = await apiFetch<{ refunds: Refund[] }>(`/refunds?user_id=${encodeURIComponent(userId)}`);
```
- `user_id`는 채팅/환불 신청 때 쓰던 값을 재사용하거나, 입력 필드로 받습니다.
- `encodeURIComponent`로 쿼리 인코딩(특수문자 안전).
- 상태값(`pending`/`approved`/`rejected`)은 백엔드 `RefundStatus` 단일 출처와 의미 일치.

### 학습 질문
- [ ] 왜 `user_id`를 쿼리 파라미터로 보내나? (조회 필터)
- [ ] 운영 환경이라면 `user_id`를 클라이언트가 보내는 게 안전할까? (인증으로 대체 — 지금은 학습용 한계로 유지)

---

## Step 2: 상태 표시 (5분)

- 상태별 배지(shadcn `Badge`, `components/ui/badge.tsx`)로 시각화:
  `pending`(대기) / `approved`(승인) / `rejected`(거절).
- 빈 목록("신청 내역 없음") 처리.

---

## 검증

- [ ] 신청한 `user_id`로 조회 → 신청 내역과 현재 상태가 보인다.
- [ ] Phase 5에서 관리자가 바꾼 상태가 반영된다(승인/거절).
- [ ] 신청 없는 `user_id` → 빈 상태 메시지.

---

## 검증 체크리스트 (개념)
- [ ] 쿼리 파라미터 기반 조회를 안다.
- [ ] 상태 enum을 백엔드와 일치시키는 이유를 안다.
- [ ] 빈/로딩/에러 상태 처리를 안다.

---

## 커밋
```
feat(frontend): user refund status page
```

## 다음 단계
- **Phase 7**: 4개 화면을 하나의 앱으로 묶고 다듬기(네비게이션·레이아웃·접근성).
