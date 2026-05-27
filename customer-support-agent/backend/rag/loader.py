"""
RAG 파이프라인 Step 1: 문서 로드 (Loader)

목적:
  - PDF, TXT 파일을 읽어 LangChain의 Document 객체로 변환
  - 각 Document에 메타데이터(출처, 페이지, 업로드 시각)를 포함

원리:
  1. PDF는 좌표 기반의 복잡한 포맷이므로 전용 라이브러리 필요
  2. pdfplumber: 표·레이아웃 추출에 강함, 스캔 PDF는 불가
  3. PyMuPDF: 빠르고 스캔 PDF도 지원, 표 추출이 약함
  4. 전략: pdfplumber 시도 → 실패 시 PyMuPDF 폴백

Document 객체 구조:
  Document(
      page_content="실제 텍스트",
      metadata={
          "source": "파일명",
          "page": 페이지번호,
          "uploaded_at": "ISO 8601 형식 타임스탬프"
      }
  )
"""

import os
from datetime import datetime, timezone

import fitz # ← PyMuPDF 내부의 fitz 모듈을 import
import pdfplumber
from langchain_core.documents import Document


def load_pdf(file_path: str) -> list[Document]:
    """
    PDF 파일을 로드하는 진입점.

    Strategy:
      1. pdfplumber로 시도 (정확성 우선)
      2. 실패 시 PyMuPDF로 폴백 (호환성 확보)

    Args:
        file_path: PDF 파일 경로

    Returns:
        Document 리스트 (페이지별)

    Raises:
        ValueError: 두 라이브러리 모두 텍스트 추출 실패
    """
    filename = os.path.basename(file_path)
    try:
        return _load_with_pdfplumber(file_path, filename)
    except Exception:
        # pdfplumber 실패 → PyMuPDF로 재시도
        return _load_with_pymupdf(file_path, filename)


def load_txt(file_path: str) -> list[Document]:
    """
    TXT 파일을 로드하는 간단한 함수.

    TXT는 평문이므로 별도의 라이브러리 불필요.
    텍스트 전체를 하나의 page로 취급.

    Args:
        file_path: TXT 파일 경로

    Returns:
        Document 리스트 (1개 항목)
    """
    filename = os.path.basename(file_path)
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

    return [
        Document(
            page_content=text,
            metadata={
                "source": filename,
                "page": 1,  # TXT는 페이지 개념이 없으므로 1로 설정
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    ]


def load_document(file_path: str) -> list[Document]:
    """
    파일 확장자에 따라 적절한 로더를 선택하는 dispatching 함수.

    Args:
        file_path: 파일 경로 (PDF 또는 TXT)

    Returns:
        Document 리스트

    Raises:
        ValueError: 지원하지 않는 파일 형식
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return load_pdf(file_path)
    elif ext == ".txt":
        return load_txt(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def _load_with_pdfplumber(file_path: str, filename: str) -> list[Document]:
    """
    pdfplumber를 사용한 PDF 로더 (Primary).

    장점:
      - 표(table) 추출이 정확
      - 레이아웃 정보 보존

    단점:
      - 스캔 이미지 기반 PDF는 텍스트 추출 불가

    Args:
        file_path: PDF 파일 경로
        filename: 출처 파일명 (메타데이터용)

    Returns:
        Document 리스트 (페이지별 split)

    Raises:
        ValueError: 텍스트 추출 실패
    """
    docs: list[Document] = []

    with pdfplumber.open(file_path) as pdf:
        # enumerate(pdf.pages, start=1): 페이지 1부터 번호 매기기
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text()

            # 공백만 있는 페이지 무시
            if text and text.strip():
                docs.append(
                    Document(
                        page_content=text,
                        metadata={
                            "source": filename,
                            "page": i,  # 페이지 번호 (1-indexed)
                            "uploaded_at": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                )

    if not docs:
        raise ValueError("pdfplumber extracted no text")

    return docs


def _load_with_pymupdf(file_path: str, filename: str) -> list[Document]:
    """
    PyMuPDF (fitz)를 사용한 PDF 로더 (Fallback).

    pdfplumber 실패 시 호출됨.

    장점:
      - 매우 빠른 처리
      - 스캔 PDF(이미지)도 처리 가능
      - 경량

    단점:
      - 표 추출이 부정확할 수 있음

    Args:
        file_path: PDF 파일 경로
        filename: 출처 파일명 (메타데이터용)

    Returns:
        Document 리스트 (페이지별 split)

    Raises:
        ValueError: 텍스트 추출 실패
    """
    docs: list[Document] = []

    with fitz.open(file_path) as pdf:
        # enumerate(pdf, start=1): 페이지 1부터 번호 매기기
        for i, page in enumerate(pdf, start=1):
            # get_text(): 페이지의 모든 텍스트 추출
            text = page.get_text()

            # 공백만 있는 페이지 무시
            if text and text.strip():
                docs.append(
                    Document(
                        page_content=text,
                        metadata={
                            "source": filename,
                            "page": i,  # 페이지 번호 (1-indexed)
                            "uploaded_at": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                )

    if not docs:
        raise ValueError("PyMuPDF also extracted no text")

    return docs
