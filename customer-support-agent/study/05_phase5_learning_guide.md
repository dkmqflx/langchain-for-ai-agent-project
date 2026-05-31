# Phase 5 학습 가이드 — Human-in-the-loop (환불 신청 & 승인)

이 가이드는 Phase 5의 파일들을 의존성 순서대로 학습할 수 있도록 구성되었습니다.

---

## Phase 5에서 새로 추가된 것

Phase 4까지는 에이전트가 **모든 작업을 혼자 끝까지** 처리했습니다.

```
[Phase 4 문제]

고객: "주문 ORD-123, 5만원 환불해줘"
Agent: "네, 환불 처리했습니다!" ← 아무 확인 없이 바로 돈이 나감 💸
```

Phase 5는 환불 같은 **민감한 작업에 두 단계의 사람 개입**을 넣습니다.

```
[Phase 5 해결]

① 고객 본인 확인 (즉시)
   고객: "ORD-123 5만원 환불해줘"
   Agent: "정말 환불 신청할까요?" ⏸️
   고객: "예" ▶️
   Agent: "신청이 접수되었습니다 (신청번호 rf-1). 검토 후 알려드릴게요"

② 관리자 승인 (나중에, 비동기)
   관리자: 대기 목록에서 rf-1 확인 → 승인/거절

③ 고객이 결과 확인 (나중에)
   고객: 마이페이지에서 "rf-1: 승인됨" 확인
```

---

## ⭐ 가장 중요한 설계 결정: "사람"이 둘이다

처음에 흔히 빠지는 함정이 있습니다:

```
[잘못된 설계] 관리자 승인을 "그 자리에서" 기다리게 함

고객: "환불해줘" → 에이전트 일시정지 → (관리자 올 때까지...) → 응답
                                          ↑
                        관리자는 실시간으로 채팅을 안 보고 있다!
                        고객이 몇 시간을 기다려야 할 수도 있음 ❌
```

핵심 통찰: 환불에는 **성격이 다른 두 개의 "승인"** 이 있습니다.

| 구분 | 누가 | 언제 | 방식 |
|------|------|------|------|
| **본인 확인** | 고객 자신 | 즉시 (채팅 중) | 동기 — "정말 신청?" |
| **업무 승인** | 관리자 | 나중에 | **비동기** — 백오피스 검토 |

그리고 또 하나: **"환불 신청 접수"는 위험한 작업이 아닙니다.** 그냥 신청서 한 장을 접수하는 것뿐이죠 (status=pending). 실제로 돈이 나가는 건 관리자가 승인할 때입니다.

**비유: 회사 휴가 신청**

```
직원이 휴가 신청서를 낸다 (신청 접수 = 안 위험함)
  → "정말 이 날짜로 낼까요?" 본인이 한 번 확인 (즉시)
  → 신청서 제출됨 (대기 상태)
팀장이 나중에 결재한다 (승인/반려 = 비동기)
직원은 나중에 결재 결과를 확인한다

직원이 신청서 내자마자 팀장 자리로 달려가
"지금 당장 결재해주세요" 하고 서 있는 건 말이 안 된다.
```

그래서 Phase 5는 둘을 **분리**합니다:
- **본인 확인** = LangGraph interrupt/resume (채팅 안에서 즉시)
- **관리자 승인** = 별도 저장소(refund_store) + 관리자 엔드포인트 (LangGraph와 무관)

---

## 학습 흐름도

```
[새로 추가/수정된 파일]
agent/refund_store.py  → 환불 '신청' 레코드 저장소 (관리자 승인 대상)
agent/tools.py         → submit_refund_request 도구 (신청 접수, 레코드 생성)
agent/agent.py         → HITL을 submit_refund_request에 걸어 본인 확인
agent/middleware.py    → SYSTEM_PROMPT에 신청 안내
routers/chat.py        → interrupt 감지 → confirmation_required + /chat/confirm
routers/refund.py      → GET /pending, POST /approve(관리자), GET /refunds(사용자)
main.py                → refund_router 등록

[① 본인 확인 흐름 — 동기]
POST /chat {"message": "ORD-123 5만원 환불"}
     ↓
모델이 submit_refund_request 호출 시도
     ↓
HumanInTheLoopMiddleware가 실행 직전 ⏸️ interrupt
     ↓
chat.py: status="confirmation_required" 반환 (아직 신청 안 됨!)
     ↓
POST /chat/confirm {"thread_id", "decision": "approve"}
     ↓
▶️ 재개 → submit_refund_request 실행 → refund_store에 레코드 생성(pending)
     ↓
status="submitted" "신청번호 rf-1 접수됨"

[② 관리자 승인 흐름 — 비동기]
GET  /pending                                  → 대기 목록 [rf-1 ...]
POST /approve {"refund_id": "rf-1", "decision": "approve"}
     ↓
refund_store: rf-1.status = "approved"

[③ 사용자 조회 흐름]
GET /refunds?user_id=cust-1  → [{"id": "rf-1", "status": "approved", ...}]
```

---

## 사전 지식: 일시정지와 재개는 어떻게 가능한가?

본인 확인(①)은 **"멈췄다가 사용자 응답을 받고 이어서 실행"** 합니다. 이게 어떻게 가능할까요?

**비유: 게임의 세이브 / 로드**

```
게임 중간에 저장(세이브)하고 꺼도, 나중에 불러오기(로드)하면
그 지점부터 이어서 플레이할 수 있다.

checkpointer (InMemorySaver) = 세이브 파일 저장 장치
thread_id                    = 어떤 세이브 파일인지 식별하는 이름
interrupt()                  = "여기서 멈추고 저장해"
Command(resume=...)          = "그 세이브 불러와서 이어서 해"
```

핵심: interrupt가 동작하려면 **checkpointer + thread_id가 필수**입니다.
Phase 3에서 이미 둘 다 만들어 뒀으니, Phase 5는 "어떤 도구를 멈출지"만 추가합니다.

---

## Step 1: `agent/refund_store.py` 읽기 — 신청 저장소 (15분)

### 목표

관리자 승인 대상인 "환불 신청 레코드"가 LangGraph와 별개의 저장소에 산다는 점을 이해

---

### 핵심 개념 1: 두 저장소는 완전히 다르다

```
checkpointer (InMemorySaver)   refund_store (이 파일)
= 대화 일시정지 상태             = 환불 '신청' 레코드
= 본인 확인용 (thread_id)        = 관리자 승인 대상
= LangGraph가 관리               = 우리가 직접 만든 dict
```

이 둘을 헷갈리면 안 됩니다. 본인 확인(interrupt)이 끝난 **뒤에** 신청 레코드가 생깁니다.

---

### 핵심 개념 2: 레코드 구조와 상태

```python
@dataclass
class RefundRequest:
    id: str            # "rf-1", "rf-2" ... (카운터로 생성)
    user_id: str
    order_id: str
    amount: float
    reason: str
    status: RefundStatus = "pending"   # pending → approved / rejected
    created_at: str = ""
    decided_at: str | None = None
```

`status`가 신청의 생애주기를 나타냅니다:

```
pending   = 접수됨, 관리자 결정 대기
approved  = 관리자가 승인 (실제 환불 진행)
rejected  = 관리자가 거절
```

**비유: 택배 송장의 배송 상태**

```
접수 → 배송중 → 배송완료 처럼
pending → approved/rejected 로 상태가 바뀐다.
고객은 "조회"로 현재 상태를 본다.
```

---

### 핵심 개념 3: 저장소가 제공하는 함수

```python
create_request(user_id, order_id, amount, reason)  # 신청 접수 (pending 생성)
list_pending()                                     # 관리자용: 대기 목록
list_by_user(user_id)                              # 사용자용: 내 신청 목록
get_request(refund_id)                             # 단건 조회
set_decision(refund_id, decision)                  # 관리자 결정 반영
```

> 학습용이라 모듈 레벨 dict를 씁니다. 서버를 재시작하면 사라집니다.
> 프로덕션에서는 DB 테이블(refund_requests)로 교체해야 합니다.

---

### 학습 질문

- checkpointer와 refund_store는 각각 무엇을 저장하는가?
- 환불 신청 레코드는 본인 확인 "전"에 생길까, "후"에 생길까?
- `status`가 pending이 아닌 신청을 관리자가 또 승인하면 안 되는 이유는?

---

## Step 2: `agent/tools.py` 읽기 — submit_refund_request (15분)

### 목표

도구가 "환불 실행"이 아니라 "신청 접수"만 한다는 점을 이해

---

### 핵심 개념: 이름이 곧 의도다 (process_refund ❌ → submit_refund_request ✅)

```python
@tool
def submit_refund_request(
    order_id: str,
    amount: float,
    reason: str,
    runtime: ToolRuntime[AgentContext],   # user_id 추출용 (자동 주입)
) -> str:
    """고객의 환불·결제 취소 '신청'을 접수합니다."""
    user_id = runtime.context.user_id if runtime.context else "anonymous"
    req = create_request(user_id=user_id, order_id=order_id, amount=amount, reason=reason)
    return f"환불 신청이 접수되었습니다. 신청번호: {req.id}, ..."
```

이 도구는 **돈을 움직이지 않습니다.** `create_request`로 신청 레코드(pending)를 하나 만들 뿐입니다.

```
process_refund (이전): "환불이 완료되었습니다" ← 이미 돈이 나간 것처럼
submit_refund_request : "환불 신청이 접수되었습니다" ← 신청서만 접수
```

`runtime.context.user_id`로 **누가** 신청했는지 기록합니다. 이게 있어야 나중에 그 사용자가 `GET /refunds`로 본인 신청을 조회할 수 있습니다.

---

### 학습 질문

- 이 도구가 "환불 완료"가 아니라 "신청 접수"만 하는 게 왜 더 안전할까?
- `runtime.context.user_id`를 기록하지 않으면 어떤 기능이 불가능해질까?

---

## Step 3: `agent/agent.py` 읽기 — 본인 확인용 HITL (15분)

### 목표

HITL interrupt를 "관리자"가 아니라 "사용자 본인" 확인에 쓰는 이유를 이해

---

### 핵심 개념: interrupt_on에 submit_refund_request 등록

```python
from langchain.agents.middleware import HumanInTheLoopMiddleware

middleware=[
    inject_memory,
    HumanInTheLoopMiddleware(
        interrupt_on={
            "submit_refund_request": {"allowed_decisions": ["approve", "reject"]},
        },
    ),
    PIIMiddleware(...),
]
```

`interrupt_on`에 등록된 도구는 **실행 직전에 멈춥니다.** 여기서 멈춰서 받는 확인은
**사용자 본인**의 확인입니다 (관리자 아님):

```
모델: "submit_refund_request(ORD-123, 50000, 불량) 호출할게"
  ↓
HumanInTheLoopMiddleware가 실행 직전 ⏸️ interrupt
  ↓
chat.py가 "정말 신청할까요?"를 사용자에게 물어봄
  ↓
사용자가 /chat/confirm으로 approve/reject ▶️
```

**왜 사용자 본인 확인에 쓰나?**

```
사용자는 지금 채팅창 앞에 있다 → 즉시 답한다 → 빨리 재개된다 ✅
관리자는 채팅을 안 보고 있다 → interrupt로 기다리면 무한정 대기 ❌

→ interrupt(동기 일시정지)는 "그 자리에 있는 사람"인 사용자에게만 적합.
   관리자(자리에 없음)는 비동기 저장소로 처리 (Step 5).
```

> 참고: interrupt가 동작하려면 `checkpointer`가 필수인데, Phase 3에서 추가한
> `InMemorySaver`가 그대로 쓰입니다.

---

### 학습 질문

- 관리자 승인을 interrupt로 처리하면 어떤 문제가 생길까?
- `interrupt_on`에서 `submit_refund_request`를 빼면 어떻게 동작이 바뀔까?

---

## Step 4: `routers/chat.py` 읽기 — 확인 요청 & 재개 (25분)

### 목표

interrupt를 감지해 사용자에게 확인을 요청하고, `/chat/confirm`으로 재개하는 흐름 이해

---

### 핵심 개념 1: interrupt 감지 → confirmation_required

```python
result = await agent.ainvoke({"messages": [("human", request.message)]},
    config={"configurable": {"thread_id": request.thread_id}},
    context=AgentContext(user_id=request.user_id))

# ⚠️ messages[-1] 접근 "전에" interrupt부터 검사
interrupts = result.get("__interrupt__")
if interrupts:
    action = interrupts[0].value["action_requests"][0]   # {name, args, description}
    return {"success": True, "message": "Confirmation required",
            "data": {"thread_id": request.thread_id,
                     "status": "confirmation_required",
                     "confirmation": {"tool": action["name"], "args": action["args"]}}}
```

**순서가 중요한 이유** (멈췄을 때 마지막 메시지는 비어 있음):

```python
# ❌ 위험: 멈췄을 때 messages[-1]은 tool_call만 담은 빈 AIMessage
ai_message = result["messages"][-1].content   # → 빈 문자열을 할루시네이션 검사 → 오류

# ✅ 안전: interrupt를 먼저 검사하고 분기
if result.get("__interrupt__"): return {...}
ai_message = result["messages"][-1].content   # 멈춤 아닐 때만
```

여기서는 **관리자 큐에 저장하지 않습니다.** 멈춤 상태는 checkpointer(thread_id)가 들고 있고,
사용자가 `/chat/confirm`으로 응답하면 그때 재개됩니다.

---

### 핵심 개념 2: /chat/confirm — 사용자 응답으로 재개

```python
@router.post("/chat/confirm")
async def confirm(request: ConfirmRequest):   # {thread_id, decision, user_id}
    result = await agent.ainvoke(
        Command(resume={"decisions": [{"type": request.decision}]}),  # ▶️ 재개
        config={"configurable": {"thread_id": request.thread_id}},
        context=AgentContext(user_id=request.user_id),
    )
    ai_message = result["messages"][-1].content
    status = "submitted" if request.decision == "approve" else "cancelled"
    return {"success": True, "data": {"response": ai_message,
            "thread_id": request.thread_id, "status": status}}
```

```
approve → submit_refund_request 실행 → 신청 레코드 생성(pending) → "submitted"
reject  → 도구 건너뜀 → 레코드 안 생김 → "cancelled"
```

**context(user_id)를 다시 넘기는 이유:**

```
재개하면 도구 실행 후 모델이 한 번 더 호출된다 (최종 답변 생성).
  → inject_memory가 user_id로 선호도를 주입하고,
  → submit_refund_request 도구가 user_id로 신청자를 기록한다.
그래서 /chat/confirm 요청에 user_id를 포함해 context로 다시 전달한다.
```

**비유: 식당에서 주문 재확인**

```
손님: "이 메뉴 매운맛으로 주세요"
점원: "매운맛 확실하세요?" ⏸️ (확인)
손님: "네" ▶️
점원: 주방에 주문 넣음 (신청 접수)

점원이 손님에게 확인받는 것 = /chat/confirm
주방이 요리하는 것(나중) = 관리자 승인
```

---

### 학습 질문

- 멈췄을 때 `result["messages"][-1].content`를 먼저 읽으면 왜 위험한가?
- `/chat/confirm`에 `user_id`를 빼면 무엇이 동작하지 않을까?
- reject를 보내면 refund_store에 레코드가 생길까, 안 생길까?

---

## Step 5: `routers/refund.py` 읽기 — 관리자 승인 & 사용자 조회 (20분)

### 목표

관리자 승인이 LangGraph 재개가 아니라 **레코드 상태 변경**임을 이해

---

### 핵심 개념 1: GET /pending — 관리자 대기 목록

```python
@router.get("/pending")
async def list_pending_refunds():
    pending = [_to_item(r) for r in list_pending()]   # status=="pending"만
    return {"success": True, "data": {"pending": pending}}
```

이건 LangGraph interrupt 목록이 아니라 **refund_store의 pending 레코드** 목록입니다.

---

### 핵심 개념 2: POST /approve — 레코드 상태만 바꾼다

```python
@router.post("/approve")
async def decide_refund(request: AdminDecisionRequest):   # {refund_id, decision}
    req = get_request(request.refund_id)
    if req is None:
        raise HTTPException(404, "신청번호를 찾을 수 없습니다.")
    if req.status != "pending":
        raise HTTPException(400, f"이미 처리된 신청입니다 (현재: {req.status}).")
    updated = set_decision(request.refund_id, request.decision)
    return {"success": True, "data": _to_item(updated)}
```

**Phase 5 본인 확인과 결정적 차이:**

```
사용자 확인 (/chat/confirm): Command(resume=...) → LangGraph 에이전트 재개 ▶️
관리자 승인 (/approve):      refund_store의 status만 변경 (LangGraph 무관)

→ 관리자 승인은 그냥 DB 레코드 UPDATE 한 줄. 에이전트는 관여 안 함.
```

`thread_id`가 아니라 `refund_id`로 식별하는 점에 주목하세요. 관리자는 "어떤 대화"가
아니라 "어떤 신청서"를 처리하는 것이니까요.

---

### 핵심 개념 3: GET /refunds — 사용자 마이페이지

```python
@router.get("/refunds")
async def my_refunds(user_id: str):
    refunds = [_to_item(r) for r in list_by_user(user_id)]
    return {"success": True, "data": {"refunds": refunds}}
```

사용자는 관리자가 처리하기를 채팅창에서 기다리지 않습니다. 나중에 **마이페이지**(이 엔드포인트)에서
본인 신청의 상태(pending/approved/rejected)를 확인합니다. 이것이 "비동기 승인"의 핵심입니다.

---

### 학습 질문

- 관리자 승인이 `Command(resume=...)`가 아니라 단순 상태 변경인 이유는?
- `/approve`가 `thread_id`가 아니라 `refund_id`로 신청을 찾는 이유는?
- 이미 approved된 신청에 또 `/approve`를 보내면 어떻게 처리될까? (힌트: 400)

---

## Step 6: `main.py` 읽기 — 라우터 등록 (5분)

```python
from routers.refund import router as refund_router

app.include_router(chat_router)    # POST /chat, POST /chat/confirm (사용자)
app.include_router(refund_router)  # GET /pending, POST /approve (관리자), GET /refunds (사용자)
```

---

## 전체 흐름 실습 (20분)

```bash
# 1. 서버 실행
cd customer-support-agent/backend
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# === ① 사용자: 환불 요청 → 본인 확인 ===

# 2. 환불 요청 → 확인 요청이 돌아옴 (아직 신청 안 됨)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "주문 ORD-123, 5만원을 제품 불량으로 환불해줘",
       "thread_id": "refund-1", "user_id": "cust-001"}'
# 기대: {"data": {"status": "confirmation_required",
#                 "confirmation": {"tool": "submit_refund_request",
#                                  "args": {"order_id": "ORD-123", ...}}}}

# 3. 본인 확인(승인) → 신청 접수
curl -X POST http://localhost:8000/chat/confirm \
  -H "Content-Type: application/json" \
  -d '{"thread_id": "refund-1", "decision": "approve", "user_id": "cust-001"}'
# 기대: {"data": {"status": "submitted", "response": "환불 신청이 접수되었습니다. 신청번호: rf-1 ..."}}

# === ② 관리자: 대기 목록 확인 → 승인 ===

# 4. 대기 목록 (관리자)
curl http://localhost:8000/pending
# 기대: {"data": {"pending": [{"id": "rf-1", "user_id": "cust-001", "status": "pending", ...}]}}

# 5. 승인 (관리자) — refund_id로 결정
curl -X POST http://localhost:8000/approve \
  -H "Content-Type: application/json" \
  -d '{"refund_id": "rf-1", "decision": "approve"}'
# 기대: {"data": {"id": "rf-1", "status": "approved", ...}}

# === ③ 사용자: 마이페이지에서 결과 확인 ===

# 6. 내 신청 상태 조회 (사용자)
curl "http://localhost:8000/refunds?user_id=cust-001"
# 기대: {"data": {"refunds": [{"id": "rf-1", "status": "approved", ...}]}}

# === 본인 확인을 취소(reject)하는 경우 ===

# 7. 환불 요청 후 본인이 취소 → 신청 자체가 안 됨
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "ORD-999 환불해줘", "thread_id": "refund-2", "user_id": "cust-002"}'
curl -X POST http://localhost:8000/chat/confirm \
  -H "Content-Type: application/json" \
  -d '{"thread_id": "refund-2", "decision": "reject", "user_id": "cust-002"}'
# 기대: {"data": {"status": "cancelled"}} — refund_store에 레코드 안 생김

# 8. Swagger UI
# http://localhost:8000/docs
```

---

## Phase 5 핵심 구조 요약

```
[① 본인 확인 — 동기, LangGraph interrupt]
환불 요청 → submit_refund_request 호출 시도
  → HumanInTheLoopMiddleware interrupt ⏸️ (checkpointer가 thread_id로 상태 저장)
  → chat.py: status="confirmation_required"
  → 사용자가 POST /chat/confirm {decision}
      approve → 도구 실행 → refund_store에 레코드 생성(pending) → "submitted"
      reject  → 도구 건너뜀 → 레코드 없음 → "cancelled"

[② 관리자 승인 — 비동기, LangGraph 무관]
GET /pending → refund_store의 pending 레코드 목록
POST /approve {refund_id, decision} → set_decision() → status 변경

[③ 사용자 조회 — 마이페이지]
GET /refunds?user_id → list_by_user() → 내 신청 상태 목록

핵심: interrupt(동기)는 "그 자리에 있는 사용자" 확인에만,
      관리자 승인(비동기)은 refund_store CRUD로 분리.
```

---

## 검증 체크리스트

### refund_store.py
- checkpointer(대화 상태)와 refund_store(신청 레코드)의 차이 이해
- 레코드가 본인 확인 "후"에 생성되는 점 이해
- status 생애주기(pending → approved/rejected) 이해

### tools.py
- submit_refund_request가 "환불 실행"이 아니라 "신청 접수"임을 이해
- runtime.context.user_id로 신청자를 기록하는 이유 이해

### agent.py
- HITL interrupt를 "사용자 본인 확인"에 쓰는 이유 이해
- 관리자 승인을 interrupt로 처리하면 안 되는 이유 이해

### routers/chat.py
- `result.get("__interrupt__")`를 messages[-1]보다 먼저 검사하는 이유 이해
- /chat/confirm이 Command(resume=...)로 재개하는 방법 이해
- 재개 시 context(user_id)를 다시 넘기는 이유 이해

### routers/refund.py
- 관리자 승인이 LangGraph 재개가 아니라 레코드 상태 변경인 점 이해
- thread_id(대화)와 refund_id(신청서)의 차이 이해
- GET /refunds로 사용자가 비동기 결과를 확인하는 흐름 이해
