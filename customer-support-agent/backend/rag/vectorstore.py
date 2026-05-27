"""
RAG 파이프라인 Step 4: 벡터스토어 (Vector Store)

목적:
  - 임베딩된 벡터를 PostgreSQL의 pgvector 확장으로 저장
  - "가장 유사한" 벡터를 검색하는 semantic search 구현

pgvector란:
  - PostgreSQL의 벡터 검색 확장
  - SQL: SELECT * WHERE embedding <-> query_vector < 0.5
  - 코사인 유사도(cosine similarity)로 거리 계산

왜 pgvector인가:
  ChromaDB (전용 벡터 DB)     pgvector (PostgreSQL 통합)
  고객 정보: PostgreSQL       전부: PostgreSQL
  대화 이력: PostgreSQL        하나로 관리 ✅
  벡터: ChromaDB              SQL JOIN 가능 ✅
  → 시스템 2개 관리 ✗         → ACID 트랜잭션 ✅

PGVector 자동 생성 테이블:
  langchain_pg_collection
    id, name (e.g., "documents")

  langchain_pg_embedding
    id (UUID)
    embedding (vector, 1536차원)
    document (TEXT, 원본 청크)
    cmetadata (JSONB, {"source": "...", "page": 1, ...})

중요: 커넥션 문자열
  🔴 틀림: postgresql://user:pass@host/db (psycopg2)
  ✅ 맞음: postgresql+psycopg://user:pass@host/db (psycopg3)

검색 방식:
  similarity: 가장 유사한 벡터 k개 반환 (단순)
  mmr: Maximal Marginal Relevance - 유사도 + 다양성 고려
    예) "환불"을 검색하면:
      - 유사도 높은 결과들만? (너무 중복)
      - mmr: 유사도 높으면서도 서로 다른 결과 5개 선택
"""

import os

from langchain_core.documents import Document
from langchain_postgres import PGVector

from rag.embedder import get_cached_embedder

# .env 파일에서 DATABASE_URL 읽기
# 형식: postgresql://postgres:postgres@localhost:5433/customer_support_db
DATABASE_URL = os.getenv("DATABASE_URL", "")


def _get_connection_string() -> str:
    """
    DATABASE_URL을 psycopg3 드라이버 형식으로 변환.

    langchain_postgres는 psycopg3만 지원합니다.
    일반적인 postgresql:// 형식을 postgresql+psycopg://로 변환합니다.

    Args:
        DATABASE_URL: 환경변수에서 읽은 원본 URL

    Returns:
        psycopg3 드라이버 명시한 URL

    Example:
        입력:  postgresql://postgres:postgres@localhost:5433/db
        출력:  postgresql+psycopg://postgres:postgres@localhost:5433/db
    """
    url = DATABASE_URL
    if url.startswith("postgresql://"):
        # postgresql:// → postgresql+psycopg:// 변환
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


# [모듈 레벨 싱글톤] PGVector 인스턴스
# 이것을 통해 모든 벡터 저장/검색이 일어남
vectorstore = PGVector(
    embeddings=get_cached_embedder(),  # Step 3에서 준비한 임베더
    collection_name="documents",  # 컬렉션 이름 (테이블 접두사)
    connection=_get_connection_string(),  # PostgreSQL 연결 문자열
    use_jsonb=True,  # 메타데이터를 JSONB로 저장 (필터링 가능)
)


def add_documents(documents: list[Document]) -> list[str]:
    """
    Document 리스트를 pgvector에 저장.

    각 Document의 page_content를 임베딩한 후,
    벡터 + 텍스트 + 메타데이터를 PostgreSQL에 INSERT합니다.

    Args:
        documents: splitter.py에서 반환한 청크 Document 리스트

    Returns:
        저장된 벡터의 ID 리스트 (UUID)

    Example:
        >>> chunks = [Document(...), Document(...)]
        >>> ids = add_documents(chunks)
        >>> len(ids)
        2
        >>> print(ids[0])
        'f47ac10b-58cc-4372-a567-0e02b2c3d479'
    """
    return vectorstore.add_documents(documents)


def get_retriever(search_type: str = "mmr", k: int = 5):
    """
    검색 설정이 적용된 retriever를 반환.

    이것을 사용해서 쿼리와 유사한 청크를 검색합니다.

    Args:
        search_type: "similarity" 또는 "mmr"
          - "similarity": 단순 거리 기반 (빠름)
          - "mmr": 유사도 + 다양성 고려 (권장)

        k: 반환할 청크 개수 (기본값 5)

    Returns:
        BaseRetriever: .invoke(query) 메서드로 검색 가능

    Example:
        >>> retriever = get_retriever(search_type="mmr", k=5)
        >>> results = retriever.invoke("환불 신청은?")
        >>> len(results)
        5
        >>> results[0].page_content
        '환불 신청은 고객센터(1234-5678)로 연락하시거나...'
    """
    return vectorstore.as_retriever(
        search_type=search_type,
        search_kwargs={"k": k},
    )
