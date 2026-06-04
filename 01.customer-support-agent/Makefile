BACKEND_DIR = backend

# 백엔드 개발 서버 (hot reload)
dev:
	cd $(BACKEND_DIR) && uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 백엔드 운영 서버 (멀티 워커)
start:
	cd $(BACKEND_DIR) && uv run uvicorn main:app --workers 4 --host 0.0.0.0 --port 8000

# 테스트
test:
	cd $(BACKEND_DIR) && uv run pytest

# 의존성 설치
install:
	cd $(BACKEND_DIR) && uv sync

# PostgreSQL 컨테이너 시작
db:
	docker compose up -d

# PostgreSQL 컨테이너 종료
db-down:
	docker compose down

# 전체 시작 (DB + 백엔드)
up: db
	sleep 2
	$(MAKE) dev

.PHONY: dev start test install db db-down up
