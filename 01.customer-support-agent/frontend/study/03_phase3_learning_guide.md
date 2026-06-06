# Phase 3 학습 가이드 — 커스텀 data part 처리 (욕설 차단 + 환불 본인확인)

**목표**: Phase 1에서 백엔드가 내보내는 `data-blocked` / `data-confirmation` 파트를 프론트 UI에서 처리한다.
이 프로젝트 **고유 도메인 흐름**이라 가장 까다로운 단계.

> ⚠️ 전제: Phase 1(백엔드가 두 파트를 emit)과 Phase 2(useChat 연결)가 끝나 있어야 합니다.

---

## 학습 흐름도

```
사용자 입력
   ├── 욕설        → 백엔드가 모델 호출 없이 단락 → data-blocked 파트
   │                  → 프론트: 차단 안내 배너/말풍선 표시 (끝)
   │
   └── "환불해줘"  → 백엔드가 본인확인 필요 판단 → data-confirmation 파트
                      → 프론트: <Confirmation> UI 표시 (tool/args)
                          ├── 승인 → POST /chat/confirm {decision:"approve"} → "접수(submitted)"
                          └── 취소 → POST /chat/confirm {decision:"reject"}  → "취소(cancelled)"
```

핵심 구분: **`data-blocked`은 표시만, `data-confirmation`은 표시 + 별도 fetch(/chat/confirm)로 후속 동작.**

---

## Step 1: data 파트를 messages에서 꺼내기 (10분)

v6에서 커스텀 data 파트는 `message.parts`에 `type: "data-<이름>"` 형태로 섞여 들어옵니다(Phase 1 매핑 참조).

```ts
for (const part of message.parts) {
  if (part.type === "text") { /* 일반 답변 */ }
  else if (part.type === "data-blocked") {
    // part.data === { reason: "..." }
  }
  else if (part.type === "data-confirmation") {
    // part.data === { tool, args, thread_id }
  }
}
```
- 데이터 형태는 `{ type, id?, data, transient? }`. 우리가 쓰는 건 `data` 안의 페이로드.
- `data`의 실제 키(`reason`, `tool`, `args`, `thread_id`)는 **Phase 1에서 백엔드가 넣은 그대로**입니다 — 양쪽을 같은 표로 맞추세요.

### 학습 질문
- [ ] 표준 `text` 파트와 커스텀 `data-*` 파트를 어떻게 구분하나?
- [ ] `transient` 파트는 어떤 의미인가? (히스토리에 남기지 않는 일회성 신호)

---

## Step 2: `data-blocked` — 차단 안내 표시 (5분)

가장 단순. 모델 호출이 없었으므로 답변 텍스트 대신 안내만 보여줍니다.

- `part.data.reason`을 말풍선 또는 경고 배너로 렌더.
- shadcn `Alert`(`components/ui/alert.tsx`, 이미 설치됨) 활용 가능.
- 후속 동작 없음 — 사용자가 다시 입력하면 끝.

### 학습 질문
- [ ] 차단 메시지를 "AI 답변 말풍선"처럼 보이게 할까, "시스템 경고"처럼 보이게 할까? (UX 결정)

---

## Step 3: `data-confirmation` — 환불 본인확인 (핵심) (15분)

### 3-1. Confirmation UI 렌더 (검증된 export 이름)
`components/ai-elements/confirmation.tsx`가 실제로 export하는 것들:
```
Confirmation, ConfirmationRequest, ConfirmationTitle,
ConfirmationActions, ConfirmationAction,
ConfirmationAccepted, ConfirmationRejected
```
- `data-confirmation`을 감지하면 "환불 신청을 진행할까요?"를 `tool`/`args`와 함께 렌더.
- 정확한 props/합성 방식은 `confirmation.tsx`를 직접 열어 확인(상상 금지).

### 3-2. 승인/취소 → `POST /chat/confirm` (별도 fetch)
> ⚠️ **이건 `useChat` 스트림이 아니라 별도 HTTP 요청**입니다. Phase 0에서 만든 `lib/api.ts`의 `apiFetch` 사용.

```ts
import { apiFetch } from "@/lib/api";

await apiFetch("/chat/confirm", {
  method: "POST",
  body: JSON.stringify({
    thread_id,                       // data-confirmation에서 받은 값 그대로
    decision: "approve" /* | "reject" */,
    user_id,                         // 채팅에서 쓰던 값
  }),
});
// 응답 status: "submitted" | "cancelled" → 채팅에 후속 메시지로 반영
```
- `apiFetch`는 봉투(`{data,isSuccess,code,message}`)를 벗겨 `data`만 돌려줍니다(실패 시 `ApiError`).

### 3-3. 상태 관리
- `data-confirmation`에서 받은 `thread_id`를 **그대로** confirm 호출에 사용 → 백엔드가 멈춰둔 LangGraph 상태를 재개.
- confirm 응답을 받으면 결과 메시지를 채팅에 추가(`setMessages`)하고 다시 일반 채팅 흐름으로 복귀.

> 참고(알려진 한계, 학습용 유지): `args.user_id`를 클라이언트가 다시 보내는 구조는 백엔드와 동일하게 둡니다.

### 학습 질문
- [ ] 승인이 왜 스트림이 아니라 별도 fetch인가? (HITL 재개는 새 요청이라서)
- [ ] `thread_id`를 잘못 보내면? (다른 대화의 상태를 재개하거나 실패)

---

## 검증

- [ ] 욕설 입력 → 차단 메시지 표시(모델 호출 없이 단락).
- [ ] "환불해줘 ORD-123" 류 입력 → `Confirmation` UI 표시 →
  - [ ] 승인 → "신청 접수(submitted)" 반영
  - [ ] 취소 → "취소(cancelled)" 반영
- [ ] 승인 시 백엔드 `GET /pending`에 신청이 쌓이는지 교차 확인(Phase 5와 연결).

---

## 검증 체크리스트 (개념)
- [ ] `message.parts`에서 `data-*` 파트를 꺼내는 법을 안다.
- [ ] `data-blocked`(표시만)와 `data-confirmation`(표시+fetch)의 차이를 안다.
- [ ] confirm이 `useChat`이 아니라 `apiFetch`(별도 HTTP)인 이유를 안다.
- [ ] `thread_id`가 HITL 상태 재개의 키라는 걸 안다.

---

## 커밋
```
feat(frontend): handle blocked + refund confirmation data parts
```

## 다음 단계
- **Phase 4**: 관리자 문서 업로드(스트리밍 없는 단순 폼).
- **Phase 5**: 여기서 승인한 환불이 쌓이는 관리자 승인 큐.
