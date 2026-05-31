# Phase 2 학습 가이드 — Agent + Hybrid Search

이 가이드는 Phase 2의 5개 파일을 의존성 순서대로 학습할 수 있도록 구성되었습니다.

---

## Phase 2에서 새로 추가된 것

Phase 1은 "문서를 저장하는 파이프라인"이었다면,
Phase 2는 "저장된 문서를 검색해서 AI가 답변하는 파이프라인"입니다.

```
[Phase 1] 문서 저장 파이프라인
  업로드 → 청킹 → 임베딩 → pgvector 저장
  (책을 도서관에 꽂아두는 작업)

[Phase 2] 질문-답변 파이프라인 (새로 추가)
  질문 → Agent → 검색 도구 호출 → 문서 검색 → 답변 생성
  (사서가 책을 찾아서 독자에게 설명해주는 작업)
```

---

## 학습 흐름도

```
고객: "환불은 어떻게 해요?"
     ↓
[1] main.py       → FastAPI 서버 진입점 (요청을 각 담당자에게 연결)
     ↓
[2] api/chat.py   → POST /chat 요청 처리 (고객 질문 접수)
     ↓
[3] agent/agent.py → ReAct Agent 실행 (어떻게 답할지 생각)
     ↓
[4] agent/tools.py → search_documents Tool 호출 (문서 검색)
     ↓
[5] pgvector       → 관련 청크 검색 (BM25 + Vector)
     ↓
"환불은 30일 이내에 고객센터로 연락하시면..."
```

---

## Step 1: `agent/tools.py` 읽기 (20분)

### 목표

Agent가 "도구"를 어떻게 사용하는지, Hybrid Search가 무엇인지 이해

---

### 핵심 개념 1: Tool (도구)이란?

**비유: 직원과 참고서**

```
신입 고객 지원 직원이 있습니다.
  직원 혼자서는 회사 정책을 다 외울 수 없습니다.
  그래서 회사 정책 매뉴얼(도구)을 사용합니다.

고객: "환불은 언제까지 가능해요?"
직원: (매뉴얼을 찾아보고) "30일 이내에 가능합니다"
```

코드에서 Agent = 직원, search_documents = 매뉴얼입니다.

```python
@tool
def search_documents(query: str) -> str:
    """
    업로드된 회사 문서에서 관련 내용을 검색합니다.
    고객 질문에 답변하기 위해 정책, 매뉴얼, FAQ 등을 검색할 때 사용하세요.
    """
```

**@tool 데코레이터가 하는 일:**

`@tool`은 이 함수를 "Agent가 사용할 수 있는 도구"로 등록합니다.

중요한 점은 **docstring(함수 설명)**입니다.

```python
@tool
def search_documents(query: str) -> str:
    """
    업로드된 회사 문서에서 관련 내용을 검색합니다.
    ↑ 이 설명이 GPT에게 전달됩니다!
    GPT는 이 설명을 보고 "언제 이 도구를 써야 하는지" 판단합니다.
    """
```

```
GPT 내부 판단 과정:
  "고객이 환불에 대해 물어봤다"
  "나한테 search_documents 라는 도구가 있다"
  "설명을 보니 '회사 문서에서 검색'하는 도구네"
  "그러면 이 도구를 사용해야겠다"
  → search_documents("환불 정책") 호출
```

docstring이 불명확하면 GPT가 언제 도구를 써야 하는지 모릅니다.

---

### 핵심 개념 2: Hybrid Search = BM25 + Vector

두 가지 검색 방식을 합쳐서 더 정확한 결과를 만드는 방법입니다.

**BM25 (키워드 검색):**

```
비유: 책 색인(인덱스)에서 단어 찾기

"환불" 검색
→ 색인에서 "환불"이라는 단어가 포함된 페이지 찾기
→ 정확한 단어 매칭

장점: "ORD-12345 주문번호" 같은 정확한 단어 매칭에 강함
단점: "반품"이라고 검색하면 "환불" 문서를 못 찾음
      (같은 의미지만 단어가 다름)
```

**Vector 검색 (의미 검색):**

```
비유: 의미를 알고 있는 사서에게 물어보기

"환불" 검색
→ "환불", "반품", "돌려보내다" 등 비슷한 의미의 문서 모두 찾기

장점: 동의어, 유사어로 검색해도 관련 문서를 찾음
단점: "ORD-12345" 같은 고유한 코드는 의미가 없어서 찾기 어려움
```

**Hybrid (둘을 합치면):**

```
BM25:   [A(1위), B(2위), C(3위)]   ← 정확한 단어 매칭
Vector: [B(1위), C(2위), D(3위)]   ← 의미 유사도

두 결과를 RRF 알고리즘으로 합산
→ 단어 매칭도 되고, 의미 검색도 되는 최고의 결과
```

---

### 핵심 개념 3: RRF (Reciprocal Rank Fusion) 알고리즘

두 검색 결과를 어떻게 합치는지에 대한 방식입니다.

**비유: 두 심사위원의 점수 합산**

```
심사위원 A (BM25): [청크1(1위), 청크2(2위), 청크3(3위)]
심사위원 B (Vector): [청크2(1위), 청크3(2위), 청크4(3위)]

RRF 점수 = 1/순위 로 계산:
  청크1: 1/1 + 0   = 1.00  (A에서만 1위)
  청크2: 1/2 + 1/1 = 1.50  (A에서 2위 + B에서 1위) ← 최종 1위
  청크3: 1/3 + 1/2 = 0.83  (A에서 3위 + B에서 2위)
  청크4: 0   + 1/3 = 0.33  (B에서만 3위)

최종 순위: 청크2 → 청크1 → 청크3 → 청크4
```

양쪽 심사위원 모두에게 좋은 점수를 받은 청크2가 최종 1위가 됩니다.

---

### 핵심 개념 4: BM25 인덱스와 build_bm25()

**왜 BM25 인덱스가 필요한가?**

```
BM25는 검색 전에 미리 준비가 필요합니다.

비유: 도서관 카드 목록
  준비 없이 검색: 책장을 하나씩 뒤지며 찾기 (느림)
  BM25 인덱스:   미리 만들어둔 카드 목록에서 찾기 (빠름)
```

**build_bm25() 코드 설명:**

```python
def build_bm25():
    global _bm25_retriever
    # global: 함수 밖에 있는 _bm25_retriever 변수를 수정하겠다는 선언
    # global 없으면 함수 안에서만 변경되고, 밖에는 적용 안 됨

    docs = vectorstore.similarity_search("", k=10000)
    # pgvector에서 전체 문서 가져오기
    # "" (빈 쿼리) = "전부 다 줘"
    # k=10000 = 최대 10000개 (사실상 전체)

    if docs:
        _bm25_retriever = BM25Retriever.from_documents(docs, k=5)
        # 가져온 문서들로 BM25 인덱스 생성
        # k=5 = 검색 시 상위 5개 결과 반환
    else:
        _bm25_retriever = None
        # 문서가 없으면 인덱스 불필요
```

**언제 호출하는가:**

```
1. 앱 시작 시 (main.py lifespan)
   → "이미 DB에 저장된 문서가 있을 수 있으니 미리 인덱스 만들어놓자"

2. 새 문서 업로드 후 (upload.py POST /upload 성공 후)
   → "새 문서가 추가됐으니 인덱스 다시 만들어야 검색에 반영됨"
```

**Vector Retriever와의 핵심 차이:**

```python
# Vector Retriever
vector_retriever = vectorstore.as_retriever(...)
# → pgvector(PostgreSQL)에 벡터가 이미 저장되어 있음
# → 초기 로드 불필요 (필요할 때마다 DB 쿼리)

# BM25 Retriever
docs = vectorstore.similarity_search("", k=10000)  # pgvector에서 문서 가져오기
_bm25_retriever = BM25Retriever.from_documents(docs, k=5)  # 메모리로 인덱스 구성
# → 메모리 기반 인덱스 (빠름)
# → 초기에 from_documents()로 빌드 필수 (문서를 메모리에 올려야 검색 가능)
```


|           | Vector                    | BM25                       |
| --------- | ------------------------- | -------------------------- |
| **저장소**   | PostgreSQL (pgvector)     | 메모리                        |
| **초기화**   | 없음 - `as_retriever()`만 호출 | 필수 - `from_documents()` 호출 |
| **왜 다른가** | 고차원 벡터는 DB에 저장하기 좋음       | 키워드 검색은 메모리 인덱스가 빠름        |


**결론:** Vector는 데이터가 이미 DB에 있으니 초기화 불필요, BM25는 메모리에 인덱스를 만들어야 하니 초기화 필수

---

### 핵심 개념 5: EnsembleRetriever 설정

```python
return EnsembleRetriever(
    retrievers=[_bm25_retriever, vector_retriever],
    weights=[0.4, 0.6],  # BM25 40%, Vector 60%
)
```

**weights=[0.4, 0.6]을 이렇게 정한 이유:**

```
고객 지원에서는 "반품=환불" 같은 동의어 처리가 중요
→ 의미 검색(Vector)이 더 중요 → 60% 가중치

BM25는 보조 역할 (정확한 단어가 나올 때 점수 보정)
→ 40% 가중치
```

---

### 학습 질문

- @tool의 docstring이 불명확하면 어떤 문제가 생길까?
- BM25와 Vector 중 하나만 쓰면 어떤 경우에 문제가 생길까?
- _bm25_retriever가 None일 때 Vector만 사용하는 코드는 어디에 있을까?
- build_bm25()에서 global 키워드가 없으면 어떻게 될까?

---

## Step 2: `agent/agent.py` 읽기 (15분)

### 목표

ReAct Agent가 무엇인지, 어떻게 설정하는지 이해

---

### 핵심 개념 1: ReAct (Reasoning + Acting) 패턴

**비유: 탐정의 사건 해결 과정**

```
탐정: 단서를 보고 (Reasoning) → 행동하고 (Acting) → 결과를 보고 다시 생각
일반 GPT: 바로 답변 (단서 조사 없이)
```

코드에서:

```
고객: "환불하고 싶어요"

[Reasoning] Agent 생각:
  "환불 방법을 정확히 알려면 회사 문서를 확인해야겠다"

[Acting] 도구 호출:
  search_documents("환불 신청 방법") 실행

[Reasoning] 결과 확인:
  "검색 결과: 30일 이내, 고객센터 1234-5678로 연락"

[Acting] 최종 답변:
  "환불은 구매일로부터 30일 이내에 고객센터(1234-5678)로..."
```

문서 없이 그냥 답변하면 틀릴 수 있습니다 (할루시네이션).
ReAct는 먼저 확인하고 답변하므로 더 정확합니다.

---

### 핵심 개념 2: Agent 설정 파라미터

```python
_agent = create_agent(
    model=_llm,                    # [1] 어떤 AI 모델을 사용할지
    tools=[search_documents],      # [2] 어떤 도구를 사용할 수 있는지
    system_prompt=SYSTEM_PROMPT,   # [3] AI에게 역할을 어떻게 부여할지
)
```

**[1] model - 어떤 AI 모델을 사용할지**

```python
_llm = ChatOpenAI(
    model="gpt-4o",    # GPT-4o 사용 (가장 강력한 모델)
    temperature=0,     # 창의성 0 = 항상 일관된 답변
                       # temperature=1이면 매번 다른 답변
                       # 고객 지원은 정확성이 중요 → 0 설정
    streaming=True,    # 토큰 단위 스트리밍 준비 (Phase 6에서 활용)
)
```

**[2] tools - 어떤 도구를 사용할 수 있는지**

```python
tools=[search_documents]  # 현재는 문서 검색 도구만 있음

# Phase 5에서 추가될 것:
tools=[search_documents, process_refund]
#                        ↑ 환불 처리 도구 (관리자 승인 필요)
```

**[3] system_prompt - AI에게 역할 부여**

```python
SYSTEM_PROMPT = """당신은 B2B SaaS 고객 지원 에이전트입니다.
- 답변은 반드시 업로드된 회사 문서를 기반으로 하세요.
- 문서에 없는 내용은 "관련 정보를 문서에서 찾을 수 없습니다."라고 답변하세요.
"""
```

System Prompt가 없으면?

```
고객: "환불은 언제까지 가능해요?"

System Prompt 없음:
  GPT가 학습 데이터에서 일반적인 환불 정책 답변
  → "보통 30일이지만 회사마다 달라요..." (우리 회사 정책이 아님!)

System Prompt 있음:
  먼저 search_documents로 우리 회사 문서 검색
  → "저희 회사 환불 정책은 30일입니다" (정확한 답변!)
```

---

### 핵심 개념 3: Phase별 Agent 변화

```
Phase 2: create_agent(model, tools, system_prompt)
          ↓ "대화를 기억 못 함"
          고객: "아까 말한 주문번호로 환불해줘"
          Agent: "아까 말씀하신 게 뭔가요?" (기억 없음)

Phase 3: + checkpointer (단기 기억)
          고객: "아까 말한 주문번호로 환불해줘"
          Agent: "ORD-123 말씀하시는 거죠?" (기억 있음!)

Phase 3: + store (장기 기억)
          고객이 언젠가: "한국어로만 답변해줘"
          다음 대화에서도: 자동으로 한국어로 답변

Phase 5: + process_refund tool
          Agent가 직접 환불 처리 가능
          (단, 관리자 승인 필요)
```

---

### 학습 질문

- temperature=0.7로 바꾸면 어떤 변화가 생길까?
- tools 리스트에 도구가 여러 개면 Agent가 어떻게 선택할까?
- checkpointer가 없는 Phase 2에서 thread_id는 왜 받는 걸까?

---

## Step 3: `api/chat.py` 읽기 (10분)

### 목표

POST /chat 엔드포인트가 요청을 받아 Agent에 전달하는 흐름 이해

---

### 핵심 개념 1: Pydantic BaseModel (요청 스키마)

```python
class ChatRequest(BaseModel):
    message: str                  # 필수 - 없으면 에러
    thread_id: str = "default"    # 선택 - 없으면 "default" 사용
    user_id: str = "anonymous"    # 선택 - 없으면 "anonymous" 사용
```

**BaseModel을 쓰는 이유:**

```
비유: 호텔 체크인 양식

양식 없이: "이름이요? 날짜요? 방 종류요?" 하나하나 확인
양식 있음: 빠진 항목은 자동으로 에러 표시, 기본값 자동 입력

BaseModel 없이:
  개발자가 직접 검증 코드 작성
  def chat(request):
      if "message" not in request:
          return error
      if not isinstance(request["message"], str):
          return error
      ...

BaseModel 있으면:
  FastAPI가 자동으로 검증 → 코드 간결
```

자동으로 얻는 것:

- 타입 검증 (message가 숫자이면 자동으로 에러)
- [http://localhost:8000/docs](http://localhost:8000/docs) 에서 API 문서 자동 생성

---

### 핵심 개념 2: Agent 비동기 호출 (ainvoke)

```python
result = await agent.ainvoke(
    {"messages": [("human", request.message)]},
    # ↑ Agent에게 "이 메시지를 처리해줘" 라고 전달
    config=config,
    # ↑ thread_id 등 설정값 전달
)
```

**await를 쓰는 이유:**

```
비유: 음식 주문

await 없이 (blocking):
  요리사에게 주문 → 음식 나올 때까지 카운터에서 기다림
  그동안 다른 손님 주문 못 받음 (서버가 멈춤)

await 있이 (non-blocking):
  요리사에게 주문 → 다른 손님 주문 받음
  음식 완성되면 알림 → 해당 손님에게 전달

→ 여러 고객의 질문을 동시에 처리 가능
```

**result["messages"] 구조:**

Agent가 답변하기까지의 전체 과정이 담겨 있습니다.

```python
result["messages"] = [
    # 1. 고객 질문
    HumanMessage("환불하고 싶어요"),

    # 2. Agent가 도구 호출 결정
    AIMessage(tool_calls=[search_documents("환불 신청 방법")]),

    # 3. 도구 실행 결과
    ToolMessage("환불 정책: 30일 이내, 고객센터 1234-5678..."),

    # 4. 최종 답변 ← result["messages"][-1]
    AIMessage("환불은 구매일로부터 30일 이내에..."),
]

ai_message = result["messages"][-1].content
# [-1] = 마지막 항목 = 최종 답변
```

---

### 핵심 개념 3: config와 thread_id

```python
config = {"configurable": {"thread_id": request.thread_id}}

result = await agent.ainvoke(..., config=config)
```

**Phase 2에서 thread_id가 당장은 안 쓰이는데 왜 받는가:**

```
Phase 3에서 checkpointer(대화 기억)를 추가할 때
thread_id로 "어느 대화 세션인지" 구분합니다.

지금부터 API에 포함시켜두면
Phase 3 구현 시 프론트엔드 코드를 수정할 필요 없음.

"미래를 위한 자리 잡기"
```

---

### 학습 질문

- BaseModel에서 message 필드를 Optional[str] = None으로 바꾸면?
- ainvoke 대신 invoke를 쓰면 어떤 문제가 생길까?
- result["messages"][-1]이 ToolMessage일 수도 있을까?

---

## Step 4: `main.py` 읽기 (10분)

### 목표

FastAPI 앱 설정, CORS, lifespan 이벤트가 왜 필요한지 이해

---

### 핵심 개념 1: lifespan (앱 생명주기)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 앱 시작 시 실행 (yield 이전) ──
    build_bm25()  # BM25 인덱스 초기화
    yield
    # ── 앱 종료 시 실행 (yield 이후) ──
    # (현재 정리 작업 없음)
```

**비유: 가게 문 열기/닫기**

```
lifespan = 가게 문을 열고 닫는 루틴

문 열기 (startup):
  - 조명 켜기
  - 진열대 정리하기
  - 영수증 프린터 준비
  → build_bm25() = "검색 목록 준비하기"

yield = 가게 영업 중 (요청 처리)

문 닫기 (shutdown):
  - 조명 끄기
  - 재고 정리
  → (현재 특별한 정리 없음)
```

**왜 요청할 때마다 build_bm25()를 하지 않고 startup에서 할까?**

```
요청마다 build_bm25():
  고객 1 질문 → BM25 빌드(3초) → 답변
  고객 2 질문 → BM25 빌드(3초) → 답변  ← 매번 3초 낭비!

startup에서 한 번만:
  앱 시작 시 BM25 빌드(3초) ← 한 번만
  고객 1 질문 → 즉시 답변
  고객 2 질문 → 즉시 답변
```

---

### 핵심 개념 2: CORS (Cross-Origin Resource Sharing)

**비유: 아파트 방문자 출입 시스템**

```
아파트(백엔드, localhost:8000)에 방문하려면
등록된 방문자(프론트엔드)만 입장 가능

CORS 설정 없음:
  브라우저: "localhost:3000에서 localhost:8000로 요청 차단!"
  에러: "Access-Control-Allow-Origin 헤더 없음"

CORS 설정 있음:
  allow_origins=["http://localhost:3000"]
  브라우저: "등록된 방문자네요, 통과!"
```

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js 로컬 개발 서버
        "https://*.vercel.app",   # Vercel 배포 프론트엔드
    ],
    allow_credentials=True,  # 쿠키/인증 정보 포함 요청 허용
    allow_methods=["*"],     # GET, POST, PUT, DELETE 등 모두 허용
    allow_headers=["*"],     # Content-Type, Authorization 등 모두 허용
)
```

---

### 핵심 개념 3: 라우터 등록

```python
app.include_router(upload_router)  # POST /upload, GET /documents
app.include_router(chat_router)    # POST /chat
```

**비유: 회사 전화 교환원**

```
전화 교환원(main.py)이 전화를 받아서 담당 부서로 연결

"/upload" → 업로드 담당 부서(upload.py)로 연결
"/chat"   → 채팅 담당 부서(chat.py)로 연결
"/docs"   → FastAPI가 자동으로 Swagger 문서 제공
```

Phase 5에서 approve_router도 추가됩니다:

```python
app.include_router(approve_router)  # GET /pending, POST /approve
```

---

### 학습 질문

- lifespan에서 build_bm25()가 실패하면 앱이 어떻게 될까?
- allow_origins=["*"]로 설정하면 어떤 보안 문제가 생길까?
- include_router를 안 하면 어떤 엔드포인트가 없어질까?

---

## 전체 흐름 실습 (15분)

서버를 실행하고 curl로 직접 테스트하세요.

```bash
# 1. 서버 실행
cd backend
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 2. 테스트용 정책 파일 생성
cat > /tmp/test_policy.txt << 'EOF'
환불 정책
1. 환불 신청 기간: 구매일로부터 30일 이내
2. 환불 신청 방법: 고객센터(1234-5678) 또는 홈페이지 마이페이지
3. 환불 불가 상품: 개봉된 소프트웨어, 사용 흔적 있는 제품
4. 처리 기간: 신청 후 영업일 기준 3~5일
EOF

# 3. 문서 업로드
curl -X POST http://localhost:8000/upload \
  -F "file=@/tmp/test_policy.txt"
# 응답: {"success": true, "data": {"filename": "test_policy.txt", "chunks": 1}}

# 4. 업로드된 문서 목록 확인
curl http://localhost:8000/documents

# 5. 문서에 있는 내용 질문
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "환불은 어떻게 신청해요?", "thread_id": "test-1"}'
# 응답: {"success": true, "data": {"response": "환불은 30일 이내에..."}}

# 6. 문서에 없는 내용 질문 (Agent가 모른다고 해야 함)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "주식 투자 방법 알려줘", "thread_id": "test-2"}'
# 응답: "관련 정보를 문서에서 찾을 수 없습니다"

# 7. Swagger UI로 테스트 (브라우저에서 직접 API 호출 가능)
# http://localhost:8000/docs 접속
```

---

## Phase 2 핵심 구조 요약

```
POST /chat {"message": "환불은?"}
     ↓
main.py → chat_router로 연결
     ↓
chat.py → ChatRequest 파싱 → Agent 호출
     ↓
agent.py → ReAct 시작
  [Reasoning] "문서를 검색해야겠다"
     ↓
tools.py → search_documents("환불") 실행
     ↓
  EnsembleRetriever
    ├─ BM25Retriever   (키워드 40%)  "환불" 단어 포함 문서
    └─ VectorRetriever (의미  60%)   "환불" 관련 의미 문서
    ↓
  RRF로 합산 → 상위 5개 청크 반환
     ↓
agent.py → [Reasoning] 검색 결과로 답변 생성
     ↓
chat.py → {"success": true, "data": {"response": "환불은 30일..."}}
```

---

## 검증 체크리스트

### tools.py

- @tool 데코레이터가 하는 일 이해
- docstring이 왜 중요한지 이해
- BM25와 Vector의 각각 장단점 이해
- build_bm25()가 언제, 왜 호출되는지 이해
- global 키워드의 역할 이해
- weights=[0.4, 0.6]의 의미 이해

### agent.py

- ReAct 패턴 (Reasoning → Acting → Reasoning) 이해
- temperature=0의 의미 이해
- Agent의 파라미터 역할 이해 (model, tools, system_prompt)
- System Prompt가 없으면 어떤 문제가 생기는지 이해

### chat.py

- Pydantic BaseModel의 자동 검증 이해
- await(비동기)가 왜 필요한지 이해
- result["messages"] 구조 이해 (질문 → Tool 호출 → Tool 결과 → 답변)
- thread_id가 Phase 3에서 어떻게 활용될지 예상

### main.py

- lifespan에서 startup/shutdown의 역할 이해
- startup에서 BM25를 미리 빌드하는 이유 이해
- CORS가 없으면 어떤 에러가 생기는지 이해
- include_router가 하는 일 이해

---

## 다음 단계

Phase 2를 완료했으면:

- **Phase 3**: Memory (Short-term + Long-term)
  - Short-term: 같은 thread_id로 대화하면 이전 내용 기억
  예) "아까 말한 주문번호로 환불해줘" → Agent가 기억
  - Long-term: "한국어로만 답변해줘" 저장 후 → 다음 대화에서도 자동 반영

