# Phase 3 학습 가이드 — 차단 + 환불 본인확인 이벤트 처리 ⚠️

> **목표**: Phase 2의 채팅 UI에서 아직 무시했던 두 이벤트 —
> `blocked`(욕설 차단)·`confirmation_required`(환불 본인확인)을 처리한다.
> 이 프로젝트 **고유 도메인 흐름**이라 가장 까다로운 단계다.
>
> 손대는 파일: `app/page.tsx`(이벤트 분기 확장) + `lib/chat.ts`의 `confirmChat`(이미 있음) 사용.

---

## 학습 흐름도

```
욕설 입력 ─────────────→ event: blocked        → 차단 안내 말풍선/배너 표시 (끝)

"환불해줘 ORD-123" ───→ event: confirmation_required {tool, args, thread_id}
                         ↓ 확인 카드 렌더 (주문/금액/사유 + 승인/취소 버튼)
                         ↓ 사용자가 승인/취소
                       confirmChat({thread_id, decision, user_id})  →  POST /chat/confirm
                         ↓ 응답 {status:"submitted"|"cancelled", response}
                       채팅 후속 메시지로 반영 (끝)
```

핵심 한 줄: **"차단은 보여주기만, 환불 확인은 별도 fetch로 흐름을 재개."**

---

## Step 1: `blocked` 처리 (5분)

욕설 입력 시 백엔드 가드레일이 모델 호출 없이 단락하고 `event: blocked {response}`를 보냅니다.

```ts
case "blocked":
  next[last] = { role: "assistant", content: evt.response };  // 차단 안내 그대로 표시
  break;
```
- 모델이 안 돌았으므로 `token`/`message`는 오지 않습니다. `blocked` → 곧이어 스트림 종료.
- UI 강조가 필요하면 배너/경고색 말풍선으로 구분(선택).

### 학습 질문
- [ ] 차단 시 왜 `token`이 한 개도 안 오나? (힌트: before_agent 가드레일이 모델 전에 단락)

---

## Step 2: `confirmation_required` → 확인 카드 (10분)

환불 신청(`submit_refund_request`)은 HITL로 **일시정지**되고, 백엔드가
`event: confirmation_required {thread_id, tool, args}`를 보냅니다. `args`에는 `order_id`, `amount`, `reason` 등이 들어있습니다.

```ts
case "confirmation_required":
  setPending({ threadId: evt.thread_id, tool: evt.tool, args: evt.args });
  break;
```
- 이걸 받아 **shadcn `Card`**로 "환불 신청을 진행할까요?"를 그리고, `args`(주문/금액/사유)를 표시,
  **승인/취소 버튼**을 둡니다.
- 이때 스트림은 이미 끝난 상태입니다(일시정지). 재개는 **별도 fetch**(`/chat/confirm`)로 합니다.

---

## Step 3: 승인/취소 → `confirmChat` (재개) (15분)

```ts
async function decide(decision: "approve" | "reject") {
  if (!pending) return;
  const { response, status } = await confirmChat({
    thread_id: pending.threadId,   // confirmation_required에서 받은 값을 그대로
    decision,
    user_id: userId,
  });
  setPending(null);
  setMessages((m) => [...m, { role: "assistant", content: response }]);  // 후속 메시지 반영
  // status: "submitted"(접수) | "cancelled"(취소)
}
```

### ⚠️ `thread_id`가 흐름의 연결고리
- `confirmation_required`에서 받은 `thread_id`를 **그대로** `confirmChat`에 넘겨야
  백엔드 checkpointer가 "어느 대화에서 멈췄는지" 찾아 재개합니다. 새로 만들면 안 됩니다.

> 참고: `user_id`를 클라이언트가 다시 보내는 알려진 한계는 백엔드와 동일하게 유지(학습용).

### 학습 질문
- [ ] confirm 호출에 왜 **같은** `thread_id`를 써야 하나? (힌트: 멈춘 상태 조회 키)
- [ ] confirm은 왜 스트림이 아니라 일반 fetch인가? (힌트: 단발성 결정 전송)

---

## 검증

- [ ] 욕설 입력 → 차단 메시지 표시(모델 호출 없이 단락).
- [ ] "환불해줘 ORD-123" 류 → 확인 카드(주문/금액/사유) 표시.
  - [ ] 승인 → "접수(submitted)" 후속 메시지.
  - [ ] 취소 → "취소(cancelled)" 후속 메시지.
- [ ] 승인 시 백엔드 `GET /pending`에 신청이 쌓이는지 교차 확인(Phase 5와 연결).

## 검증 체크리스트 (개념 이해)
- [ ] `blocked`는 "표시만", `confirmation_required`는 "별도 fetch로 재개"임을 안다.
- [ ] `thread_id`가 일시정지된 흐름을 재개하는 키임을 안다.
- [ ] 승인/취소 후 채팅 흐름으로 복귀하는 상태 전환을 설명할 수 있다.

---

## 커밋

```
feat(frontend): handle blocked + refund confirmation sse events
```

## 다음 단계
- **Phase 4**: 관리자 문서 업로드 화면(`POST /upload`, `GET /documents`).
