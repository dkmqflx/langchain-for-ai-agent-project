# Phase 4 학습 가이드 — PII + Guardrail + create_agent 마이그레이션

이 가이드는 Phase 4의 4개 수정 파일을 의존성 순서대로 학습할 수 있도록 구성되었습니다.

---

## Phase 4에서 새로 추가된 것

Phase 3까지는 두 가지 문제가 있었습니다.

```
[문제 1: 안전 장치 없음]

고객: "씨발 환불해줘"
Agent: "안녕하세요! 환불 정책은..." ← 욕설을 그냥 처리 😱

고객: "내 카드 1234-5678-9012-3456로 결제했는데..."
Agent: "1234-5678-9012-3456 카드로..." ← 카드번호를 그대로 반복 😱

Agent: "환불은 7일 이내 가능합니다" ← (문서엔 30일이라고 적혀있는데 날조!)

[문제 2: create_react_agent는 legacy]

create_react_agent에는 middleware= 파라미터가 없어서
LangChain 공식 PIIMiddleware를 직접 연결할 방법이 없음.
```

Phase 4는 두 문제를 함께 해결합니다:

```
[해결 1: create_agent로 마이그레이션]

create_react_agent (legacy) → create_agent (현대 표준)
  middleware=[PIIMiddleware(...), InjectMemoryMiddleware()] 추가 가능
  context_schema=AgentContext → user_id를 context=로 전달
  ToolRuntime[AgentContext] → 도구에서 store/context 접근

[해결 2: 안전 장치 추가]

PIIMiddleware (에이전트 내부):
  "내 카드 1234-5678-9012-3456..." → "내 카드 ****-****-****-3456..."
  "이메일 a@b.com 이에요" → "[REDACTED_EMAIL] 이에요"

Before Guardrail (에이전트 실행 전):
  "씨발 환불해줘" → "부적절한 언어가..." (에이전트 실행 없음, 비용 절약)

After Guardrail (에이전트 실행 후):
  Agent: "환불은 7일 이내 가능합니다"
  GPT-4o-mini: "HALLUCINATION" 판정
  최종: "관련 정보를 문서에서 찾을 수 없습니다." ✅
```

---

## 학습 흐름도

```
[수정된 파일]
agent/context.py    → 변경 없음 (create_agent의 context_schema로 그대로 사용)
agent/tools.py      → InjectedStore+RunnableConfig → ToolRuntime[AgentContext]
agent/middleware.py → make_inject_memory → InjectMemoryMiddleware 클래스
                      is_blocked_input, check_hallucination 추가
agent/agent.py      → create_react_agent → create_agent + middleware=[]
routers/chat.py     → Before/After Guardrail 통합, context= 방식으로 변경

[요청 처리 파이프라인]
POST /chat {"message": "씨발 환불해줘", "user_id": "cust-001", "thread_id": "..."}
     ↓
[1] is_blocked_input(message)       → 욕설 감지 → 즉시 반환 (에이전트 미실행)
     ↓ (차단 안 됨)
[2] agent.invoke(
      context=AgentContext(user_id)  → InjectMemoryMiddleware가 사용 (장기 기억)
      config={thread_id}             → checkpointer가 사용 (단기 기억)
    )
     ┌─ 에이전트 내부 ─────────────────────────────────────────┐
     │  InjectMemoryMiddleware.before_model → system prompt 주입  │
     │  PIIMiddleware.before_model         → 입력 PII 마스킹      │
     │  ---- 모델 호출 ----                                       │
     │  PIIMiddleware.after_model          → 출력 PII 마스킹      │
     └──────────────────────────────────────────────────────────┘
     ↓
[3] ToolMessage 분석 → search_documents 결과 수집
     ↓
[4] check_hallucination(...) → 컨텍스트 있을 때만 GPT-4o-mini 검증
     ↓
응답 반환
```

---

## Step 1: `agent/tools.py` 읽기 — ToolRuntime 마이그레이션 (15분)

### 목표

`InjectedStore + RunnableConfig`에서 `ToolRuntime[AgentContext]`로 바뀐 이유와 차이를 이해

---

### 핵심 개념 1: Phase 3 vs Phase 4 도구 시그니처

**Phase 3 (create_react_agent)**:

```python
from typing import Annotated
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import InjectedStore
from langgraph.store.base import BaseStore

@tool
def save_user_preference(
    key: str,
    value: str,
    config: RunnableConfig,                      # ← LangGraph가 자동 주입
    store: Annotated[BaseStore, InjectedStore()], # ← LangGraph가 자동 주입
) -> str:
    user_id = config["configurable"].get("user_id", "anonymous")
    store.put(("user_preferences", user_id), key, {"value": value})
```

**Phase 4 (create_agent)**:

```python
from langchain.tools import ToolRuntime

@tool
def save_user_preference(
    key: str,
    value: str,
    runtime: ToolRuntime[AgentContext],  # ← 하나의 객체로 store + context 통합
) -> str:
    user_id = runtime.context.user_id if runtime.context else "anonymous"
    runtime.store.put(("user_preferences", user_id), key, {"value": value})
```

**비유: 개별 도구 vs 스위스 아미 나이프**

```
Phase 3: 도구들을 따로따로 받음
  config: 열쇠
  store:  손전등
  각각 어디서 왔는지 알아야 함

Phase 4: ToolRuntime = 스위스 아미 나이프
  runtime.context: 열쇠
  runtime.store:   손전등
  하나만 받으면 모두 접근 가능
```

---

### 핵심 개념 2: ToolRuntime이 LLM 스키마에 노출되지 않는 이유

```
LLM(손님)이 보는 주문서:
  - 선호도 이름(key): ____
  - 선호도 값(value): ____

runtime은 주문서에 없음. LangGraph가 알아서 주입.
```

Phase 3의 `InjectedStore`와 동일한 원리지만, `ToolRuntime` 하나로 context와 store를 함께 전달합니다.

---

### 핵심 개념 3: ToolRuntime의 import 경로

```python
from langchain.tools import ToolRuntime   # ✅ 공식 LangChain API
```

내부적으로 `langgraph.prebuilt.tool_node.ToolRuntime`과 동일한 클래스지만, 공식 문서가 `langchain.tools`를 사용하므로 이 경로가 올바릅니다.

---

### 학습 질문

- Phase 3의 `config["configurable"].get("user_id")` 와 Phase 4의 `runtime.context.user_id`는 어떻게 다른가?
- `runtime.context`가 `None`일 수 있는 상황은?
- `ToolRuntime[AgentContext]`의 제네릭 타입 파라미터 `AgentContext`의 역할은?

---

## Step 2: `agent/middleware.py` 읽기 — InjectMemoryMiddleware (20분)

### 목표

`make_inject_memory` 팩토리 패턴이 왜 `InjectMemoryMiddleware` 클래스로 바뀌었는지,
`AgentMiddleware.before_model` 훅이 어떻게 작동하는지 이해

---

### 핵심 개념 1: Phase 3 vs Phase 4 장기 기억 주입 방식

**Phase 3 (callable prompt)**:

```python
# agent.py
_agent = create_react_agent(
    model=_llm,
    tools=[...],
    prompt=make_inject_memory(_store),  # ← callable을 prompt= 파라미터로 전달
)

# middleware.py
def make_inject_memory(store: BaseStore):
    def inject_memory(state, config: RunnableConfig) -> list:
        user_id = config["configurable"].get("user_id", "anonymous")
        items = store.search(("user_preferences", user_id))
        ...
        return [SystemMessage(...)] + list(state["messages"])
    return inject_memory
```

**Phase 4 (AgentMiddleware)**:

```python
# agent.py
_agent = create_agent(
    model=_llm,
    tools=[...],
    system_prompt=SYSTEM_PROMPT,           # ← 정적 문자열
    middleware=[InjectMemoryMiddleware()], # ← 미들웨어로 동적 주입
)

# middleware.py
class InjectMemoryMiddleware(AgentMiddleware):
    def before_model(self, state, runtime: Runtime) -> dict | None:
        user_id = runtime.context.user_id
        items = runtime.store.search(("user_preferences", user_id))
        # SystemMessage 찾아서 선호도 추가
        ...
        return {"messages": updated_messages}
```

**왜 바꿨는가:**

```
create_react_agent: prompt= 파라미터가 callable을 받음 → make_inject_memory 가능
create_agent:      system_prompt= 파라미터는 str/SystemMessage만 받음 (callable 불가)
                   대신 middleware= 파라미터를 제공 → AgentMiddleware로 동적 주입
```

---

### 핵심 개념 2: AgentMiddleware.before_model 훅

```python
class InjectMemoryMiddleware(AgentMiddleware):
    def before_model(self, state: Any, runtime: Runtime) -> dict | None:
        # runtime.store   → InMemoryStore (store= 파라미터로 주입된 것)
        # runtime.context → AgentContext (context=AgentContext(...) 로 전달된 것)
        
        if not runtime.store or not runtime.context:
            return None  # 변경 없음
        
        items = runtime.store.search(("user_preferences", runtime.context.user_id))
        
        if not items:
            return None  # 선호도 없으면 변경 없음
        
        # SystemMessage 찾아서 선호도 추가
        messages = list(state["messages"])
        for i, msg in enumerate(messages):
            if isinstance(msg, SystemMessage):
                messages[i] = SystemMessage(content=msg.content + memory_text)
                return {"messages": messages}  # 변경된 state 반환
        
        return None
```

**before_model 반환값 의미:**

```
None 반환:       state 변경 없음 (선호도 없을 때)
dict 반환:       반환된 dict로 state 업데이트
                 {"messages": [...]} → 메시지 목록을 교체
```

**Phase 3의 inject_memory와 차이:**

```
Phase 3: [SystemMessage] + 기존 메시지 → 항상 SystemMessage를 앞에 추가
Phase 4: 기존 SystemMessage를 찾아서 content에 선호도 덧붙임
         이유: create_agent가 system_prompt=를 이미 SystemMessage로 추가해뒀기 때문
```

---

### 핵심 개념 3: is_blocked_input과 check_hallucination

이 두 함수는 Phase 3→4 마이그레이션과 무관하게 새로 추가된 순수 안전 기능입니다.

**is_blocked_input — 에이전트 실행 전 단락(short-circuit)**:

```python
def is_blocked_input(text: str) -> tuple[bool, str]:
    text_lower = text.lower()
    for keyword in _BLOCKED_KEYWORDS:
        if keyword in text_lower:
            return True, "부적절한 언어가 포함되어 있어..."
    return False, ""
```

`(bool, reason)` tuple을 반환하는 이유: `if blocked: return {"response": reason}` 처럼 거절 메시지도 함께 전달하기 위해.

**check_hallucination — 에이전트 실행 후 검증**:

```python
def check_hallucination(answer: str, context: str) -> str:
    prompt = _HALLUCINATION_PROMPT.format(context=context, answer=answer)
    response = _get_monitor_llm().invoke(prompt)
    if "HALLUCINATION" in response.content.upper():
        return _HALLUCINATION_FALLBACK
    return answer
```

`_get_monitor_llm()`이 lazy 초기화인 이유: 모듈 임포트 시점에 OPENAI_API_KEY가 없어도 서버가 시작되게 하기 위해.

---

### 학습 질문

- `before_model`이 `None`을 반환할 때와 `{"messages": [...]}`를 반환할 때의 차이는?
- `abefore_model`을 따로 정의하지 않으면 어떻게 될까? (`AgentMiddleware` 기본 구현 확인)
- Phase 3의 `make_inject_memory`에서는 팩토리 패턴이 필요했는데, Phase 4에서는 왜 필요 없는가?

---

## Step 3: `agent/agent.py` 읽기 — create_agent 마이그레이션 (20분)

### 목표

`create_react_agent`와 `create_agent`의 차이, `PIIMiddleware` 통합 방식 이해

---

### 핵심 개념 1: create_react_agent vs create_agent

```python
# Phase 3 (create_react_agent from langgraph)
from langgraph.prebuilt import create_react_agent

_agent = create_react_agent(
    model=_llm,
    tools=[...],
    prompt=make_inject_memory(_store),  # callable
    checkpointer=_checkpointer,
    store=_store,
    # middleware= 파라미터 없음!
)
```

```python
# Phase 4 (create_agent from langchain)
from langchain.agents import create_agent

_agent = create_agent(
    model=_llm,
    tools=[...],
    system_prompt=SYSTEM_PROMPT,  # str/SystemMessage만 (callable 불가)
    middleware=[                   # ← 공식 middleware= 파라미터
        InjectMemoryMiddleware(),
        PIIMiddleware("email", ...),
        PIIMiddleware("credit_card", ...),
    ],
    checkpointer=_checkpointer,
    store=_store,
    context_schema=AgentContext,   # ← user_id 전달 방식 선언
)
```

| 항목 | create_react_agent | create_agent |
|------|-------------------|--------------|
| 출처 | langgraph.prebuilt | langchain.agents |
| middleware= | ❌ 없음 | ✅ 있음 |
| prompt= | callable 가능 | ❌ 없음 |
| system_prompt= | ❌ 없음 | str/SystemMessage만 |
| context_schema= | ❌ 없음 | ✅ 있음 |

---

### 핵심 개념 2: PIIMiddleware — 공식 내장 PII 처리

```python
from langchain.agents.middleware import PIIMiddleware

PIIMiddleware(
    "email",
    detector=r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    strategy="redact",
    apply_to_input=True,   # 입력(HumanMessage) 마스킹
    apply_to_output=True,  # 출력(AIMessage) 마스킹
)
```

**strategy 선택지:**

```
redact: test@example.com → [REDACTED_EMAIL]   ← 완전 제거
mask:   1234-5678-9012-3456 → ****-****-****-3456  ← 마지막 4자리 노출
block:  감지 시 PIIDetectionError 발생
hash:   결정론적 해시로 대체 (분석용)
```

**커스텀 detector가 필요한 이유:**

```
기본 detector 한계:
  이메일: "이메일은 test@example.com이에요" → 탐지 실패 (한국어 앞뒤)
  카드:   "1234-5678-9012-3456" → 탐지 실패 (하이픈 있음)
  카드:   Luhn 알고리즘 통과하는 번호만 탐지

커스텀 regex detector로 해결:
  detector=r"[a-zA-Z0-9._%+\-]+@..." → 한국어 앞뒤도 탐지 ✅
  detector=r"(?<!\d)\d{4}[-\s]?..."   → 하이픈 카드번호도 탐지 ✅
```

---

### 핵심 개념 3: context_schema — user_id 전달 방식 변화

```python
# Phase 3 invoke
result = await agent.invoke(
    {"messages": [("human", message)]},
    config={
        "configurable": {
            "thread_id": thread_id,
            "user_id": user_id,     # ← config 안에 포함
        }
    },
)

# Phase 4 invoke
result = await agent.invoke(
    {"messages": [("human", message)]},
    config={"configurable": {"thread_id": thread_id}},  # thread_id만
    context=AgentContext(user_id=user_id),               # ← 별도 context로 분리
)
```

**왜 분리했는가:**

```
config["configurable"]:  LangGraph 인프라용 (checkpointer의 thread_id 등)
context:                 비즈니스 로직용 (user_id, user_tier 등)

create_agent의 context_schema= 로 타입을 선언하면
  런타임에서 context가 올바른 타입인지 검증됨
  runtime.context.user_id 처럼 타입 안전하게 접근 가능
```

---

### 학습 질문

- `middleware=[]` 리스트의 순서가 중요한가? `PIIMiddleware`가 `InjectMemoryMiddleware`보다 먼저 오면?
- `apply_to_input=True, apply_to_output=False`(기본값)이면 출력 PII는 어떻게 되는가?
- `create_agent`에 `store=_store`를 넘기면 어디서 접근할 수 있는가?

---

## Step 4: `routers/chat.py` 읽기 (15분)

### 목표

Phase 3→4 파이프라인 변화, context= 전달 방식 이해

---

### 핵심 개념: Phase 3 vs Phase 4 chat.py 비교

**Phase 3:**

```python
result = await agent.invoke(
    {"messages": [("human", request.message)]},
    config={
        "configurable": {
            "thread_id": request.thread_id,
            "user_id": request.user_id,   # ← config에 user_id
        }
    },
)
ai_message = result["messages"][-1].content
# PII 처리 없음, 안전 장치 없음
```

**Phase 4:**

```python
# [1] Before Guardrail
blocked, reason = is_blocked_input(request.message)
if blocked:
    return {..., "status": "blocked"}

# [2] Agent 실행
result = await agent.invoke(
    {"messages": [("human", request.message)]},
    config={"configurable": {"thread_id": request.thread_id}},  # thread_id만
    context=AgentContext(user_id=request.user_id),               # user_id 분리
)

# [3] 검색 컨텍스트 추출 + [4] After Guardrail
search_contexts = [
    msg.content for msg in result["messages"]
    if isinstance(msg, ToolMessage) and msg.name == "search_documents"
]
if search_contexts:
    ai_message = check_hallucination(ai_message, "\n\n---\n\n".join(search_contexts))
```

**PII 마스킹 위치 변화:**

```
Phase 3:
  chat.py에서 mask_pii(입력) → agent → mask_pii(출력)
  ← 에이전트 경계 밖에서 처리

Phase 4:
  agent 내부에서 PIIMiddleware가 자동으로 처리
  apply_to_input=True:  HumanMessage에서 PII 제거 (checkpointer에도 마스킹된 버전 저장)
  apply_to_output=True: AIMessage에서 PII 제거
  ← 에이전트 경계 안에서 처리 (더 포괄적)
```

---

### 학습 질문

- Phase 4에서는 `request.message`를 마스킹 없이 그대로 agent에 넘기는데, PII가 안전한 이유는?
- `is_blocked_input`이 `request.message`에 적용되는 것이 맞는가? 마스킹 후에 적용해야 하지 않는가?
- `search_contexts`가 빈 리스트일 때 After Guardrail을 건너뛰는 이유는?

---

## 전체 흐름 실습 (20분)

```bash
# 1. 서버 실행
cd customer-support-agent/backend
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# =====================
# PIIMiddleware 테스트
# =====================

# 2. 이메일 포함 메시지
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "안녕하세요, 제 이메일은 test@example.com이에요",
    "thread_id": "pii-test-1",
    "user_id": "cust-001"
  }'
# 기대: 응답에 [REDACTED_EMAIL] 처리 (PIIMiddleware apply_to_output=True)

# 3. 카드번호 포함 메시지
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "카드 1234-5678-9012-3456으로 결제했는데 환불해줘",
    "thread_id": "pii-test-2",
    "user_id": "cust-001"
  }'
# 기대: 에이전트가 ****-****-****-3456으로 처리

# =====================
# Before Guardrail 테스트
# =====================

# 4. 욕설 포함 메시지
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "씨발 왜 환불이 안 되는 거야",
    "thread_id": "guardrail-test-1",
    "user_id": "cust-002"
  }'
# 기대: {"status": "blocked", "response": "부적절한 언어가..."}

# =====================
# context= 전달 확인
# =====================

# 5. 선호도 저장 (user_id가 context로 전달되어 ToolRuntime에서 사용)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "앞으로 영어로만 답변해줘",
    "thread_id": "ctx-test-1",
    "user_id": "cust-003"
  }'

# 6. 새 대화에서 선호도 반영 확인 (InjectMemoryMiddleware)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "환불 정책 알려줘",
    "thread_id": "ctx-test-2",
    "user_id": "cust-003"
  }'
# 기대: 영어로 답변 (InjectMemoryMiddleware가 선호도 주입)
```

---

## Phase 4 핵심 구조 요약

```
[create_agent 마이그레이션]
create_react_agent (legacy)     →  create_agent (현대 표준)
  prompt=callable                   system_prompt=str + middleware=[]
  InjectedStore+RunnableConfig      ToolRuntime[AgentContext]
  config["configurable"]["user_id"] context=AgentContext(user_id=...)

[PIIMiddleware 흐름]
HumanMessage("카드 1234-5678-9012-3456")
  → PIIMiddleware.before_model
  → HumanMessage("카드 ****-****-****-3456")  ← checkpointer에도 마스킹된 버전 저장
  → 모델 호출
AIMessage("카드 ****-****-****-3456으로...")  ← 이미 마스킹됨
  → PIIMiddleware.after_model (추가 마스킹)
  → 응답

[Before Guardrail 흐름]
입력 → is_blocked_input() → 욕설?
  YES → 즉시 "blocked" 반환 (agent.invoke() 호출 없음)
  NO  → 계속

[After Guardrail 흐름]
agent.invoke() 완료
  → ToolMessage 중 name="search_documents" 수집
  → 있음? → check_hallucination(answer, context)
              GPT-4o-mini: OK → 원본 / HALLUCINATION → fallback
  → 없음? → 검증 생략 (일반 대화)
```

---

## 검증 체크리스트

### agent/tools.py
- `ToolRuntime[AgentContext]`가 `InjectedStore + RunnableConfig`를 대체하는 이유 이해
- `runtime.context.user_id` vs `config["configurable"].get("user_id")` 차이 이해
- `from langchain.tools import ToolRuntime`이 공식 import 경로임을 이해

### agent/middleware.py
- `InjectMemoryMiddleware`가 `make_inject_memory` 팩토리 패턴을 대체하는 이유 이해
- `before_model(state, runtime)` 훅의 반환값 의미 이해 (None vs dict)
- `is_blocked_input` 단락 패턴의 필요성 이해
- `check_hallucination`이 search_contexts 있을 때만 호출되는 이유 이해

### agent/agent.py
- `create_react_agent` vs `create_agent` 핵심 차이 이해
- `PIIMiddleware` 커스텀 detector가 필요한 이유 이해 (한국어, 하이픈)
- `context_schema=AgentContext`의 역할 이해

### routers/chat.py
- `config`에서 `user_id`가 빠진 이유 이해 (`context=`로 분리됨)
- PII 마스킹이 chat.py에서 사라진 이유 이해 (PIIMiddleware로 이동)
- Before/After Guardrail의 실행 위치와 이유 이해

---

## Production 전환 시 고려사항

```
PIIMiddleware:
  기본 detector의 한계(한국어, Luhn 검증) → 커스텀 detector로 해결
  추가 PII 타입 필요 시:
    PIIMiddleware("phone", detector=r"0\d{1,2}-\d{3,4}-\d{4}", strategy="mask")
    PIIMiddleware("ssn", detector=r"\d{6}-[1-4]\d{6}", strategy="block")

Before Guardrail:
  키워드 기반의 한계 → LLM 기반 분류 또는 전용 라이브러리로 교체
  (better-profanity, toxic-bert 등)

After Guardrail:
  이진 판정의 한계 → 신뢰도 점수 + 재답변 요청 방식으로 개선 가능

context_schema:
  현재 AgentContext(user_id, user_tier) → Phase 5에서 user_tier 활용 예정
```

---

## 다음 단계

Phase 4를 완료했으면:

- **Phase 5**: Human-in-the-loop
  - 환불·계좌 변경 등 민감 작업은 에이전트가 임의 처리 불가
  - `interrupt()`로 실행 일시 중단 → 관리자 승인 대기
  - `status: "pending_approval"` 응답 → 프론트에서 "관리자 검토 중" 표시
  - `POST /approve`로 승인/거절 → `Command(resume=...)` 으로 에이전트 재개
