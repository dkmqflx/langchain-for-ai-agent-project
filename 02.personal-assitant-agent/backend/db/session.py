"""
DB 연결 + 세션 관리 (SQLAlchemy 2.0 공식 패턴)

구성 요소:
  - engine:       DB로 가는 커넥션 풀 (앱당 1개)
  - SessionLocal: 요청마다 만들어 쓰는 "작업 단위"(트랜잭션) 팩토리
  - Base:         모든 테이블 모델이 상속하는 부모 (DeclarativeBase)
  - get_db():     FastAPI Depends용 의존성. 요청 시작 시 세션 열고, 끝나면 닫음.

왜 get_db()가 yield를 쓰는가 (FastAPI 공식: di-yield-cleanup):
  yield 위 = 준비(세션 생성), yield 아래 = 정리(세션 종료).
  요청 처리 중 예외가 나도 finally에서 반드시 close → 커넥션 누수 방지.

동기(sync) SQLAlchemy를 쓰는 이유:
  psycopg/SQLAlchemy 호출은 블로킹 I/O다. 그래서 이 세션을 쓰는 엔드포인트는
  async def가 아니라 def로 선언해 FastAPI가 threadpool에서 돌리게 한다
  (FastAPI 공식: async-def-vs-def).
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import get_settings

# echo=False: SQL 로그 끔 (디버깅 시 True로)
engine = create_engine(get_settings().database_url, echo=False, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """모든 ORM 모델의 부모 클래스."""


def get_db() -> Generator[Session, None, None]:
    """요청 단위 DB 세션 (FastAPI Depends)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
