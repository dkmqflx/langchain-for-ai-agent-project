"""
FastAPI 진입점 (Phase 1)

조립 순서:
  1. lifespan에서 테이블 생성 (Base.metadata.create_all)
  2. SessionMiddleware  — OAuth state를 서버 세션에 안전하게 보관 (CSRF 방어)
  3. CORSMiddleware     — 프론트엔드(localhost:3000) 호출 허용
  4. auth 라우터 등록

실행:
  cd 02.personal-assitant-agent/backend
  uv run uvicorn main:app --reload --port 8000

참고:
  - 테이블 생성을 lifespan에서 create_all로 처리하는 것은 학습용 간이 방식.
    실서비스에서는 Alembic 마이그레이션을 사용한다.
  - DB(assistant_db)와 .env가 준비돼 있어야 정상 기동한다.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from config import get_settings
from db import models  # noqa: F401  (create_all 전에 User 모델을 Base에 등록)
from db.session import Base, engine
from routers import auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    # [startup] users 테이블이 없으면 생성
    Base.metadata.create_all(bind=engine)
    yield
    # [shutdown] 정리 작업 없음


app = FastAPI(
    title="Personal Assistant Agent API",
    description="AI 개인 비서 에이전트 — Phase 1: Google OAuth2 인증",
    version="0.1.0",
    lifespan=lifespan,
)

# OAuth state 보관용 세션 (itsdangerous로 서명된 쿠키)
app.add_middleware(SessionMiddleware, secret_key=get_settings().session_secret)

# 프론트엔드 호출 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)


@app.get("/health")
def health() -> dict[str, str]:
    """서버 상태 확인."""
    return {"status": "ok"}
