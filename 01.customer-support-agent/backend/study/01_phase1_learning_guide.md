# Phase 1 학습 가이드 — RAG 파이프라인

이 가이드는 Phase 1의 5개 파일을 의존성 순서대로 학습할 수 있도록 구성되었습니다.

---

## 학습 흐름도

```
문서 입력 (PDF/TXT)
     ↓
[1] loader.py      → 텍스트 추출 + 메타데이터 추가
     ↓
[2] splitter.py    → 텍스트를 청크로 분할 (겹침 포함)
     ↓
[3] embedder.py    → 각 청크를 숫자 벡터로 변환 (캐시 활용)
     ↓
[4] vectorstore.py → pgvector에 저장 + 검색 기능 제공
     ↓
[5] upload.py      → HTTP API로 전체 파이프라인 노출
     ↓
검색 결과 반환
```

---

## Step 1: `loader.py` 읽기 (10분)

### 목표
문서를 Python이 다룰 수 있는 형태로 변환하는 방식 이해

### 핵심 개념

**Document 객체**: LangChain의 기본 단위
```python
Document(
    page_content="실제 텍스트",
    metadata={"source": "파일명", "page": 번호}
)
```

**로더 선택 전략**:
| 상황 | 선택 |
|------|------|
| 일반 PDF | pdfplumber (정확한 텍스트 추출) |
| 스캔된 PDF (실패) | PyMuPDF (폴백) |
| TXT 파일 | 직접 읽기 |

### 학습 질문
- [ ] PDF와 TXT를 다르게 처리하는 이유는?
- [ ] 메타데이터에 page, source를 포함하는 이유는?
- [ ] pdfplumber가 실패하면 PyMuPDF로 폴백하는 이유는?

### 코드 읽기 팁
`_load_with_pdfplumber()` → `_load_with_pymupdf()` 순서로 읽으면, 두 라이브러리의 차이가 명확합니다.

---

## Step 2: `splitter.py` 읽기 (5분)

### 목표
큰 문서를 작은 청크로 나누되, 맥락을 잃지 않는 방식 이해

### 핵심 개념

**왜 청킹이 필요한가**:
- 전체 문서 → GPT: 토큰 비용 ⬆️⬆️⬆️, 답변 품질 ⬇️⬇️⬇️
- 관련 청크만 → GPT: 토큰 비용 ✅, 답변 품질 ✅

**RecursiveCharacterTextSplitter 설정**:
```python
chunk_size=500      # 한 청크 최대 글자 수
chunk_overlap=50    # 앞 청크와 겹치는 부분 (맥락 보존)
separators=["\n\n", "\n", ". ", " ", ""]  # 자를 위치 우선순위
```

**Overlap의 중요성**:
```
[청크 1] "...환불 신청은 어떻게" (500자)
[청크 2] "...신청은 어떻게 하나요? (50자 겹침)..." (500자)
         ↑ 50자 겹침으로 문장이 끝나는 맥락을 보존
```

### 학습 질문
- [ ] chunk_size를 100으로 하면? 2000으로 하면?
- [ ] overlap이 0이면 뭐가 문제될까?
- [ ] separators 리스트가 왜 이 순서일까?

### 코드 읽기 팁
`split_documents()` 함수는 단 3줄이지만, 파라미터 조합이 얼마나 중요한지 이해하는 게 핵심입니다.

---

## Step 3: `embedder.py` 읽기 (5분)

### 목표
텍스트를 의미를 담은 숫자 벡터로 변환하고, 캐싱으로 비용을 줄이는 방식 이해

### 핵심 개념

**Embedding (임베딩)**:
텍스트를 고정 길이의 숫자 배열로 변환하여, 의미가 유사한 문장끼리 숫자도 비슷하게 만드는 것

```
"환불 신청하고 싶어요"  → [0.23, -0.41, 0.87, ...]  (1536개 숫자)
"반품 요청합니다"        → [0.21, -0.39, 0.85, ...]  (비슷한 숫자!)
"날씨가 맑다"           → [-0.91, 0.12, -0.34, ...]  (전혀 다른 숫자)
```

**CacheBackedEmbeddings (임베딩 캐시)**:
```
요청 1: "환불 정책" → API 호출 → 벡터 계산 → $0.02 비용 + 캐시 저장
요청 2: "환불 정책" → 캐시 확인 → 즉시 반환 → $0.00 비용
```

**InMemoryByteStore**:
임베딩 결과를 메모리에 저장. 프로세스가 재시작되면 초기화됩니다.

### 비용 비교
```
캐시 없음: 100개 청크, 10회 임베딩 = 1000번 API 호출
캐시 있음: 100개 청크, 10회 임베딩 = 100번 API 호출 (10배 절감!)
```

### 학습 질문
- [ ] Embedding API가 안 되면 어떻게 될까?
- [ ] 캐시가 메모리에만 있으면 단점이 뭘까?
- [ ] 1536개 숫자가 맞나? OpenAI 모델마다 다를까?

### 코드 읽기 팁
모듈 레벨 싱글톤 패턴을 사용합니다 (`cached_embedder = ...`). Phase 3에서 중요한 개념입니다.

---

## Step 4: `vectorstore.py` 읽기 (10분)

### 목표
벡터를 데이터베이스에 저장하고, 의미 검색(semantic search)으로 결과를 가져오는 방식 이해

### 핵심 개념

**pgvector (PostgreSQL 벡터 확장)**:
PostgreSQL에 벡터 검색 기능을 추가합니다.
```sql
-- pgvector 덕분에 가능한 SQL
SELECT document FROM langchain_pg_embedding
WHERE embedding <-> query_vector < 0.5  -- cosine similarity 검색
ORDER BY embedding <-> query_vector
LIMIT 5;
```

**PGVector 설정**:
```python
vectorstore = PGVector(
    embeddings=get_cached_embedder(),      # 임베딩 함수
    collection_name="documents",           # 테이블 접두사
    connection=DATABASE_URL,               # DB 연결
    use_jsonb=True,                        # 메타데이터 필터링 가능
)
```

**중요: 커넥션 문자열 형식**
```python
# 🔴 틀림 (psycopg2)
DATABASE_URL = "postgresql://user:pass@host/db"

# ✅ 맞음 (psycopg3 - langchain_postgres 필수)
DATABASE_URL = "postgresql+psycopg://user:pass@host/db"
```

**검색 방식**:
```python
# MMR (Maximal Marginal Relevance) - 다양성 보장
retriever = vectorstore.as_retriever(
    search_type="mmr",
    search_kwargs={"k": 5}  # 상위 5개
)
```

### 자동 생성 테이블 구조
```sql
langchain_pg_collection        -- 컬렉션 메타데이터
  - id
  - name ("documents")

langchain_pg_embedding         -- 실제 벡터 + 텍스트
  - id
  - embedding: vector(1536)    -- 벡터 (cosine distance로 검색)
  - document: text             -- 원본 텍스트
  - cmetadata: jsonb           -- source, page 등 메타데이터
```

### 왜 ChromaDB 대신 pgvector?
```
ChromaDB (별도 시스템)          pgvector (PostgreSQL 통합)
고객 정보: PostgreSQL          전부: PostgreSQL
대화 이력: PostgreSQL
벡터: ChromaDB
↓ 시스템 2개 관리 필요          ↓ 시스템 1개, SQL JOIN 가능
```

### 학습 질문
- [ ] MMR vs similarity 검색의 차이?
- [ ] search_kwargs={"k": 5}를 10으로 하면?
- [ ] use_jsonb=True를 False로 하면?

### 코드 읽기 팁
`_get_connection_string()` 함수가 하는 일을 이해하면, "왜 psycopg3 드라이버를 명시해야 하나"가 명확해집니다.

---

## Step 5: `upload.py` 읽기 (5분)

### 목표
1~4 단계를 HTTP API로 묶어, 클라이언트가 쉽게 문서를 업로드할 수 있도록 하는 방식 이해

### 핵심 개념

**FastAPI APIRouter**:
```python
router = APIRouter()  # 라우터 생성

@router.post("/upload")  # POST /upload 엔드포인트
async def upload_document(file: UploadFile):
    # 1. 파일 수신
    # 2. 임시 저장
    # 3. RAG 파이프라인 (load → split → embed → store)
    # 4. 응답 반환
```

**파일 처리 흐름**:
```
브라우저에서 파일 선택
  ↓
POST /upload (multipart/form-data)
  ↓
FastAPI가 UploadFile로 파싱
  ↓
내용을 임시 파일(/tmp/xxx.pdf)로 저장
  ↓
loader.py 실행
  ↓
성공 시 DB 저장 → 응답 반환
실패 시 HTTP 500 에러
  ↓
파일 정리 (finally 블록)
```

**GET /documents 엔드포인트**:
```python
# 업로드된 모든 고유 파일명 반환 (source 기준)
results = vectorstore.similarity_search("", k=1000)
sources = {doc.metadata["source"]: ... for doc in results}
```

### 에러 처리
```python
if ext not in ALLOWED_EXTENSIONS:
    raise HTTPException(400, "지원하지 않는 파일")

try:
    # RAG 파이프라인
except Exception as e:
    raise HTTPException(500, str(e))
finally:
    os.unlink(tmp_path)  # 파일 정리
```

### 학습 질문
- [ ] 왜 파일을 메모리에 올리지 않고 임시 파일로 저장할까?
- [ ] 대용량 파일(1GB)을 올리면?
- [ ] GET /documents가 similarity_search를 쓰는 이유?

### 코드 읽기 팁
임시 파일 처리와 에러 핸들링 패턴을 배우면, Phase 2의 chat.py도 같은 구조를 따릅니다.

---

## 전체 흐름 실습 (20분)

이 코드를 한 줄씩 실행하며 각 단계의 결과를 관찰하세요:

```bash
cd backend
uv run python << 'EOF'
import os, sys
sys.path.insert(0, '.')

# 환경 변수 설정
os.environ['OPENAI_API_KEY'] = open('../.env').read().split('OPENAI_API_KEY=')[1].split()[0]
os.environ['DATABASE_URL'] = 'postgresql+psycopg://postgres:postgres@localhost:5433/customer_support_db'

print("=" * 60)
print("Phase 1 전체 파이프라인 실습")
print("=" * 60)

# [Step 1] 로드
print("\n[Step 1] loader.py 실행")
from rag.loader import load_txt
docs = load_txt('/tmp/test_rag_pipeline.txt')
print(f"  ✅ {len(docs)}개 Document 로드")
print(f"     - 텍스트 길이: {len(docs[0].page_content)}자")
print(f"     - 메타데이터: {docs[0].metadata}")

# [Step 2] 분할
print("\n[Step 2] splitter.py 실행")
from rag.splitter import split_documents
chunks = split_documents(docs)
print(f"  ✅ {len(chunks)}개 청크 생성")
for i, chunk in enumerate(chunks):
    print(f"     - 청크 {i+1}: {len(chunk.page_content)}자")

# [Step 3] 임베딩
print("\n[Step 3] embedder.py 실행")
from rag.embedder import get_cached_embedder
embedder = get_cached_embedder()
print(f"  ✅ 임베디 함수 준비 완료")
print(f"     - 모델: text-embedding-3-small")
print(f"     - 출력 차원: 1536")

# [Step 4] 벡터스토어 저장
print("\n[Step 4] vectorstore.py 실행")
from rag.vectorstore import add_documents, get_retriever
ids = add_documents(chunks)
print(f"  ✅ {len(ids)}개 청크를 pgvector에 저장")

# [Step 5] 검색
print("\n[Step 5] retriever 검색")
retriever = get_retriever(search_type="mmr", k=3)
results = retriever.invoke("환불은 어떻게?")
print(f"  ✅ {len(results)}개 결과 검색")
for i, result in enumerate(results, 1):
    print(f"\n  [{i}] 관련도: {result.metadata.get('source', 'N/A')}")
    print(f"      {result.page_content[:60]}...")

print("\n" + "=" * 60)
print("전체 파이프라인 완료!")
print("=" * 60)
EOF
```

---

## 검증 체크리스트

각 파일을 읽은 후 다음을 확인하세요:

### loader.py
- [ ] pdfplumber와 PyMuPDF의 차이 이해
- [ ] Document 객체의 page_content와 metadata 구분
- [ ] 메타데이터가 나중에 왜 중요한지 이해

### splitter.py
- [ ] chunk_size와 chunk_overlap의 의미 이해
- [ ] separators 리스트가 왜 이 순서인지 이해
- [ ] 청킹이 왜 필요한지 설명 가능

### embedder.py
- [ ] Embedding과 일반 텍스트의 차이 이해
- [ ] CacheBackedEmbeddings의 캐싱 메커니즘 이해
- [ ] 캐시 없을 때 비용 계산 가능

### vectorstore.py
- [ ] pgvector가 뭐 하는지 이해
- [ ] postgresql+psycopg:// 형식이 왜 필요한지 이해
- [ ] MMR 검색의 장점 이해

### upload.py
- [ ] FastAPI의 APIRouter 개념 이해
- [ ] 파일 업로드 흐름 이해
- [ ] 에러 핸들링과 정리 코드의 중요성 이해

---

## 다음 단계

Phase 1을 완료했으면:
- **Phase 2**: Agent + RAG Tool + Hybrid Search (BM25 + Vector)
- **Phase 3**: Memory (Short-term + Long-term)

Phase 1 개념이 이해되면 Phase 2는 훨씬 수월합니다!
