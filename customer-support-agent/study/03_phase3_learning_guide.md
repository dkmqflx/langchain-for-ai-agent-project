# Phase 3 학습 가이드 — Short-term & Long-term Memory

이 가이드는 Phase 3의 5개 파일을 의존성 순서대로 학습할 수 있도록 구성되었습니다.

---

## Phase 3에서 새로 추가된 것

Phase 2까지는 에이전트가 "기억 상실증" 상태였습니다.

```
[Phase 2 문제]

고객: "제 주문번호는 ORD-123이에요"
Agent: "네, ORD-123 말씀이시군요."

고객: "아까 말한 주문번호로 환불해줘"
Agent: "죄송합니다, 어떤 주문번호를 말씀하시는 건가요?" ← 방금 들은 걸 잊어버림!

고객: "한국어로만 답변해줘"
Agent: "네!" (이번 대화에서는 한국어로 답변)
(다음 날 새 대화) Agent: "Hello! How can I help you?" ← 선호도를 기억 못 함!
```

Phase 3는 두 가지 기억을 추가합니다:

```
[Phase 3 해결]

단기 기억 (Short-term): 같은 대화 내에서 기억
  고객: "제 주문번호는 ORD-123이에요"
  고객: "아까 말한 주문번호로 환불해줘"
  Agent: "ORD-123으로 환불 처리해드릴게요!" ✅

장기 기억 (Long-term): 다음 대화에서도 기억
  고객: "한국어로만 답변해줘" → 저장
  (다음 날 새 대화)
  Agent: "안녕하세요! 무엇을 도와드릴까요?" ✅ (자동으로 한국어)
```

---

## 학습 흐름도

```
[새로 추가된 파일]
context.py      → 요청마다 user_id 담는 데이터 클래스
middleware.py   → 장기 기억을 system prompt에 주입하는 함수
tools.py        → save_user_preference, get_user_preferences 도구 추가
agent.py        → checkpointer(단기) + store(장기) 연결
routers/chat.py → config에 user_id 추가

[요청 흐름]
POST /chat {"message": "한국어로 답변해줘", "user_id": "cust-001"}
     ↓
chat.py → config={"configurable": {"thread_id": ...}} + context=AgentContext(user_id="cust-001")
     ↓
agent.py → inject_memory 호출
     ↓
middleware.py → store에서 "cust-001" 선호도 조회 → system prompt에 추가
     ↓
Agent → "save_user_preference('language', '한국어')" 도구 호출
     ↓
tools.py → store.put(("user_preferences", "cust-001"), "language", {"value": "한국어"})
     ↓
다음 대화에서 inject_memory가 선호도를 읽어 자동 반영
```

---

## Step 1: `agent/context.py` 읽기 (5분)

### 목표

요청 컨텍스트가 무엇인지, 왜 dataclass를 쓰는지 이해

---

### 핵심 개념: dataclass vs dict

```python
@dataclass
class AgentContext:
    user_id: str = "anonymous"
    user_tier: str = "standard"
```

**비유: 호텔 체크인 카드 vs 빈 종이**

```
빈 종이(dict):
  context = {"user_id": "cust-001", "user_tier": "premium"}
  context["user_tier"]   ← 오타 나도 런타임에서야 발견
  context["usr_tier"]    ← KeyError (언제 터질지 모름)

체크인 카드(dataclass):
  context = AgentContext(user_id="cust-001", user_tier="premium")
  context.user_tier      ← IDE가 자동완성 지원
  context.usr_tier       ← IDE가 즉시 빨간 줄 표시 (오타 즉시 발견)
```

**user_tier를 지금 추가하는 이유:**

```
현재는 standard만 있지만, Phase 5 이후 확장 시:
  standard → 일반 처리
  premium  → 우선 처리, 더 상세한 답변

지금부터 필드를 만들어두면 나중에 API 스키마 변경 불필요.
```

---

## Step 2: `agent/middleware.py` 읽기 (20분)

### 목표

장기 기억이 system prompt에 어떻게 주입되는지, `@wrap_model_call` 미들웨어가 어떻게 동작하는지 이해

---

### 핵심 개념 1: 동적 system prompt 주입

Phase 2까지는 모든 사용자에게 동일한 system prompt가 전달됩니다.

```
모든 사용자에게 동일한 prompt:
  고객 A → "당신은 고객 지원 에이전트입니다."
  고객 B → "당신은 고객 지원 에이전트입니다."
  고객 C → "당신은 고객 지원 에이전트입니다."
  (선호도 반영 불가)
```

Phase 3는 `inject_memory` (@wrap_model_call 데코레이터)로 요청마다 사용자별 선호도를 system prompt에 동적으로 주입합니다.

```
요청마다 선호도 조회 → 사용자별 다른 prompt:
  고객 A (language=한국어) → "...에이전트입니다.\n[선호도]\n- language: 한국어"
  고객 B (선호도 없음)     → "...에이전트입니다."
  고객 C (style=간결하게)  → "...에이전트입니다.\n[선호도]\n- style: 간결하게"
```

---

### 핵심 개념 2: inject_memory 내부 동작

```python
from typing import Callable
from langchain.agents.middleware import wrap_model_call, ModelRequest, ModelResponse

@wrap_model_call
async def inject_memory(request: ModelRequest, handler: Callable) -> ModelResponse:
    # [1] runtime에서 user_id 추출 (request.runtime로 접근)
    if not request.runtime.store or not request.runtime.context:
        return await handler(request)  # store/context 없으면 그대로 진행
    user_id = request.runtime.context.user_id

    # [2] store에서 해당 사용자의 선호도 조회
    namespace = ("user_preferences", user_id)
    items = request.runtime.store.search(namespace)

    if not items:
        return await handler(request)  # 선호도 없으면 그대로 진행

    # [3] 선호도를 문자열로 변환
    preferences = "\n".join(
        f"- {item.key}: {item.value['value']}" for item in items
    )
    memory_text = f"\n\n[사용자 선호도 - 반드시 반영하세요]\n{preferences}"

    # [4] 기존 system_prompt를 보존하고 선호도를 덧붙여 override
    #     base를 보존하지 않으면 역할/도구 지침이 통째로 사라짐
    base_prompt = request.system_prompt or ""
    request = request.override(system_prompt=base_prompt + memory_text)
    return await handler(request)  # 수정된 request로 모델 호출
```

**wrap_model_call 동작 방식:**

```
(request, handler) 시그니처:
  request  → 모델 호출 정보 (system_prompt, messages, model, tools 등)
  handler  → 실제 모델 호출 함수. await handler(request)를 호출해야 모델이 실행됨

핵심 패턴:
  - request.override(system_prompt=...) → 수정된 새 request 반환
  - return await handler(request)       → 수정된 request로 모델 호출
  - 조건 미충족 시 그냥 return await handler(request) → 원본 그대로 진행

before_model(state 수정)과 달리, wrap_model_call은 "모델 호출 자체를 감싸서"
그 호출에만 적용되는 system_prompt를 만든다. state의 메시지는 건드리지 않으므로
매 모델 호출마다 항상 base SYSTEM_PROMPT에서 새로 시작 → 선호도 중복 누적 없음.
```

**왜 async 함수인가:**

```
chat.py는 FastAPI 비동기 핸들러에서 `await agent.ainvoke(...)`로 실행한다.
@wrap_model_call에 sync 함수를 넘기면 sync wrap_model_call 훅만 등록되고,
async 경로(ainvoke)에서 호출되는 awrap_model_call은 base 기본 구현
(NotImplementedError를 raise)으로 남는다 → 매 요청 500 에러.
→ async def로 정의하면 awrap_model_call 훅으로 등록되어 ainvoke에서 정상 동작.
```

**namespace가 tuple인 이유:**

```
LangGraph Store는 계층적 네임스페이스 지원.
("user_preferences", "cust-001") → 그룹="user_preferences" > 사용자="cust-001"
나중에 ("conversation_history", "cust-001") 같은 다른 그룹도 추가 가능.
```

---

### 학습 질문

- items가 빈 리스트일 때 `handler(request)`가 그대로 호출되는 이유는?
- `store.search(namespace)`에서 namespace가 tuple인 이유는 무엇일까?
- `request.override(system_prompt=memory_text)`처럼 base를 빼면 어떤 문제가 생기는가?

---

## Step 3: `agent/tools.py` 읽기 (20분)

### 목표

ToolRuntime이 무엇인지, 왜 runtime이 LLM에 보이지 않는지 이해

---

### 핵심 개념 1: ToolRuntime — LangChain이 자동 주입하는 파라미터

```python
from langchain.tools import ToolRuntime

@tool
def save_user_preference(
    key: str,                          # ← LLM이 채워야 하는 파라미터
    value: str,                        # ← LLM이 채워야 하는 파라미터
    runtime: ToolRuntime[AgentContext], # ← LangChain이 자동 주입 (context + store 통합)
) -> str:
    user_id = runtime.context.user_id if runtime.context else "anonymous"
    namespace = ("user_preferences", user_id)
    runtime.store.put(namespace, key, {"value": value})
```

**비유: 식당 주문서 vs 주방 자동 공급**

```
LLM(손님)이 보는 주문서:
  - 선호도 이름(key): ____
  - 선호도 값(value): ____

LLM은 key와 value만 채움. runtime은 주문서에 없음.

주방(LangChain)이 알아서 runtime을 주입:
  - runtime.context: AgentContext (user_id, user_tier)
  - runtime.store:   InMemoryStore 인스턴스

LLM이 채운 값 + LangChain이 주입한 runtime → 함수 실행
```

**만약 store를 일반 파라미터로 만들면:**

```python
# 잘못된 방식
@tool
def save_user_preference(key: str, value: str, store: BaseStore) -> str:
    ...

# LLM이 보는 스키마:
# {
#   "key": "string",
#   "value": "string",
#   "store": ???   ← LLM이 어떻게 채우지?? InMemoryStore를 JSON으로 못 표현
# }
# → LLM이 store를 채울 수 없음 ❌
# ToolRuntime은 LangChain이 "주입 파라미터"로 인식해 LLM 스키마에서 제외 ✅
```

---

### 핵심 개념 2: namespace — 사용자별 격리된 저장 공간

```python
namespace = ("user_preferences", user_id)
runtime.store.put(namespace, key, {"value": value})
```

**비유: 아파트 우편함**

```
아파트 우편함 = InMemoryStore

("user_preferences", "cust-001") → 101호 우편함
  language: "한국어"
  style: "간결하게"

("user_preferences", "cust-002") → 102호 우편함
  language: "English"

각 세입자(user_id)는 자신의 우편함에만 접근.
cust-001의 선호도가 cust-002에게 노출되지 않음.
```

**namespace가 tuple인 이유:**

```
LangGraph Store는 계층적 네임스페이스 지원.
("user_preferences", "cust-001") → 그룹="user_preferences" > 사용자="cust-001"
나중에 ("conversation_history", "cust-001") 같은 다른 그룹도 추가 가능.
```

---

### 핵심 개념 3: get_user_preferences — LLM 노출 파라미터 없는 도구

```python
@tool
def get_user_preferences(runtime: ToolRuntime[AgentContext]) -> str:
    """저장된 사용자 선호도를 모두 조회합니다."""
```

LLM에 노출되는 파라미터가 없습니다 (runtime은 주입 전용). LLM은 인자 없이 호출:

```
LLM: get_user_preferences() 호출
LangChain: runtime(context + store)을 자동으로 주입 후 실행
```

---

### 학습 질문

- `ToolRuntime[AgentContext]`가 LLM 스키마에 노출되지 않는 이유는 무엇일까?
- store.put(namespace, "language", {"value": "한국어"})에서 값을 `"한국어"` 대신 `{"value": "한국어"}`로 감싸는 이유는?
- save_user_preference를 두 번 호출하면 (같은 key) 덮어쓰기가 될까?

---

## Step 4: `agent/agent.py` 읽기 (15분)

### 목표

checkpointer와 store가 무엇인지, 왜 싱글톤이어야 하는지 이해

---

### 핵심 개념 1: InMemorySaver (단기 기억)

```python
_checkpointer = InMemorySaver()

_agent = create_agent(
    ...
    checkpointer=_checkpointer,
)
```

**비유: 화이트보드**

```
InMemorySaver = 상담 센터의 화이트보드

thread_id="sess-A":
  [화이트보드 A]
  고객: "ORD-123 환불해줘"
  상담사: "네, 확인해볼게요"
  고객: "아까 말한 주문 취소도 해줘"
  ← 상담사가 화이트보드를 보며 "ORD-123 취소" 이해

thread_id="sess-B":
  [화이트보드 B] (별도)
  고객: "배송 언제 와요?"
  ← 완전히 독립된 대화
```

**checkpointer가 없으면 (Phase 2):**

```
매 요청 = 새 화이트보드
고객: "ORD-123 환불해줘"  → 화이트보드에 기록
고객: "아까 말한 거 취소해줘" → 새 화이트보드 (이전 내용 없음!)
상담사: "무엇을 취소하시는 건가요?" ← 기억 없음
```

**checkpointer가 있으면 (Phase 3):**

```
같은 thread_id = 같은 화이트보드 유지
고객: "ORD-123 환불해줘"  → 화이트보드 A에 기록
고객: "아까 말한 거 취소해줘" → 화이트보드 A 이어받음
상담사: "ORD-123 취소해드릴게요" ← 기억 있음!
```

---

### 핵심 개념 2: InMemoryStore (장기 기억)

```python
_store = InMemoryStore()

_agent = create_agent(
    ...
    store=_store,
)
```

**비유: 고객 CRM 카드**

```
InMemoryStore = 고객 관리 시스템 (CRM)

화이트보드(단기)와 달리 대화가 끝나도 유지됨.

cust-001 카드:
  language: 한국어
  style: 간결하게

월요일 대화 (thread_id="sess-mon"):
  고객: "한국어로 답해줘" → CRM 카드에 저장

화요일 대화 (thread_id="sess-tue", 완전히 새 대화):
  inject_memory가 CRM 카드 조회
  → system prompt에 "language: 한국어" 자동 추가
  → 고객이 다시 요청 안 해도 한국어로 답변
```

---

### 핵심 개념 3: 싱글톤이 필수인 이유

```python
# ✅ 올바른 방식 — 모듈 레벨 싱글톤
_checkpointer = InMemorySaver()
_store = InMemoryStore()

def get_agent():
    return _agent   # 항상 같은 인스턴스 반환
```

```python
# ❌ 잘못된 방식 — 요청마다 새로 생성
def get_agent():
    checkpointer = InMemorySaver()   # 매번 새로 만들면
    store = InMemoryStore()          # 이전에 저장된 내용이 사라짐!
    return create_agent(...)
```

```
비유: 이사를 매일 하면 어떻게 될까?

매일 새 집(새 InMemoryStore):
  월요일: 집에 언어 선호도 메모 붙임
  화요일: 이사 (새 집, 메모 없음)
  → 선호도가 사라짐!

같은 집 유지(모듈 레벨 싱글톤):
  월요일: 집에 언어 선호도 메모 붙임
  화요일: 같은 집, 메모 그대로 있음
  → 선호도 유지!
```

---

### 핵심 개념 4: Phase별 Agent 변화

```
Phase 2:
  create_agent(
      model=_llm,
      tools=[search_documents],
      system_prompt="고정 문자열",
  )

Phase 3:
  create_agent(
      model=_llm,
      tools=[search_documents, save_user_preference, get_user_preferences],
      system_prompt=SYSTEM_PROMPT,
      middleware=[inject_memory],  # ← 장기 기억 동적 주입 (@wrap_model_call 데코레이터 함수)
      checkpointer=_checkpointer,            # ← 단기 기억 추가
      store=_store,                          # ← 장기 기억 추가
      context_schema=AgentContext,
  )

Phase 5: + process_refund tool
```

---

### 학습 질문

- `_checkpointer = InMemorySaver()`를 `get_agent()` 내부에서 만들면 어떻게 될까?
- thread_id와 user_id의 차이를 한 문장으로 설명하면?
- `store=_store`를 빼면 `inject_memory`와 `save_user_preference`는 어떻게 될까?

---

## Step 5: `routers/chat.py` 읽기 (10분)

### 목표

thread_id는 config로, user_id는 context로 전달하는 이유와 각각 어디에 쓰이는지 이해

---

### 핵심 개념: config vs context — 두 가지 기억을 연결하는 라우터

```python
result = await agent.ainvoke(
    {"messages": [("human", request.message)]},
    config={"configurable": {"thread_id": request.thread_id}},  # → checkpointer (단기 기억)
    context=AgentContext(user_id=request.user_id),               # → inject_memory + tools (장기 기억)
)
```

**비유: 택배 송장**

```
thread_id (config): "어떤 배송 건인지" (단기 기억 — 이번 배송)
  InMemorySaver: "sess-001이 이 대화 내역이야"

user_id (context): "누구에게 배달하는지" (장기 기억 — 고객 정보)
  inject_memory: "cust-001의 선호도를 꺼내서 prompt에 넣어줘"
  save_user_preference: "cust-001의 선호도를 저장해줘"
```

**config vs context 역할 분리:**

```
config["configurable"]: LangGraph 인프라용 (checkpointer의 thread_id 등)
context:                비즈니스 로직용 (user_id, user_tier 등)

create_agent에 context_schema=AgentContext를 선언하면
  → ainvoke(context=AgentContext(...))로 전달한 값을
  → 미들웨어/도구에서 runtime.context.user_id로 타입 안전하게 접근
```

---

### 학습 질문

- thread_id를 전달하지 않으면 어떻게 될까? (config 없이 invoke)
- user_id="anonymous"인 두 사람이 선호도를 저장하면 서로 덮어쓰일까?
- 같은 user_id + 다른 thread_id로 두 번 대화하면 장기 기억이 공유될까?

---

## 전체 흐름 실습 (20분)

서버를 실행하고 curl로 단기/장기 기억을 직접 테스트하세요.

```bash
# 1. 서버 실행
cd customer-support-agent/backend
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# =====================
# 단기 기억 테스트
# =====================

# 2. 첫 번째 메시지 (주문번호 알려주기)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "제 주문번호는 ORD-123이에요",
    "thread_id": "test-short-term",
    "user_id": "cust-001"
  }'

# 3. 같은 thread_id로 두 번째 메시지 (이전 내용 기억 확인)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "아까 말한 주문번호가 뭐였죠?",
    "thread_id": "test-short-term",
    "user_id": "cust-001"
  }'
# 기대 응답: "ORD-123이라고 말씀하셨습니다" ✅

# 4. 다른 thread_id로 같은 질문 (기억 없어야 함)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "아까 말한 주문번호가 뭐였죠?",
    "thread_id": "test-new-session",
    "user_id": "cust-001"
  }'
# 기대 응답: "주문번호를 다시 알려주시겠어요?" ✅ (새 대화니까 모름)

# =====================
# 장기 기억 테스트
# =====================

# 5. 선호도 저장 요청
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "앞으로는 영어로만 답변해줘",
    "thread_id": "pref-session-1",
    "user_id": "cust-002"
  }'
# Agent가 save_user_preference("language", "English") 호출

# 6. 완전히 새 대화 (thread_id 변경) — 선호도 유지 확인
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "환불 정책이 어떻게 돼요?",
    "thread_id": "pref-session-2",
    "user_id": "cust-002"
  }'
# 기대 응답: "The refund policy is..." ✅ (새 대화인데도 영어로!)

# 7. Swagger UI에서 시각적으로 테스트
# http://localhost:8000/docs
```

---

## Phase 3 핵심 구조 요약

```
[단기 기억 흐름]
같은 thread_id로 연속 질문
     ↓
InMemorySaver(checkpointer)
  → 이전 메시지를 자동으로 state["messages"]에 포함
     ↓
Agent가 이전 대화 맥락을 보고 답변

[장기 기억 흐름]
새 요청 (어떤 thread_id든)
     ↓
context=AgentContext(user_id="cust-001")
     ↓
inject_memory(request, handler) 호출
  → request.runtime.store.search(("user_preferences", "cust-001"))
  → 저장된 선호도 발견
  → request.override(system_prompt=base + "[사용자 선호도]\n- language: 한국어")
     ↓
Agent가 한국어로 답변 (고객이 다시 요청 안 해도!)
```

---

## 검증 체크리스트

### context.py
- dataclass가 dict보다 나은 이유 이해
- user_tier 필드가 지금 당장은 안 쓰이는데 왜 있는지 이해

### middleware.py
- `inject_memory` (@wrap_model_call 데코레이터)의 `(request, handler)` 패턴 이해
- `request.override(system_prompt=base + memory_text)`로 base 보존하며 주입하는 방식 이해
- namespace가 `("user_preferences", user_id)` tuple인 이유 이해

### tools.py
- `ToolRuntime[AgentContext]`가 context와 store를 함께 주입하는 방식 이해
- runtime이 LLM 스키마에 노출되지 않는 이유 이해
- namespace를 통한 사용자 격리 이해
- runtime.store.put과 runtime.store.search 사용법 이해

### agent.py
- InMemorySaver(단기) vs InMemoryStore(장기) 차이 이해
- 싱글톤이 필수인 이유 이해 (요청마다 새로 만들면 상태 유실)
- Phase 2 → Phase 3 변화 요약 이해

### routers/chat.py
- config에 user_id를 추가한 이유 이해
- thread_id와 user_id가 각각 어느 기억에 사용되는지 이해

---

## Production 전환 시 고려사항

현재 Phase 3의 구현은 **개발/학습용**입니다.

```
개발용 (현재):
  InMemorySaver → 서버 재시작 시 단기 기억 초기화
  InMemoryStore → 서버 재시작 시 장기 기억 초기화

Production 전환 (Phase 7):
  InMemorySaver → PostgresSaver (langgraph-checkpoint-postgres)
    "서버가 재시작돼도 대화 이력 유지"

  InMemoryStore → Redis 기반 Store
    "서버가 재시작돼도 선호도 유지"
    "여러 서버 인스턴스 간 공유 가능"
```

---

## 다음 단계

Phase 3을 완료했으면:

- **Phase 4**: PII + Guardrail Middleware
  - PII 마스킹: `PIIMiddleware` (langchain 내장) + 커스텀 detector
    예) "내 이메일은 test@test.com이에요" → "[REDACTED_EMAIL]"
  - Before Guardrail: 키워드 기반 욕설 차단 (`is_blocked_input`)
  - After Guardrail: GPT-4o-mini가 답변 검증 (`check_hallucination`)
