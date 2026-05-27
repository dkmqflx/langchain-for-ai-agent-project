"""
RAG 파이프라인 Step 3: 임베딩 (Embedding)

목적:
  - 텍스트를 고정 길이의 숫자 벡터(1536차원)로 변환
  - 의미가 유사한 텍스트는 벡터도 유사하게 만들기
  - 캐싱으로 반복 임베딩 비용 절감

임베딩이란:
  "환불 신청하고 싶어요"  → [0.23, -0.41, 0.87, ...]  (1536개 숫자)
  "반품 요청합니다"        → [0.21, -0.39, 0.85, ...]  (비슷한 숫자! 의미 유사)
  "날씨가 맑다"           → [-0.91, 0.12, -0.34, ...]  (다른 숫자)

OpenAIEmbeddings (text-embedding-3-small):
  - 모델: OpenAI의 최신 임베딩 모델
  - 입력: 문자열
  - 출력: 1536차원 벡터
  - 비용: $0.02/1M 토큰 (매우 저렴)
  - 성능: 의미 검색에 최적화

CacheBackedEmbeddings (캐싱):
  - 같은 텍스트를 여러 번 임베딩할 때 API 호출 피함
  - InMemoryByteStore에 벡터 저장 (메모리, 빠름)

비용 비교:
  캐시 없음: "정책" 100번 × $0.02 = $2
  캐시 있음: "정책" 1번 × $0.02 = $0.02 (100배 절감!)

주의사항:
  - InMemoryByteStore는 메모리에만 저장 (프로세스 종료 시 손실)
  - 영구 캐시는 Phase 7에서 Redis로 구현
  - namespace="text-embedding-3-small": 모델별 캐시 분리
"""

from langchain_classic.embeddings.cache import CacheBackedEmbeddings
from langchain_core.stores import InMemoryByteStore
from langchain_openai import OpenAIEmbeddings

# [1] 기본 임베딩 모델 설정
# OpenAI의 text-embedding-3-small: 빠르고 정확하며 저렴
_underlying = OpenAIEmbeddings(model="text-embedding-3-small")

# [2] 캐시 저장소: InMemoryByteStore
# 임베딩 결과를 메모리에 저장해서 같은 텍스트는 API 호출 안 함
_store = InMemoryByteStore()

# [3] CacheBackedEmbeddings: 캐시 기능이 있는 임베딩 래퍼
cached_embedder = CacheBackedEmbeddings.from_bytes_store(
    _underlying,  # 실제 임베딩을 하는 모델
    _store,       # 결과를 저장할 캐시
    namespace=_underlying.model,  # 모델별로 캐시 분리 (나중에 여러 모델 사용 시 유용)
)


def get_cached_embedder() -> CacheBackedEmbeddings:
    """
    캐싱 기능이 있는 임베더 반환.

    이 함수는 모듈 레벨 싱글톤 패턴을 사용합니다.
    매 호출마다 새로운 인스턴스를 생성하지 않고,
    같은 _underlying과 _store를 공유합니다.

    이렇게 하면:
      1. 캐시가 초기화되지 않음
      2. 메모리 효율적

    Returns:
        CacheBackedEmbeddings: 캐싱 기능이 있는 임베더

    Usage:
        >>> embedder = get_cached_embedder()
        >>> vec1 = embedder.embed_query("환불")  # API 호출 ($비용)
        >>> vec2 = embedder.embed_query("환불")  # 캐시 사용 (무료)
    """
    return cached_embedder
