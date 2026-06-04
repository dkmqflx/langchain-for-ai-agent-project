# Backend 규약 (CLAUDE.md)

이 문서는 **backend 디렉토리 고유의 규약**만 다룬다.
테크스택, 전체 저장소 구조, API 엔드포인트 표, "공식 문서 전용" 코딩 표준, 구현 Phase는
**루트 `CLAUDE.md`를 참조**한다 (여기서 중복하지 않는다).

---

## 1. 레이어 구조와 책임

```
backend/
├── main.py        # 앱 조립: FastAPI 생성, CORS, 전역 예외 핸들러, 라우터 등록, lifespan(BM25 빌드)
├── routers/       # HTTP 엔드포인트 (얇게 유지). 요청 파싱 → 서비스 호출 → 응답 봉투 반환
│   ├── chat.py    #   POST /chat, /chat/confirm, /chat/stream(SSE)
│   ├── refund.py  #   GET /pending, POST /approve, GET /refunds
│   └── upload.py  #   POST /upload, GET /documents
├── models/        # Pydantic 요청/응답 모델 (라우터당 1파일 + 공용 common)
│   ├── common.py  #   ErrorResponse (공용 에러 봉투)
│   ├── chat.py / refund.py / upload.py
├── agent/         # LangChain 에이전트 영역
│   ├── agent.py        # create_agent 조립 (모델, 도구, 미들웨어 순서)
│   ├── tools.py        # 도구 정의 + BM25 인덱스(build_bm25)
│   ├── middleware.py   # inject_memory, 가드레일, PII 등
│   ├── context.py      # AgentContext (user_id 등 런타임 컨텍스트)
│   ├── refund_store.py # 환불 신청 인메모리 저장소 (LangGraph checkpointer와 별개)
│   └── streaming.py    # SSE 스트림 헬퍼 (토큰/인터럽트 판별)
├── rag/           # RAG 파이프라인 (loader → splitter → embedder → vectorstore, bm25)
└── tests/
```

**레이어 규칙**
- `routers/`는 얇게. 비즈니스 로직은 `agent/`·`rag/`에 두고 라우터는 호출·응답 조립만 한다.
- 의존 방향은 `routers → models/agent/rag` 단방향. `agent`·`rag`는 `routers`를 import하지 않는다.
- 엔드포인트는 `async def`. `APIRouter(tags=[...])`로 그룹화하고 등록은 `main.py`에서 한다.

---

## 2. 응답 형식 규약 (가장 중요)

**모든 JSON 응답은 성공·실패 동일하게 다음 봉투(envelope)를 사용한다.**
필드 순서도 이대로 유지한다:

```jsonc
{ "data": <T | null>, "isSuccess": <bool>, "code": <string>, "message": <string> }
```

| 상황 | data | isSuccess | code | message |
|---|---|---|---|---|
| 성공 | 페이로드(타입 모델) | `true` | `"SUCCESS"` | 사람이 읽을 설명 |
| HTTPException | `null` | `false` | `"HTTP_<상태코드>"` (예: `HTTP_404`) | `exc.detail` |
| 요청 검증 실패(422) | `null` | `false` | `"VALIDATION_ERROR"` | `"필드: 사유; ..."` 상세 |

**규칙**
1. **에러는 `raise HTTPException(...)`** — 절대 에러 dict를 `return`하지 않는다.
   변환은 `main.py`의 전역 핸들러가 담당한다 (라우터에서 봉투를 직접 만들지 않는다).
2. **422는 `RequestValidationError` 핸들러**가 처리한다 (HTTPException이 아니므로 별도 핸들러 필요).
   FastAPI 기본 `{"detail": [...]}`를 그대로 내보내지 않는다.
3. 넓은 `except` 안에서는 `HTTPException`을 먼저 재-raise 한다:
   ```python
   except HTTPException:
       raise
   except Exception as e:
       raise HTTPException(status_code=500, detail=str(e))
   ```
4. **성공 응답 모델의 `data`는 nullable로 두지 않는다.** 실패는 `ErrorResponse`가 담당하므로
   `data: UploadData`처럼 non-null로 선언한다 (`UploadData | None` 금지 — OpenAPI에 `anyOf null`이 생긴다).

---

## 3. 모델 컨벤션 (`models/`)

- 라우터당 모델 파일 1개, 공용 에러 봉투는 `models/common.py`의 `ErrorResponse`.
- 성공 응답 모델은 봉투 4필드를 `{data, isSuccess, code, message}` 순으로 선언하고
  `isSuccess: bool = True`, `code: str = "SUCCESS"` 기본값을 둔다 (`message`는 필수).
- **모든 엔드포인트는 성공 응답에 `response_model=`을 단다.** 안 달면 OpenAPI에 `any`로 노출된다.
- Swagger 예시가 빈약해지지 않도록 데이터 모델 필드에 현실적인 `Field(examples=[...])`를 부여한다.
- 상태/열거 타입은 단일 출처를 재사용한다 (예: `agent.refund_store.RefundStatus`).

---

## 4. OpenAPI 에러 문서화

- 엔드포인트 데코레이터에 `responses=`로 에러 응답을 문서화한다:
  ```python
  @router.post("/upload", response_model=UploadResponse, status_code=201,
      responses={
          400: {"model": ErrorResponse, "description": "..."},
          422: {"model": ErrorResponse, "description": "..."},
          500: {"model": ErrorResponse, "description": "..."},
      })
  ```
- **실제로 봉투를 반환할 수 있는 코드만** 문서화한다 (정확성 우선):
  - 요청 바디/쿼리 파라미터가 있으면 → `422`
  - `raise HTTPException(status_code=...)`가 있으면 → 그 코드 (400/404/500 등)
  - 파라미터도 없고 `raise`도 없으면 → 에러 문서를 달지 않는다.
- 미처리 예외는 전역 핸들러를 타지 않아 봉투로 안 나간다. 봉투 500을 보장하려면 라우터에서
  `except Exception → raise HTTPException(500)`으로 명시 변환해야 한다.

---

## 5. 코드 스타일

- 주석·독스트링은 **한국어 교육용 톤**(왜/흐름 설명 위주)으로 일관되게 작성한다.
- import 순서: 표준 라이브러리 → 서드파티 → 로컬(`from agent...`, `from models...`).
- 의존성은 `uv`로 관리(`uv run ...`). 루트 "공식 문서 전용" 규칙을 따르고,
  `langchain-community`는 import 금지.

---

## 6. 함정 / 주의 (실제로 겪은 것)

- **에이전트 미들웨어의 `wrap_model_call` 훅은 `async def` + `await handler(...)`** 여야 한다.
  `chat.py`가 `agent.ainvoke`로 실행하기 때문이다 (동기 훅이면 실행이 깨진다).
- **SSE 클라이언트는 이벤트 구분자를 `\r\n\r\n`으로 split** 해야 한다(`\n\n` 아님).
  `sse-starlette`가 CRLF로 내보내므로, fetch 기반 클라이언트가 `\n\n`만 보면 화면이 빈다.
- `/chat/stream`은 스트림 **시작 전** 검증 실패(422)만 JSON 봉투로 나가고, 시작 후 오류는
  SSE `error` 이벤트(`{"detail": ...}`)로 나간다 — 이 둘은 다른 프로토콜이다.

---

## 7. 검증 (변경 후 / 커밋 전)

```bash
# 1) 임포트 deprecation 검사 (루트 규칙)
uv run python -W error::DeprecationWarning -c "import main"

# 2) 테스트
uv run pytest tests/ -q

# 3) OpenAPI 스키마 확인 (응답 모델/에러 문서가 의도대로인지)
uv run python -c "import main, json; print(json.dumps(main.app.openapi()['paths'], ensure_ascii=False)[:2000])"
```
