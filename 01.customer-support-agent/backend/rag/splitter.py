"""
RAG 파이프라인 Step 2: 문서 분할 (Chunking)

목적:
  - 큰 문서를 작은 청크로 분할해서 검색 정확도와 토큰 비용 최적화
  - 청크 경계에서 맥락이 손실되지 않도록 overlap 설정

왜 청킹이 필요한가:
  1. 전체 문서를 GPT에 던지면 토큰 비용 ↑↑↑, 답변 품질 ↓↓↓
  2. 검색으로 찾은 관련 청크만 주면 비용 ✅, 품질 ✅

예시:
  - 100페이지 매뉴얼 → 청크 없이 GPT 호출: 엄청난 비용, 품질 낮음
  - 같은 매뉴얼 → 관련 5개 청크만 선택해서 GPT 호출: 저렴, 품질 높음

RecursiveCharacterTextSplitter 설정:
  chunk_size=500
    - 각 청크의 최대 글자 수
    - 너무 작으면 (100): 맥락 손실 많음
    - 너무 크면 (5000): 검색 정확도 떨어짐

  chunk_overlap=50
    - 이전 청크와 겹치는 글자 수
    - 문장이 청크 경계에서 잘려도 다음 청크에 일부가 포함되어 맥락 보존

  separators=["\n\n", "\n", ". ", " ", ""]
    - 어느 위치에서 자를지 우선순위
    - 단락 → 줄 → 문장 → 단어 → 문자 순서로 시도
    - 자연스러운 위치에서 분할 가능

청크 겹침의 중요성:
  청크1: "...이 환불은 30일 이내에..."  (500자)
  청크2: "...내에... (50자 겹침)...신청서 작성."  (500자)
         ↑ 50자 겹침으로 경계 부분의 문맥 보존
"""

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 모듈 레벨 싱글톤: RecursiveCharacterTextSplitter 인스턴스 생성
# (매 함수 호출마다 새로 생성하지 않음 - 효율성)
_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,  # 각 청크 최대 글자 수
    chunk_overlap=50,  # 이전 청크와 겹치는 글자 수 (맥락 보존)
    separators=[
        "\n\n",  # 단락 경계 (가장 자연스러움)
        "\n",    # 줄 바꿈
        ". ",    # 문장 끝
        " ",     # 단어 (마지막 수단)
        "",      # 문자 (사실 사용되지 않음)
    ],
)


def split_documents(documents: list[Document]) -> list[Document]:
    """
    Document 리스트를 청크 단위로 분할.

    각 Document의 page_content를 RecursiveCharacterTextSplitter로 분할하고,
    기존 metadata는 모두 유지됨.

    Args:
        documents: loader.py에서 반환한 Document 리스트

    Returns:
        청크로 분할된 Document 리스트
        예: 1개 입력 Document(1000자) → 3개 출력 Document(각 300~500자)

    Example:
        >>> docs = load_txt("policy.txt")  # 1개 Document, 500자
        >>> chunks = split_documents(docs)  # 1개 Document, 500자 미만 (나누지 않음)
        >>> print(len(chunks))
        1  # 500자는 chunk_size=500보다 작아서 분할 안 됨
    """
    return _splitter.split_documents(documents)
