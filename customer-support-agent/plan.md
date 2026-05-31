# B2B SaaS Customer Support Agent - Implementation Plan

## Context

README.md에 정의된 7단계 구현 계획을 기반으로, 빈 프로젝트(README.md + .env만 존재)에서 풀스택 AI 고객 지원 에이전트를 구축한다. RAG, Agentic RAG, Guardrail, Memory, Human-in-the-loop을 모두 결합한 프로덕션 수준의 시스템이 최종 목표.

---

## Phase 1: RAG Pipeline (3일)

**목표**: 문서 업로드 → 청킹 → 임베딩 → pgvector 저장/검색 기반 구축

### RAG란?

AI에게 "우리 회사 환불 정책이 뭐야?"라고 물으면, 기본 GPT는 학습 데이터에 없는 회사 문서를 모릅니다. RAG(Retrieval-Augmented Generation)는 이 문제를 해결합니다.

```
[기존 GPT]  질문 → GPT → "모르겠습니다" (회사 문서가 없으니까)

[RAG]       질문 → ① 문서에서 관련 내용 검색
                 → ② 검색 결과를 GPT에게 전달
                 → ③ GPT가 문서를 참고해서 정확한 답변 생성
```

**도서관 사서 비유**: RAG는 사서가 책장에서 관련 책을 찾아 독자에게 건네주는 것처럼, AI가 답변하기 전에 먼저 문서에서 관련 내용을 찾아서 참고하게 하는 기술.

### 전체 흐름

```
관리자가 PDF 업로드
     ↓
1. loader.py     → PDF를 텍스트로 읽기
     ↓
2. splitter.py   → 텍스트를 500자 단위로 자르기 (청킹)
     ↓
3. embedder.py   → 각 청크를 숫자 벡터로 변환 (임베딩)
     ↓
4. vectorstore.py → PostgreSQL(pgvector)에 저장
     ↓
5. upload.py     → 위 1~4를 묶어서 API로 노출
```

### 생성할 파일

| 파일 | 역할 |
|------|------|
| `backend/requirements.txt` | 전체 의존성 정의 |
| `backend/rag/__init__.py` | 패키지 초기화 |
| `backend/rag/loader.py` | PDF/TXT 문서 로딩 |
| `backend/rag/splitter.py` | RecursiveCharacterTextSplitter (chunk_size=500, overlap=50) |
| `backend/rag/embedder.py` | OpenAIEmbeddings + CacheBackedEmbeddings |
| `backend/rag/vectorstore.py` | pgvector 저장/조회 (langchain_postgres.PGVector) |
| `backend/api/__init__.py` | 패키지 초기화 |
| `backend/api/upload.py` | POST /upload, GET /documents 엔드포인트 |

### 파일별 구현 포인트

#### loader.py — PDF를 텍스트로 읽기

PDF는 텍스트 파일이 아니라 좌표 기반의 복잡한 포맷이기 때문에 전용 라이브러리가 필요합니다.

| 라이브러리 | 강점 | 약점 |
|-----------|------|------|
| `pdfplumber` | 표·레이아웃 파악 정확 | 스캔 PDF(이미지) 불가 |
| `PyMuPDF` | 빠르고 스캔 PDF도 처리 | 표 파악이 약함 |

전략: **pdfplumber 먼저 시도, 실패하면 PyMuPDF로 폴백**.

메타데이터를 함께 저장하는 이유 — 나중에 출처 명시 가능:
```python
# 텍스트만 저장하면
"환불은 30일 이내 가능합니다."

# 메타데이터 포함 시
{
    "content": "환불은 30일 이내 가능합니다.",
    "metadata": {
        "source": "refund_policy.pdf",   # 출처 파일명
        "page": 3,                        # 페이지 번호
        "uploaded_at": "2026-05-27"       # 업로드 시각
    }
}
# → AI가 "환불 정책.pdf 3페이지에 따르면..." 식으로 출처 명시 가능
```

#### splitter.py — 텍스트를 500자 단위로 자르기

PDF 전체를 GPT에 넣으면 토큰 비용 폭증 + 관련 없는 내용으로 답변 품질 저하. 관련 페이지만 골라 읽는 것처럼, 청크 단위로 잘라서 검색 정확도를 높입니다.

```python
RecursiveCharacterTextSplitter(
    chunk_size=500,      # 한 청크 최대 글자 수
    chunk_overlap=50,    # 앞 청크와 겹치는 글자 수 (문맥 보존)
    separators=["\n\n", "\n", ". ", " ", ""]  # 자를 위치 우선순위
)
```

`chunk_overlap=50`이 필요한 이유: 문장이 청크 경계에서 잘리면 의미가 손실됩니다. 50자를 앞 청크와 겹치게 해서 경계 부분의 맥락을 보존합니다.

`separators` 작동 방식: "단락 → 줄바꿈 → 문장 끝 → 단어" 순으로 자연스러운 위치를 탐색. 단어 중간을 자르는 일이 없습니다.

#### embedder.py — 텍스트를 숫자 벡터로 변환

컴퓨터는 "환불"과 "반품"이 비슷한 의미인지 모릅니다. 임베딩은 텍스트를 **의미를 담은 숫자 배열**로 변환해서, 의미가 비슷한 문장끼리 숫자도 비슷하게 만듭니다.

```
"환불 신청하고 싶어요" → [0.23, -0.41, 0.87, ...]  (1536개 숫자)
"반품 요청합니다"     → [0.21, -0.39, 0.85, ...]  (비슷한 숫자!)
"날씨가 맑다"        → [-0.91, 0.12, -0.34, ...]  (전혀 다른 숫자)
```

`CacheBackedEmbeddings`가 필요한 이유: 임베딩 API는 호출할 때마다 비용이 발생합니다. 같은 텍스트를 다시 임베딩할 필요가 없으므로 캐시로 재사용합니다.

```python
# 캐시 없을 때
"환불 정책" → API 호출 → 비용 발생
"환불 정책" → API 호출 → 비용 발생 (중복 낭비!)

# CacheBackedEmbeddings 사용 시
"환불 정책" → API 호출 → 캐시 저장
"환불 정책" → 캐시에서 반환 → 비용 0
```

#### vectorstore.py — PostgreSQL에 벡터로 저장

pgvector는 PostgreSQL에 벡터 검색 기능을 추가하는 extension입니다. SQL 쿼리처럼 "가장 가까운 벡터 찾기"가 가능합니다.

왜 ChromaDB 같은 전용 벡터 DB 대신 PostgreSQL을 쓰는가:
```
[전용 벡터 DB 방식]    고객 정보: PostgreSQL / 벡터 데이터: ChromaDB → 시스템 2개 관리
[pgvector 방식]       고객 정보 + 대화 이력 + 벡터 데이터 → PostgreSQL 하나로 통합
```

커넥션 문자열 주의사항 (`langchain_postgres`는 psycopg3 드라이버 필수):
```python
# 틀린 방식 (psycopg2)
"postgresql://user:pass@localhost/db"

# 올바른 방식 (psycopg3)
"postgresql+psycopg://user:pass@localhost/db"
#              ^^^^^^^^ 이 부분이 핵심 — 빠뜨리면 연결 오류
```

```python
vectorstore = PGVector(
    embeddings=get_cached_embedder(),
    collection_name="documents",
    connection=DATABASE_URL,
    use_jsonb=True,   # 메타데이터 필터링을 위해 필수
)
```

PGVector가 자동 생성하는 테이블:
```sql
langchain_pg_collection  -- 컬렉션 메타데이터 (이름: "documents")
langchain_pg_embedding   -- 실제 청크 + 벡터
  - id:          UUID
  - embedding:   vector(1536)   -- 숫자 배열
  - document:    text           -- 원본 텍스트
  - cmetadata:   jsonb          -- source, page 등 메타데이터
```

#### upload.py — API로 전체 파이프라인 노출

1~4 단계를 하나의 HTTP 엔드포인트로 묶습니다:

```
POST /upload (PDF 파일)
  ① FastAPI UploadFile 수신
  ② 임시 파일로 저장 (/tmp/xxx.pdf)
  ③ loader.py  → 텍스트 추출
  ④ splitter.py → 청킹
  ⑤ embedder.py → 벡터 변환
  ⑥ vectorstore.py → pgvector 저장
응답: {"status": "success", "filename": "manual.pdf", "chunks": 47}
```

### 주요 의존성 패키지

```
fastapi, uvicorn, python-dotenv, python-multipart
langchain, langchain-openai, langchain-community, langchain-postgres, langgraph
pdfplumber, pymupdf, rank-bm25
psycopg[binary], sqlalchemy
sse-starlette, langsmith
```

### 전체 데이터 흐름 요약

```
[문서 인덱싱]
관리자 PDF 업로드
  → loader   : PDF → 텍스트 + 메타데이터
  → splitter : 텍스트 → 500자 청크들
  → embedder : 청크 → 숫자 벡터 (+ 캐시)
  → pgvector : 벡터 + 텍스트 + 메타데이터 저장

[고객 질문 시 — Phase 2에서 연결]
"환불 어떻게 해요?" → 임베딩 → [0.21, -0.38, ...]
  → pgvector cosine similarity 검색 → 유사 청크 TOP 5 반환
  → GPT가 해당 청크를 참고해서 답변 생성
```

### 검증 체크리스트

```sql
-- 1. pgvector 설치 확인
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. PDF 업로드 후 청크 수 확인
SELECT COUNT(*) FROM langchain_pg_embedding;

-- 3. 텍스트가 제대로 잘렸는지 확인
SELECT document FROM langchain_pg_embedding LIMIT 3;

-- 4. 메타데이터 포함 여부 확인
SELECT cmetadata FROM langchain_pg_embedding LIMIT 3;
```

---

## Phase 2: Basic Agent + RAG Tool + Hybrid Search (3일)

**목표**: 에이전트가 질문을 받으면 문서에서 검색(Hybrid Search)해 답변

### 생성할 파일

| 파일 | 역할 |
|------|------|
| `backend/agent/__init__.py` | 패키지 초기화 |
| `backend/agent/tools.py` | `search_documents` Tool (Hybrid Search) |
| `backend/agent/agent.py` | `create_agent` 설정 |
| `backend/api/chat.py` | POST /chat 엔드포인트 |
| `backend/main.py` | FastAPI 진입점 + CORS + 라우터 등록 |

### 핵심 구현 포인트

**Hybrid Search (tools.py)**: `EnsembleRetriever` 사용 (내부적으로 RRF 알고리즘 적용)

```python
from langchain.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever

bm25_retriever = BM25Retriever.from_documents(all_docs, k=5)
vector_retriever = vectorstore.as_retriever(search_type="mmr", search_kwargs={"k": 5})
ensemble_retriever = EnsembleRetriever(
    retrievers=[bm25_retriever, vector_retriever],
    weights=[0.4, 0.6],
)
```

**BM25 인덱스 관리**: 앱 시작 시 pgvector에서 전체 청크 로드 → BM25Retriever 생성. 새 문서 업로드 시 eager rebuild.

**agent.py**: `langchain.agents.create_agent` + `ChatOpenAI(model="gpt-4o", temperature=0, streaming=True)`. 이 단계에서는 checkpointer/store 없이 기본 구성.

**main.py**: FastAPI + CORS 미들웨어 (localhost:3000 + Vercel 허용) + 라우터 include.

### 검증
- 문서 업로드 후 "환불 정책이 어떻게 돼요?" 질문 → 문서 기반 답변 확인
- 문서에 없는 내용 질문 → "관련 정보를 찾을 수 없습니다" 확인

---

## Phase 3: Short-term + Long-term Memory (2일)

**목표**: 대화 맥락 유지(Short-term) + 고객 선호도 기억(Long-term)

### 생성/수정할 파일

| 파일 | 변경 |
|------|------|
| `backend/agent/context.py` | **생성** - Context dataclass (user_id, user_tier) |
| `backend/agent/tools.py` | **수정** - `save_user_preference`, `get_user_preference` 추가 |
| `backend/agent/agent.py` | **수정** - InMemorySaver(checkpointer) + InMemoryStore(store) 추가 |
| `backend/agent/middleware.py` | **생성** - `InjectMemoryMiddleware` (Long-term memory → system prompt 주입) |
| `backend/routers/chat.py` | **수정** - config에 user_id 전달 |

### 핵심 구현 포인트

**Memory 싱글톤**: `checkpointer`와 `store`는 반드시 모듈 레벨 싱글톤으로 생성. 요청마다 새로 만들면 상태가 유실됨.

```python
checkpointer = InMemorySaver()   # thread_id 기반 대화 이력
store = InMemoryStore()           # user_id 기반 장기 기억
```

**Memory Tools**: `ToolRuntime[AgentContext]`를 통해 store와 context에 접근. 네임스페이스 `("user_preferences", user_id)`.

**InjectMemoryMiddleware**: `create_agent`의 `middleware=[]`에 등록하는 `AgentMiddleware` 서브클래스. `before_model` 훅에서 장기 메모리를 system prompt에 동적 주입.

### 검증
- 같은 thread_id로 대화 → 이전 맥락 기억 확인 (Short-term)
- "한국어로 답변해줘" 저장 후 새 thread_id → 선호도 반영 확인 (Long-term)

---

## Phase 4: PII + Guardrail Middleware (2일)

**목표**: 안전하고 신뢰할 수 있는 에이전트 구축

### 수정할 파일

| 파일 | 변경 |
|------|------|
| `backend/agent/agent.py` | **수정** - `PIIMiddleware` + `InjectMemoryMiddleware` 추가 |
| `backend/agent/middleware.py` | **수정** - `InjectMemoryMiddleware` 클래스 추가, `is_blocked_input`, `check_hallucination` 추가 |
| `backend/agent/tools.py` | **수정** - `InjectedStore+RunnableConfig` → `ToolRuntime[AgentContext]` |
| `backend/routers/chat.py` | **수정** - Before/After Guardrail 통합, `context=AgentContext(...)` 방식으로 변경 |

### 핵심 구현 포인트

**create_agent 구성**:
- `middleware=[]` 파라미터로 `PIIMiddleware`, `InjectMemoryMiddleware` 연결
- `context_schema=AgentContext` + `invoke(context=AgentContext(...))` 로 user_id 전달

**PII Masking (PIIMiddleware)**:
- `langchain.agents.middleware.PIIMiddleware` 공식 내장 미들웨어 사용
- 이메일: 커스텀 regex detector → `[REDACTED_EMAIL]`
- 카드번호: 커스텀 regex detector → `****-****-****-1234`
- `apply_to_input=True, apply_to_output=True`로 에이전트 내부에서 입출력 모두 처리

**Before Agent Guardrail**: `is_blocked_input()` — 키워드 기반 욕설 차단. 탐지 시 `agent.invoke()` 호출 없이 즉시 거절 반환.

**After Agent Guardrail**: `check_hallucination()` — GPT-4o-mini 감시자 모델로 할루시네이션 검증.
- `result["messages"]`에서 `ToolMessage(name="search_documents")` 수집
- 검색 컨텍스트 있을 때만 실행 (없으면 오탐 방지를 위해 생략)
- `"HALLUCINATION"` 판정 시 교정 메시지로 대체

**chat.py 파이프라인**: 욕설 체크 → 에이전트 실행(내부 PIIMiddleware 자동 실행) → 검색 컨텍스트 추출 → 할루시네이션 검증

### 검증
- 이메일/카드번호 포함 메시지 → 마스킹 확인
- 욕설 포함 메시지 → 차단 확인
- 문서에 없는 내용 질문 → 할루시네이션 교정 확인

---

## Phase 5: Human-in-the-loop (2일)

**목표**: 민감 작업(환불)은 관리자 승인 후 실행

### 생성/수정할 파일

| 파일 | 변경 |
|------|------|
| `backend/agent/tools.py` | **수정** - `process_refund` Tool 추가 (interrupt() 사용) |
| `backend/agent/agent.py` | **수정** - tools 리스트에 process_refund 추가 |
| `backend/routers/approve.py` | **생성** - GET /pending, POST /approve |
| `backend/routers/chat.py` | **수정** - GraphInterrupt 처리, pending_approval 상태 반환 |
| `backend/main.py` | **수정** - approve_router 등록 |

### 핵심 구현 포인트

**process_refund Tool**: LangGraph `interrupt()` 직접 사용. interrupt payload에 order_id, amount, reason 포함. 승인 시 `Command(resume=...)` 로 재개.

```python
@tool
def process_refund(order_id: str, amount: float, reason: str) -> str:
    approval = interrupt({"type": "refund_approval", "order_id": order_id, ...})
    if approval.get("decision") == "approve":
        return f"Refund processed for order {order_id}"
    else:
        return f"Refund rejected for order {order_id}"
```

**GraphInterrupt 처리 (chat.py)**: `ainvoke()` 후 state를 확인하여 interrupt 발생 여부 판단. interrupt 시 `pending_approvals` dict에 저장하고 `status: "pending_approval"` 반환.

**approve.py**: POST /approve에서 `Command(resume={"decision": ...})` 로 에이전트 재개.

### 검증
- "주문 ORD-123 환불 요청" → `pending_approval` 상태 확인
- GET /pending → 대기 목록에 표시 확인
- POST /approve → 에이전트 재개 후 처리 완료 확인

---

## Phase 6: Frontend + LangSmith (4일)

**목표**: 실제 사용 가능한 UI + 모니터링

### 생성할 파일

| 파일 | 역할 |
|------|------|
| `frontend/` | Next.js 15 프로젝트 초기화 (App Router + Tailwind) |
| `frontend/app/page.tsx` | 채팅 UI (SSE 스트리밍) |
| `frontend/app/admin/page.tsx` | 문서 업로드 관리자 화면 |
| `frontend/app/approve/page.tsx` | Human-in-the-loop 승인 화면 |
| `backend/api/chat.py` | **수정** - POST /chat/stream SSE 엔드포인트 추가 |

### 핵심 구현 포인트

**SSE Streaming (chat.py)**: `sse-starlette`의 `EventSourceResponse` + `agent.astream(stream_mode="messages")`.

**app.state로 Agent 관리 전환 (main.py + chat.py)**:
현재 모듈 레벨 싱글톤 방식(`get_agent()`)을 FastAPI 권장 방식인 `app.state`로 전환.
```python
# main.py lifespan에서 Agent 초기화
app.state.agent = create_agent(...)

# chat.py에서 Depends()로 주입
def get_agent(req: Request):
    return req.app.state.agent
```
이유: 테스트 시 Mock 교체 용이, FastAPI 의존성 주입 패턴 준수.

**Chat UI (page.tsx)**: `fetch()` → `ReadableStream` → SSE 파싱. "관리자 검토 중" 상태 표시. thread_id는 UUID로 생성.

**Admin UI (admin/page.tsx)**: Drag-and-drop 파일 업로드 + `FormData` → POST /upload. 업로드된 문서 목록 (GET /documents).

**Approve UI (approve/page.tsx)**: GET /pending 폴링(5초 간격). 승인/거절 버튼 → POST /approve.

**LangSmith**: 환경변수 설정만으로 자동 추적 활성화. 코드 변경 불필요.

### 검증
- 채팅 UI에서 스트리밍 응답 확인
- 문서 업로드 → 목록 표시 확인
- 환불 요청 → "관리자 검토 중" → 승인 화면에서 처리 → 채팅 업데이트 확인

---

## Phase 7: AWS Infrastructure (4일)

**목표**: EC2 + RDS 배포, CI/CD, 모니터링

### Day 1: VPC + Security Groups
- FastAPI SG: HTTP(80), HTTPS(443) 인바운드, SSH(22) 본인 IP만
- RDS SG: PostgreSQL(5432) FastAPI SG에서만 접근

### Day 2: RDS PostgreSQL + pgvector
- PostgreSQL 15+, t3.micro, DB명: customer_support_db
- `CREATE EXTENSION IF NOT EXISTS vector;`

### Day 3: EC2 + systemd
- Ubuntu 22.04, t3.micro, Elastic IP
- systemd 서비스 파일로 자동 실행

### Day 4: CI/CD + Vercel + CloudWatch
- `.github/workflows/deploy.yml`: main push → EC2 SSH 배포
- Vercel 프론트엔드 배포 (`NEXT_PUBLIC_API_URL` = EC2 Elastic IP)
- CloudWatch: CPU > 80% 알림

### 생성할 파일
- `.github/workflows/deploy.yml`
- `.gitignore` (반드시 `.env` 포함)

### 검증
- `curl http://<elastic-ip>/docs` → Swagger UI 확인
- Vercel → EC2 통신 확인
- GitHub Actions 자동 배포 확인

---

## 전체 파일 생성 순서

```
Phase 1: requirements.txt → rag/{__init__, loader, splitter, embedder, vectorstore}.py → api/{__init__, upload}.py
Phase 2: agent/{__init__, tools, agent}.py → api/chat.py → main.py
Phase 3: agent/context.py → tools.py 수정 → agent.py 수정 → agent/middleware.py → routers/chat.py 수정
Phase 4: agent/agent.py 수정(create_agent+PIIMiddleware) → middleware.py 수정(InjectMemoryMiddleware) → tools.py 수정(ToolRuntime) → routers/chat.py 수정
Phase 5: tools.py 수정 → agent.py 수정 → routers/approve.py → routers/chat.py 수정 → main.py 수정
Phase 6: frontend/ 초기화 → page.tsx, admin/page.tsx, approve/page.tsx → chat.py 수정
Phase 7: .gitignore → .github/workflows/deploy.yml → AWS 수동 설정
```

## Production 전환 시 고려사항

- `InMemorySaver` → `PostgresSaver` (langgraph-checkpoint-postgres)
- `InMemoryStore` → Redis 기반 Store
- `InMemoryByteStore` → Redis 기반 ByteStore
- 서버 재시작 시에도 대화 상태 및 메모리 유지
