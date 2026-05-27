"""
FastAPI 진입점 (Entry Point)

목적:
  - FastAPI 앱 생성 + CORS 설정 + 라우터 등록
  - uvicorn으로 이 파일을 실행: uvicorn main:app --reload

CORS(Cross-Origin Resource Sharing):
  브라우저 보안 정책으로, 다른 도메인에서 API를 호출할 때 허용 여부를 결정.

  예시:
    프론트엔드: http://localhost:3000 (Next.js)
    백엔드:    http://localhost:8000 (FastAPI)
    → 도메인이 다름 → CORS 설정 없으면 브라우저가 요청 차단 🚫

  allow_origins에 프론트 주소를 추가하면 허용됨 ✅

라우터 등록:
  upload_router: POST /upload, GET /documents
  chat_router:   POST /chat

startup 이벤트:
  앱이 시작될 때 BM25 인덱스를 빌드.
  pgvector에 이미 문서가 있다면 인덱스 초기화.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

# .env 파일은 backend의 상위(customer-support-agent/) 디렉토리에 위치
load_dotenv(Path(__file__).parent.parent / ".env")
from fastapi.middleware.cors import CORSMiddleware

from agent.tools import build_bm25
from api.chat import router as chat_router
from api.upload import router as upload_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    앱 시작/종료 시 실행되는 로직.

    startup (yield 이전):
      - BM25 인덱스 빌드 (pgvector에 이미 있는 문서 반영)
      - DB가 비어있으면 그냥 넘어감 (_bm25_retriever = None 유지)

    shutdown (yield 이후):
      - 현재는 특별한 정리 작업 없음
    """
    # [startup] BM25 인덱스 초기화
    build_bm25()
    yield
    # [shutdown] 정리 작업 (현재 없음)


# FastAPI 앱 생성
app = FastAPI(
    title="Customer Support Agent API",
    description="RAG 기반 고객 지원 에이전트 API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 미들웨어 설정
# 프론트엔드(localhost:3000, Vercel)에서 API 호출 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",   # Next.js 로컬 개발 서버
        "https://*.vercel.app",    # Vercel 배포 프론트엔드
    ],
    allow_credentials=True,
    allow_methods=["*"],   # GET, POST, PUT, DELETE 등 모두 허용
    allow_headers=["*"],   # 모든 헤더 허용
)

# 라우터 등록
# upload_router: POST /upload, GET /documents
# chat_router:   POST /chat
app.include_router(upload_router)
app.include_router(chat_router)


@app.get("/health")
async def health():
    """서버 상태 확인 엔드포인트."""
    return {"status": "ok"}
