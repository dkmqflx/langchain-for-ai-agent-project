# Phase 4 학습 가이드 — PII + Guardrail Middleware

이 가이드는 Phase 4의 2개 수정 파일을 의존성 순서대로 학습할 수 있도록 구성되었습니다.

---

## Phase 4에서 새로 추가된 것

Phase 3까지는 에이전트가 "무방비" 상태였습니다.

```
[Phase 3 문제]

고객: "씨발 환불해줘"
Agent: "안녕하세요! 환불 정책은..." ← 욕설을 그냥 처리 😱

고객: "내 카드 1234-5678-9012-3456로 결제했는데..."
Agent: "1234-5678-9012-3456 카드로..." ← 카드번호를 그대로 반복 😱

Agent: "환불은 7일 이내 가능합니다" ← (문서엔 30일이라고 적혀있는데 날조!)
고객: 잘못된 정보를 믿고 행동 😱
```

Phase 4는 세 가지 안전 장치를 추가합니다:

```
[Phase 4 해결]

PII 마스킹:
  "내 카드 1234-5678-9012-3456..." → "내 카드 ****-****-****-3456..."
  "이메일 a@b.com 이에요" → "이메일 [EMAIL REDACTED] 이에요"

Before Guardrail (욕설 차단):
  "씨발 환불해줘" → "부적절한 언어가 포함되어 있어 처리할 수 없습니다." ✅
  에이전트 실행 없음 (비용 절약)

After Guardrail (할루시네이션 방지):
  Agent: "환불은 7일 이내 가능합니다"
  문서에는 30일이라 적혀있음
  GPT-4o-mini: "HALLUCINATION" 판정
  최종 응답: "관련 정보를 문서에서 찾을 수 없습니다." ✅
```

---

## 학습 흐름도

```
[수정된 파일]
middleware.py → mask_pii, is_blocked_input, check_hallucination 추가
routers/chat.py → 미들웨어 파이프라인 통합

[요청 처리 파이프라인]
POST /chat {"message": "씨발 환불해줘", ...}
     ↓
[1] mask_pii(message)         → PII 마스킹 (이메일, 카드번호)
     ↓
[2] is_blocked_input(message) → 욕설 감지 → 차단 시 즉시 반환 (에이전트 미실행)
     ↓ (차단 안 됨)
[3] agent.invoke(...)         → ReAct Agent 실행
     ↓
[4] ToolMessage 분석          → search_documents 호출 결과 수집
     ↓
[5] check_hallucination(...)  → 컨텍스트 있을 때만 GPT-4o-mini로 검증
     ↓
[6] mask_pii(answer)          → 출력 PII 마스킹
     ↓
응답 반환
```

---

## Step 1: `agent/middleware.py` 읽기 — PII 마스킹 (15분)

### 목표

정규식으로 개인정보를 어떻게 탐지하고 치환하는지 이해

---

### 핵심 개념 1: 정규식 (Regular Expression) 기초

정규식은 문자열 패턴을 찾는 "암호"입니다.

```
일반 검색:     "test@gmail.com" 찾기   → 정확히 이 문자열만 찾음
정규식 검색:   이메일 패턴 찾기         → a@b.com, hello@company.org 등 모두 찾음
```

**이메일 정규식 분해:**

```python
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
```

```
[a-zA-Z0-9._%+\-]+   → 영문자·숫자·특수문자 1개 이상   (예: test.user+1)
@                    → @ 기호 (문자 그대로)
[a-zA-Z0-9.\-]+      → 영문자·숫자·점·하이픈 1개 이상  (예: gmail.com)
\.                   → 점 (문자 그대로, . 은 정규식에서 "아무 문자"라서 이스케이프 필요)
[a-zA-Z]{2,}         → 영문자 2개 이상                 (예: com, org, io)

전체: test.user@gmail.com ✅   user@company.co.kr ✅
```

**카드번호 정규식 분해:**

```python
_CARD_RE = re.compile(r"(?<!\d)(\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?)(\d{4})(?!\d)")
```

```
(?<!\d)          → 앞에 숫자가 없어야 함 (15자리, 17자리 숫자 오탐 방지)
(\d{4}[-\s]?)    → 숫자 4개 + 선택적 하이픈 또는 공백
                   세 번 반복 = 앞 12자리 (그룹 1)
(\d{4})          → 마지막 4자리 (그룹 2)
(?!\d)           → 뒤에 숫자가 없어야 함

예:  1234-5678-9012-3456  ✅ (하이픈 구분)
     1234 5678 9012 3456  ✅ (공백 구분)
     1234567890123456     ✅ (구분자 없음)
     12345678901234567    ❌ (17자리 → 오탐 방지)
```

---

### 핵심 개념 2: `\b` 대신 lookahead/lookbehind를 쓰는 이유

처음에 `\b` (단어 경계)를 쓰려고 했지만 한국어에서 실패합니다.

```
\b가 작동하는 원리:
  단어 문자(\w: 영문자·숫자·밑줄)와 비단어 문자 사이의 경계

  "abc 123 def"
       ↑↑↑↑
       \b가 여기에 있음 (공백 ← 비단어, 숫자 → 단어)
```

```
한국어에서의 문제:
  Python re 모듈의 \w는 유니코드 기본 설정에서
  한글도 단어 문자로 인식

  "카드번호 1234...3456입니다"
                      ↑
                    6과 입 사이 → 둘 다 \w → 경계 없음! → \b 실패 ❌
```

```
해결: lookahead/lookbehind (탐색 경계 사용)

  (?<!\d)  — "앞에 숫자가 없을 때만" (negative lookbehind)
  (?!\d)   — "뒤에 숫자가 없을 때만" (negative lookahead)

  이 문자들은 실제 매칭에 포함되지 않고 조건만 검사
  → 한글이 뒤에 와도 정상 작동 ✅
```

---

### 핵심 개념 3: 입력과 출력 모두 마스킹하는 이유

```
[입력만 마스킹하면 충분한가?]

고객: "이메일 test@gmail.com 이에요"
  → mask_pii → "이메일 [EMAIL REDACTED] 이에요"
  → Agent에 전달 (마스킹된 버전)
  → checkpointer에 "[EMAIL REDACTED]"로 저장 ✅ (PII가 단기 기억에 없음)

[그런데 왜 출력도 마스킹?]

시나리오:
  고객: "이메일 a@b.com 이에요 문의드립니다"
  Agent가 검색 없이 바로 답변:
    "안녕하세요 a@b.com 고객님, 도와드릴게요!"
    ← Agent가 입력에서 이메일을 그대로 반복!

  출력 마스킹이 없으면:
    응답: "안녕하세요 a@b.com 고객님..." → PII 노출 ❌

  출력 마스킹 적용:
    응답: "안녕하세요 [EMAIL REDACTED] 고객님..." ✅

비유: 입구(입력)와 출구(출력) 양쪽에 검문소 설치.
     입구에서 잡아도 내부에서 다시 PII가 생길 수 있음.
```

---

### 학습 질문

- `re.compile()`을 매번 함수 안에서 쓰지 않고 모듈 레벨에서 쓰는 이유는?
- `r"..."` (raw string)을 쓰는 이유는? (힌트: `\n`, `\t` 등의 이스케이프 시퀀스)
- `re.sub(r"****-****-****-\2", text)`에서 `\2`는 무슨 의미인가?

---

## Step 2: `agent/middleware.py` 읽기 — Before Guardrail (10분)

### 목표

키워드 기반 차단이 왜 "단락(short-circuit)" 패턴이어야 하는지 이해

---

### 핵심 개념 1: Before Guardrail 설계

```python
_BLOCKED_KEYWORDS = ["씨발", "개새끼", ..., "fuck", "shit", ...]

def is_blocked_input(text: str) -> tuple[bool, str]:
    text_lower = text.lower()
    for keyword in _BLOCKED_KEYWORDS:
        if keyword in text_lower:
            return True, "부적절한 언어가..."
    return False, ""
```

**반환값이 `(bool, str)` tuple인 이유:**

```
# 만약 bool만 반환하면:
blocked = is_blocked_input(text)
if blocked:
    return {"response": "???"}  # 거절 메시지를 어디서 가져와?

# tuple 반환:
blocked, reason = is_blocked_input(text)
if blocked:
    return {"response": reason}  # 거절 메시지도 함께 전달 ✅
```

**`text.lower()`를 쓰는 이유:**

```
"FUCK" ← 대문자로 욕설 → .lower() 없으면 필터 통과 ❌
"FuCk" ← 혼합 대소문자 → .lower() 없으면 통과 ❌

.lower()로 소문자 변환 후 비교 → 대소문자 무관 ✅
```

---

### 핵심 개념 2: 단락(short-circuit) 패턴

단락은 불필요한 처리를 조기에 멈추는 패턴입니다.

```python
# chat.py
blocked, reason = is_blocked_input(clean_message)
if blocked:
    return {                    # ← 즉시 반환! agent.invoke()를 전혀 안 씀
        "data": {"response": reason, "status": "blocked"},
    }

agent = get_agent()            # ← 여기까지 오지 않음
result = await agent.invoke(...)
```

**단락이 필요한 이유:**

```
[단락 없이 처리하면]
"씨발 환불해줘"
  → ChatOpenAI API 호출 (토큰 비용 발생 💸)
  → 욕설이 checkpointer에 저장 (단기 기억에 부적절 내용 남음 😱)
  → Agent가 욕설 포함 메시지를 처리 (의도치 않은 행동 가능성)

[단락으로 처리하면]
"씨발 환불해줘"
  → 키워드 검사 (CPU 연산만, API 호출 없음)
  → 즉시 거절 반환
  → API 비용 0, checkpointer에도 저장 안 됨 ✅
```

**비유: 건물 경비원**

```
건물 입구 = is_blocked_input
경비원이 입구에서:
  신분증 확인 → 문제 있으면 입장 거부 (엘리베이터까지 가지 않음)
  신분증 OK → 통과

단락 없이:
  건물 안에 들어가서 / 엘리베이터 타고 / 층 올라가서 / 경비원이 쫓아냄
  → 불필요한 자원 낭비
```

---

### 한계와 실서비스 고려사항

```
현재 구현의 한계:
  1. 키워드를 변형하면 탈출 가능: "씨_ 발", "s h i t"
  2. 새로운 욕설은 목록에 추가해야 함
  3. 단어 맥락 무시: "바보 같은 제 실수" → "바보"에 차단됨

실서비스 대안:
  - LLM 기반 분류: "이 메시지가 부적절한가?" (더 정확하지만 비용 증가)
  - 전용 필터 라이브러리: profanity-filter, better-profanity 등
  - 하이브리드: 키워드(빠름) + LLM(정확) 조합
```

---

### 학습 질문

- `is_blocked_input`이 `True`를 반환할 때 `agent.invoke()`가 실행되지 않는 이유는?
- `text.lower()`를 적용하면 한국어 욕설 탐지에도 영향이 있을까?
- 욕설 필터를 통과한 메시지에도 악의적 내용이 있을 수 있다면, 어떤 추가 방어 방법이 있을까?

---

## Step 3: `agent/middleware.py` 읽기 — After Guardrail (20분)

### 목표

할루시네이션이 무엇인지, GPT-4o-mini 감시자 패턴이 왜 효과적인지 이해

---

### 핵심 개념 1: 할루시네이션(Hallucination)이란?

```
AI가 사실이 아닌 내용을 자신있게 답변하는 현상.

[예시]
문서 내용: "환불은 구매 후 30일 이내에 가능합니다."
Agent 답변: "환불은 7일 이내에 신청하셔야 합니다."

이 답변은:
  - 자신감 있어 보임 ← 사용자가 믿을 수 있음
  - 하지만 문서와 다름 ← 잘못된 정보
  → 고객이 7일 지나서 환불 안 된다고 생각 → 실제로는 30일까지 가능했는데!
```

**왜 발생하는가:**

```
LLM은 "모른다"고 말하는 것이 불편함.
문서에서 정확한 정보를 못 찾아도, 학습 데이터에서 비슷한 패턴을 만들어 답변.
→ 그럴듯하지만 틀린 답변 생성
```

---

### 핵심 개념 2: 감시자(Watcher) 패턴

```
[감시자 패턴 없이]
고객 질문 → Main Agent (GPT-4o) → 답변 (틀릴 수도 있음)
                                        ↓
                                   고객에게 전달

[감시자 패턴 적용]
고객 질문 → Main Agent (GPT-4o) → 답변
                                        ↓
                               Watcher (GPT-4o-mini)
                                 "이 답변이 문서에 근거하는가?"
                                        ↓
                               OK → 그대로 전달
                               HALLUCINATION → 교정 메시지로 교체
```

**왜 GPT-4o-mini인가:**

```
Main Agent: GPT-4o (더 강력, 더 비쌈)
  → 복잡한 추론, 문서 이해, 도구 사용 등 어려운 작업

Watcher: GPT-4o-mini (더 빠름, 더 쌈)
  → 단순한 이진 판단 ("OK" or "HALLUCINATION")
  → 복잡한 추론 불필요

비유: 전문의(GPT-4o)가 진단하고, 간호사(GPT-4o-mini)가 처방전 검토.
```

---

### 핵심 개념 3: 검증 프롬프트 설계

```python
_HALLUCINATION_PROMPT = """당신은 AI 답변 품질 검사관입니다.

아래 [컨텍스트]에 근거하지 않은 사실이 [답변]에 포함되어 있으면 "HALLUCINATION"이라고만 답하세요.
컨텍스트에 기반한 정확한 답변이라면 "OK"라고만 답하세요.

[컨텍스트]
{context}

[답변]
{answer}"""
```

**프롬프트 설계의 핵심:**

```
1. 역할 명시: "AI 답변 품질 검사관"
   → LLM에게 맥락을 부여. "검사관"은 비판적으로 봐야 함을 암시.

2. 컨텍스트를 먼저: [컨텍스트] → [답변] 순서
   → 기준을 먼저 보고 답변을 평가. 순서가 반대면 답변에 끌려갈 수 있음.

3. 이진 출력 강제: "HALLUCINATION" 또는 "OK"만
   → "글쎄요...", "어느 정도는..." 같은 모호한 답변 방지
   → 파싱이 쉬움 ("HALLUCINATION" in response)

4. 추가 설명 금지
   → 검증 모델의 출력이 길면 파싱 오류 가능성
   → "이라고만" 강조로 간결한 출력 유도
```

---

### 핵심 개념 4: 컨텍스트가 없을 때 검증을 생략하는 이유

```python
# chat.py
if search_contexts:           # ← search_documents가 호출된 경우에만
    combined_context = "\n\n---\n\n".join(search_contexts)
    ai_message = check_hallucination(ai_message, combined_context)
```

**컨텍스트 없이 검증하면 오탐이 발생합니다:**

```
[시나리오 1: 일반 인사]
고객: "안녕하세요"
Agent: "안녕하세요! 무엇을 도와드릴까요?"

검색 없음 → 컨텍스트 없음
만약 검증 실행:
  Watcher에게: context="" / answer="안녕하세요! 무엇을..."
  Watcher: "컨텍스트에 없는 내용이네..." → "HALLUCINATION" 판정 ❌
  실제로는 완전히 정상적인 답변인데!

[시나리오 2: 선호도 저장]
고객: "앞으로는 영어로만 답해줘"
Agent: "알겠습니다! 영어로 답변드리겠습니다." (save_user_preference 호출)

검색 없음 → 컨텍스트 없음
검증 생략 → 정상 응답 그대로 전달 ✅
```

---

### 핵심 개념 5: 검색 컨텍스트 추출 방법

Phase 4에서는 `result["messages"]`를 직접 분석하여 컨텍스트를 추출합니다.

```python
# chat.py
search_contexts = [
    msg.content
    for msg in result["messages"]
    if isinstance(msg, ToolMessage) and msg.name == "search_documents"
]
```

**agent.invoke() 결과의 메시지 구조:**

```
result["messages"] = [
    HumanMessage("환불 정책이 어떻게 돼요?"),
    AIMessage(tool_calls=[{"name": "search_documents", "args": {...}}]),
    ToolMessage(content="[출처: ...]\n환불은 30일...", name="search_documents"),  ← 여기서 추출
    AIMessage("환불 정책에 따르면 30일 이내..."),  ← 최종 답변
]
```

**에이전트가 두 번 검색한 경우:**

```
result["messages"] = [
    HumanMessage("..."),
    AIMessage(tool_calls=[search_documents]),
    ToolMessage(content="첫 번째 검색 결과", name="search_documents"),  ← 수집
    AIMessage(tool_calls=[search_documents]),  # 추가 검색
    ToolMessage(content="두 번째 검색 결과", name="search_documents"),  ← 수집
    AIMessage("최종 답변"),
]

search_contexts = ["첫 번째 검색 결과", "두 번째 검색 결과"]
combined_context = "첫 번째 검색 결과\n\n---\n\n두 번째 검색 결과"
```

**왜 모듈 레벨 dict 방식을 안 쓰는가:**

```
# 다른 방법: 모듈 레벨 dict에 저장
_search_contexts: dict[str, list] = {}  # thread_id → 검색 결과

# 문제점:
# 1. 대화가 끝나도 메모리에 남음 → 서버 장시간 운영 시 메모리 누수
# 2. 동시 요청 처리 시 같은 thread_id 충돌 가능성
# 3. cleanup 로직 필요 (언제 dict에서 지울지?)

# ToolMessage 분석 방식:
# 상태가 없음 → 메모리 누수 없음
# 요청마다 독립 → 동시성 문제 없음
# cleanup 불필요 → 코드 단순
```

---

### 학습 질문

- `check_hallucination`이 search_documents 결과가 없을 때 호출되면 어떤 일이 벌어질까?
- Watcher가 "HALLUCINATION"으로 오판하면 (실제로는 정확한 답변인데)? 어떻게 개선할까?
- 감시자 모델을 `_get_monitor_llm()`처럼 lazy 초기화한 이유는?

---

## Step 4: `routers/chat.py` 읽기 (15분)

### 목표

미들웨어 파이프라인이 chat.py에서 어떻게 조합되는지 이해

---

### 핵심 개념 1: 파이프라인 패턴

```python
@router.post("/chat")
async def chat(request: ChatRequest):
    # [1] 입력 PII 마스킹
    clean_message = mask_pii(request.message)

    # [2] Before Guardrail
    blocked, reason = is_blocked_input(clean_message)
    if blocked:
        return {..., "status": "blocked"}

    # [3] Agent 실행
    result = await agent.invoke(...)

    # [4] 검색 컨텍스트 추출
    search_contexts = [
        msg.content
        for msg in result["messages"]
        if isinstance(msg, ToolMessage) and msg.name == "search_documents"
    ]

    # [5] After Guardrail
    if search_contexts:
        combined_context = "\n\n---\n\n".join(search_contexts)
        ai_message = check_hallucination(ai_message, combined_context)

    # [6] 출력 PII 마스킹
    ai_message = mask_pii(ai_message)

    return {..., "status": "completed"}
```

**파이프라인 설계 원칙: 순서가 중요합니다**

```
[입력 PII → Before Guardrail] 순서가 중요한 이유:
  PII 마스킹 먼저:
    "카드 1234-5678-9012-3456 환불해줘"
    → "카드 ****-****-****-3456 환불해줘"
    → 욕설 없음, 통과

  만약 순서가 반대면:
    Before Guardrail 먼저 (통과)
    PII 마스킹: "카드 ****-****-****-3456 환불해줘"
    → Agent에 마스킹된 메시지 전달 ✅ (결과는 같음)
    
  실제로 이 두 경우는 결과가 같지만 PII 먼저 하는 것이 관례:
    "욕설이 포함된 PII 메시지"를 처리할 때
    PII 먼저 마스킹 → checkpointer에 마스킹된 버전만 저장 ✅

[After Guardrail → 출력 PII 마스킹] 순서가 중요한 이유:
  할루시네이션 검증 먼저:
    answer = "고객 test@mail.com 님의 환불은 7일 이내..."
    → 할루시네이션 판정 → fallback 메시지로 교체
    → PII 마스킹: fallback 메시지에는 PII 없음 (이미 교체됨)

  만약 순서가 반대면:
    PII 마스킹 먼저:
    → answer = "고객 [EMAIL REDACTED] 님의 환불은 7일 이내..."
    → 할루시네이션 검증 (마스킹된 답변으로 검증)
    → 결과는 동일하지만 검증 프롬프트에 "[EMAIL REDACTED]"가 들어가서 약간 부자연스러움
```

---

### 핵심 개념 2: status 필드의 의미

```json
{
  "status": "completed"  → 정상 처리
  "status": "blocked"    → Before Guardrail에 의해 차단
}
```

```
Phase 5에서 추가될 상태:
  "status": "pending_approval" → Human-in-the-loop 대기 중
  (환불 같은 민감 작업은 관리자 승인 대기)

프론트엔드에서 status를 보고 UI 처리:
  completed → 답변 표시
  blocked   → "부적절한 언어..." 표시
  pending_approval → "관리자 검토 중" 표시 (Phase 6)
```

---

### 학습 질문

- `clean_message = mask_pii(request.message)`이면서 왜 `agent.invoke({"messages": [("human", clean_message)]})`에 `clean_message`를 넣는가? (hint: checkpointer에 저장되는 내용)
- Phase 3의 chat.py와 비교했을 때 어떤 줄이 추가되었는가?
- `search_contexts`가 빈 리스트면 `"\n\n---\n\n".join([])`의 결과는?

---

## 전체 흐름 실습 (20분)

서버를 실행하고 curl로 각 미들웨어를 직접 테스트하세요.

```bash
# 1. 서버 실행
cd customer-support-agent/backend
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# =====================
# PII 마스킹 테스트
# =====================

# 2. 이메일 포함 메시지
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "안녕하세요, 제 이메일은 test@example.com이에요",
    "thread_id": "pii-test-1",
    "user_id": "cust-001"
  }'
# 기대: 응답에 test@example.com 없음, [EMAIL REDACTED] 처리

# 3. 카드번호 포함 메시지
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "카드 1234-5678-9012-3456으로 결제했는데 환불해줘",
    "thread_id": "pii-test-2",
    "user_id": "cust-001"
  }'
# 기대: 응답에 ****-****-****-3456 처리

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
# 확인: status가 "completed"가 아닌 "blocked"

# =====================
# After Guardrail 테스트 (문서 필요)
# =====================

# 5. 먼저 테스트용 문서 업로드
# refund_policy.txt 내용: "환불은 구매 후 30일 이내에 신청 가능합니다."
curl -X POST http://localhost:8000/upload \
  -F "file=@refund_policy.txt"

# 6. 문서에 없는 내용 질문 (할루시네이션 유발 가능성)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "환불 가능 기간이 얼마나 되나요?",
    "thread_id": "guardrail-test-2",
    "user_id": "cust-003"
  }'
# 기대: 30일 기반 답변 (문서 내용 기반)
# After Guardrail이 문서와 일치 여부 검증 후 응답

# 7. Swagger UI
# http://localhost:8000/docs
```

---

## Phase 4 핵심 구조 요약

```
[Before Guardrail 흐름]
입력 메시지
     ↓
mask_pii(입력) → PII 제거
     ↓
is_blocked_input() → 욕설 감지?
  YES → 즉시 "blocked" 반환 (API 호출 없음, 비용 절약)
  NO  → 계속

[After Guardrail 흐름]
agent.invoke() 완료
     ↓
result["messages"]에서 ToolMessage 수집
(name="search_documents")
     ↓
search_contexts 있음?
  NO  → 검증 생략 (일반 대화, 선호도 저장 등)
  YES → check_hallucination(answer, context)
            ↓
        GPT-4o-mini 판정
          OK          → 원본 답변 유지
          HALLUCINATION → fallback 메시지로 교체
     ↓
mask_pii(출력) → 출력 PII 제거
     ↓
"completed" 응답 반환
```

---

## 검증 체크리스트

### middleware.py — PII 마스킹
- `_EMAIL_RE`가 다양한 이메일 형식을 탐지하는지 이해 (서브도메인, 특수문자 포함)
- `_CARD_RE`에서 `\b` 대신 lookahead/lookbehind를 쓰는 이유 이해 (한국어 유니코드)
- 입력과 출력 모두 마스킹하는 이유 이해 (checkpointer 저장 + 에이전트 반복 방지)

### middleware.py — Before Guardrail
- `is_blocked_input`이 `(bool, str)` tuple을 반환하는 이유 이해
- `.lower()` 변환이 필요한 이유 이해
- 키워드 기반 필터의 한계와 실서비스 대안 이해

### middleware.py — After Guardrail
- 할루시네이션이 무엇인지, 왜 위험한지 이해
- 감시자(Watcher) 패턴의 구조 이해
- 검증을 search_contexts가 있을 때만 실행하는 이유 이해
- `_get_monitor_llm()` lazy 초기화의 이유 이해

### routers/chat.py
- 파이프라인 6단계 순서와 각 단계의 목적 이해
- `clean_message`가 Agent에 전달되는 이유 (checkpointer에 PII 저장 방지)
- `status` 필드 값의 종류와 의미 이해

---

## Production 전환 시 고려사항

```
현재 구현의 제한:
  Before Guardrail: 키워드 기반 → 변형 욕설 통과 가능
  After Guardrail:  단순 이진 판정 → 오탐 가능성
  PII 마스킹: 이메일/카드만 → 주민번호, 전화번호 등 미처리

Production 개선:
  Before Guardrail:
    - LLM 기반 분류 모델 (더 정확하지만 비용 증가)
    - 전용 라이브러리 (better-profanity, toxic-bert 등)
    - 하이브리드: 키워드(1차, 빠름) + LLM(2차, 정확)

  After Guardrail:
    - 신뢰도 점수 추가: "HALLUCINATION (0.87)" 형식
    - 교정 시도: 거절 대신 "문서 기반으로 재답변" 요청
    - 로깅: 할루시네이션 발생 사례 수집 → 프롬프트 개선

  PII 마스킹:
    - 주민번호: r"\d{6}-[1-4]\d{6}"
    - 전화번호: r"0\d{1,2}-\d{3,4}-\d{4}"
    - Presidio(Microsoft) 같은 전문 NLP 라이브러리 도입
```

---

## 다음 단계

Phase 4를 완료했으면:

- **Phase 5**: Human-in-the-loop
  - 환불·계좌 변경 같은 민감 작업은 에이전트가 임의 처리 불가
  - `interrupt()`로 실행을 일시 중단하고 관리자 승인 대기
  - 관리자가 `/approve` 엔드포인트로 승인/거절하면 에이전트 재개
  - `status: "pending_approval"` 상태로 프론트엔드에 알림
