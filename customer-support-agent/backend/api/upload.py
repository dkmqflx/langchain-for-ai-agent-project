"""
RAG 파이프라인 Step 5: 업로드 API (Upload Endpoint)

목적:
  - Step 1~4를 HTTP API로 통합
  - 클라이언트(프론트엔드)가 파일을 업로드하면 자동으로 RAG 파이프라인 실행
  - 업로드된 문서 목록 조회 기능

엔드포인트:
  POST /upload
    - 파일(PDF/TXT) 업로드 → RAG 파이프라인 실행
    - 성공: {"success": true, "message": "...", "data": {"filename": "...", "chunks": 47}}
    - 실패: {"success": false, "message": "...", "data": null}

  GET /documents
    - 업로드된 문서 목록 조회
    - 성공: {"success": true, "message": "...", "data": {"documents": [...]}}
    - 실패: {"success": false, "message": "...", "data": null}

파일 처리 흐름:
  1. 브라우저에서 파일 선택
  2. POST /upload (multipart/form-data)
  3. FastAPI가 UploadFile로 파싱
  4. 임시 파일로 저장 (/tmp/xxx.pdf)
  5. loader → splitter → embedder → vectorstore 순차 실행
  6. 성공 → JSON 응답
  7. 실패 → HTTP 500 에러 + 임시 파일 정리
"""

import os
import tempfile

from fastapi import APIRouter, UploadFile
from fastapi.responses import JSONResponse

from agent.tools import build_bm25
from rag.loader import load_document
from rag.splitter import split_documents
from rag.vectorstore import add_documents, vectorstore

# APIRouter: FastAPI에서 라우트 그룹화
# main.py에서 app.include_router(router)로 등록됨
router = APIRouter()

# 지원하는 파일 확장자
ALLOWED_EXTENSIONS = {".pdf", ".txt"}


@router.post("/upload")
async def upload_document(file: UploadFile):
    """
    파일 업로드 → Step 1~4 자동 실행.

    흐름:
      1. 파일 확장자 검증 (.pdf 또는 .txt만 허용)
      2. 임시 파일로 저장 (메모리 오버플로우 방지)
      3. loader.py: 텍스트 추출
      4. splitter.py: 청킹
      5. embedder.py: 벡터 변환 (캐시)
      6. vectorstore.py: pgvector 저장
      7. 성공 응답

    Args:
        file: FastAPI의 UploadFile (multipart/form-data)

    Returns (성공):
        {
            "success": true,
            "message": "File uploaded successfully",
            "data": {
                "filename": "manual.pdf",
                "chunks": 47
            }
        }

    Returns (실패):
        {
            "success": false,
            "message": "에러 메시지",
            "data": null
        }

    Example:
        # 클라이언트 (JavaScript)
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        const res = await fetch('/upload', { method: 'POST', body: formData });
        const json = await res.json();

        if (json.success) {
            console.log(`${json.data.chunks}개 청크 저장됨`);
        } else {
            console.error(json.message);
        }
    """
    # [1] 파일 확장자 검증
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": f"Unsupported file type: {ext}. Use PDF or TXT.",
                "data": None
            }
        )

    # [2] 임시 파일로 저장하는 이유:
    #
    # FastAPI의 UploadFile은 메모리에만 존재하는 객체입니다.
    # 하지만 loader.py의 load_document()는 파일 경로(/tmp/xxx.pdf)를 요구합니다.
    # 따라서 메모리의 파일 내용을 디스크의 임시 파일로 저장해야 합니다.
    #
    # 흐름:
    #   1. 프론트 → 파일 업로드 (메모리)
    #   2. 우리 → 임시 디스크 저장 (loader가 경로로 접근 가능)
    #   3. loader → 파일 경로로 읽기 (/tmp/tmpXXX.pdf)
    #   4. 마지막에 정리 (디스크 공간 낭비 방지)
    #
    # tempfile.NamedTemporaryFile 설정:
    #   - delete=False: with 블록을 빠져나가도 파일이 자동 삭제되지 않음
    #                   (finally에서 명시적으로 os.unlink()로 삭제)
    #   - suffix=ext: 임시 파일명에 .pdf, .txt 확장자 포함
    #                 (loader가 파일 형식을 인식하기 쉬움)
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        content = await file.read()  # 프론트에서 받은 파일 내용을 메모리에서 읽음
        tmp.write(content)  # 디스크의 임시 파일에 내용 기록
        tmp_path = tmp.name  # 임시 파일의 경로 저장 (예: /tmp/tmpABC123.pdf)

    try:
        # [3] RAG 파이프라인 실행
        documents = load_document(tmp_path)  # Step 1: 로드
        chunks = split_documents(documents)  # Step 2: 청킹
        ids = add_documents(chunks)  # Step 3~4: 임베딩 + 저장

        # [4] BM25 인덱스 재빌드
        # 새 문서가 추가됐으므로 search_documents Tool이 새 문서도 검색할 수 있도록 갱신
        build_bm25()

        # [5] 성공 응답
        return {
            "success": True,
            "message": "File uploaded successfully",
            "data": {
                "filename": file.filename,
                "chunks": len(ids),
            }
        }

    except Exception as e:
        # [5] 에러 처리: 상세 메시지를 클라이언트에 반환
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": str(e),
                "data": None
            }
        )

    finally:
        # [6] 임시 파일 정리 (매우 중요)
        #
        # 목적: 디스크 공간 낭비 방지
        # finally 블록: 성공(return)/실패(except) 관계없이 항상 실행됨
        #
        # 예시:
        #   - 성공: RAG 파이프라인 완료 → 임시 파일 불필요 → 삭제
        #   - 실패: 에러 발생 → 임시 파일 남아있음 → 반드시 정리해야 함
        #
        # 만약 finally가 없다면?
        #   - 매 업로드마다 /tmp 디렉토리에 쓰레기 파일이 쌓임
        #   - 디스크 용량 부족 에러 발생 가능
        os.unlink(tmp_path)  # 임시 파일 삭제


@router.get("/documents")
async def list_documents():
    """
    업로드된 문서 목록 조회.

    pgvector에 저장된 모든 청크를 검색해서 고유 source 추출.
    (각 source = 업로드된 하나의 파일)

    Returns (성공):
        {
            "success": true,
            "message": "Documents retrieved successfully",
            "data": {
                "documents": [
                    {"filename": "manual.pdf", "uploaded_at": "2026-05-27T..."},
                    {"filename": "faq.txt", "uploaded_at": "2026-05-26T..."}
                ]
            }
        }

    Returns (실패):
        {
            "success": false,
            "message": "에러 메시지",
            "data": null
        }

    Note:
        similarity_search("", k=1000)은 빈 쿼리로 모든 결과를 반환합니다.
        (k=1000은 최대 1000개의 고유 파일 지원을 의미)

    Example:
        # 클라이언트 (JavaScript)
        const res = await fetch('/documents');
        const json = await res.json();

        if (json.success) {
            json.data.documents.forEach(doc => {
                console.log(`${doc.filename} (${doc.uploaded_at})`);
            });
        } else {
            console.error(json.message);
        }
    """
    try:
        # 모든 벡터 검색 (빈 쿼리, 최대 1000개)
        results = vectorstore.similarity_search("", k=1000)

        # 고유 source 추출 (source = 파일명)
        sources = {}
        for doc in results:
            source = doc.metadata.get("source", "unknown")
            if source not in sources:  # 중복 제거
                sources[source] = {
                    "filename": source,
                    "uploaded_at": doc.metadata.get("uploaded_at", ""),
                }

        return {
            "success": True,
            "message": "Documents retrieved successfully",
            "data": {
                "documents": list(sources.values())
            }
        }

    except Exception as e:
        # 에러 발생 시 에러 응답 반환
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": str(e),
                "data": None
            }
        )
