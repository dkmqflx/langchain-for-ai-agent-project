# Phase 6 (1차): 채팅 스트리밍 설계

날짜: 2026-05-31
브랜치: `phase6-chat-streaming`
범위: plan.md Phase 6 중 **채팅 흐름만** (admin/approve 화면은 다음 세션)

## 1. 목표

고객이 채팅 UI에서 질문하면, 일반 답변은 토큰이 실시간으로 흘러나오고(streaming),
RAG/환불/차단 같은 특수 흐름은 안전하게 처리되는 풀스택 채팅 경험을 만든다.

- 백엔드: `POST /chat/stream` SSE 엔드포인트 추가 (`routers/chat.py`)
- 프론트엔드: Next.js 15 (App Router + Tailwind) 초기화 + `app/page.tsx` 채팅 UI

## 2. 핵심 설계 결정 (확정)

| # | 결정 | 근거 |
|---|------|------|
| 1 | **일반(도구 미사용) 답변만 토큰 스트리밍** | RAG 답변은 할루시네이션 검사로 통째 교체될 수 있어 스트리밍과 충돌. 검색 컨텍스트가 있는 답변은 버퍼링 후 검사본을 전송 |
| 2 | **단일 `/chat/stream` 엔드포인트가 내부에서 분기** | 에이전트가 런타임에 도구 호출 여부를 결정하므로, 프론트가 미리 RAG/일반을 구분해 다른 엔드포인트를 고를 수 없음 |
| 3 | **순수 Tailwind** (shadcn 미사용) | plan.md 명시. 의존성 최소, 학습용 투명성 |
| 4 | **PII 출력 마스킹 빈틈은 문서화된 학습용 한계** | 스트리밍 토큰은 `after_model` PII 마스킹 이전 단계. 입력 마스킹(`apply_to_input`)에 의존. 완전 보호는 비스트리밍 `/chat`에서만 |
| 5 | **`app.state` 리팩터링 안 함** | `get_agent()` 싱글톤 유지. 스트리밍과 무관한 리팩터링은 범위 밖. 다음 세션으로 미룸 |
| 6 | **이번 세션은 채팅 흐름만** | 전역 가이드의 "한 기능/컨텍스트 40%" 원칙. admin/approve는 다음 세션 |

## 3. 백엔드: `POST /chat/stream`

`sse-starlette`의 `EventSourceResponse` + `agent.astream(...)`로 구현. 기존 `/chat`,
`/chat/confirm`은 **변경하지 않고 그대로 둔다**(비스트리밍 경로 = 전체 안전장치 보존).

### 분기 로직

```
POST /chat/stream  (요청 바디는 기존 ChatRequest 재사용: message, thread_id, user_id)
  ① is_blocked_input(message) 체크
       차단됨 → event:blocked {response} 전송 → 종료 (에이전트 미실행)
  ② agent.astream(...) 실행하며 관찰:
       - search_documents ToolMessage 등장 여부(used_search) 추적
       - 최종 AIMessage 토큰 처리:
           · used_search == False → event:token {content} 실시간 전송
           · used_search == True  → 토큰을 버퍼에 누적(전송 안 함)
  ③ 스트림 종료 후:
       - __interrupt__ 감지(환불 본인 확인) → event:confirmation_required {thread_id, tool, args} → 종료
       - used_search == True → check_hallucination(버퍼, 검색컨텍스트) → event:message {response, status:"completed"}
       - 그 외(일반 답변) → 이미 token으로 다 보냄 → event:done {thread_id, status:"completed"}
  ④ 예외 → event:error {detail}
```

### 미해결 구현 디테일 (구현 단계에서 LangGraph 공식 문서로 검증)

- `astream`의 정확한 `stream_mode` 조합. 후보: `stream_mode=["updates", "messages"]`로
  토큰(messages)과 노드 단위 이벤트(updates, interrupt 포함)를 함께 수신.
- `__interrupt__` 감지 방식: 스트림 중 updates에서 잡을지, 스트림 종료 후 그래프 state에서
  확인할지. CLAUDE.md 규칙대로 **공식 문서 패턴으로 확정** 후 구현.
- 토큰 청크에서 "최종 답변 메시지"와 "도구 호출용 AIMessage"를 구분하는 방법
  (`metadata`의 노드명/`langgraph_node` 등 활용).

> 이 디테일들은 설계가 아니라 구현 검증 사항이다. 분기 **정책**(위 표/로직)은 확정됨.

### SSE 이벤트 프로토콜

| event | data | 의미 |
|-------|------|------|
| `token` | `{content}` | 일반 답변 토큰 (프론트에서 누적) |
| `message` | `{response, status:"completed"}` | RAG 답변 완성본 (할루시네이션 검사 통과) |
| `blocked` | `{response}` | Before 가드레일 차단 |
| `confirmation_required` | `{thread_id, tool, args}` | 환불 본인 확인 필요 |
| `done` | `{thread_id, status}` | 스트림 정상 종료 |
| `error` | `{detail}` | 처리 오류 |

`thread_id`, `user_id`는 기존 `/chat`과 동일하게 처리. 환불 확인은 기존 `POST /chat/confirm`을
그대로 사용(스트리밍 불필요).

## 4. 프론트엔드: `app/page.tsx`

- Next.js 15 App Router + Tailwind. `frontend/` 디렉토리에 초기화.
- `NEXT_PUBLIC_API_URL`(기본 `http://localhost:8000`)로 백엔드 호출.
- 채팅 전송: `fetch(`${API}/chat/stream`, {method:POST, body})` →
  `response.body.getReader()` → SSE 라인 파싱 → 이벤트별 상태 갱신.
- `thread_id`: 첫 진입 시 `crypto.randomUUID()`로 생성, 세션 동안 유지.
- 이벤트 처리:
  - `token` → 현재 어시스턴트 말풍선에 글자 누적
  - `message` → 말풍선을 완성본으로 설정
  - `confirmation_required` → "환불 신청을 확인하시겠어요?" 카드 + [확인]/[취소] →
    `POST /chat/confirm {thread_id, decision, user_id}` 호출, 응답을 말풍선에 표시
  - `blocked` → 차단 안내 메시지 표시
  - `error` → 오류 토스트/메시지
- 컴포넌트 분리(파일 단위 또는 컴포넌트 단위): 메시지 목록 / 입력창 / 확인 카드.
- 순수 Tailwind로 스타일링. 과한 추상화 금지(YAGNI).

## 5. 변경/생성 파일

| 파일 | 변경 |
|------|------|
| `backend/routers/chat.py` | **수정** — `POST /chat/stream` 추가 (기존 핸들러 불변) |
| `backend/requirements.txt` / `pyproject.toml` | **확인** — `sse-starlette` 존재 여부 확인, 없으면 추가 |
| `frontend/` | **생성** — Next.js 15 (App Router + Tailwind) 초기화 |
| `frontend/app/page.tsx` | **생성** — 채팅 UI + SSE 소비 |
| `frontend/.env.local` 또는 문서 | `NEXT_PUBLIC_API_URL` 안내 |

## 6. 검증 (수동)

1. 백엔드 기동 후 `curl -N` 또는 UI로 `/chat/stream` 호출:
   - 일반 질문(예: "안녕") → `token` 이벤트가 연속 도착, 글자가 흘러나옴
   - 문서 관련 질문(예: "환불 정책 알려줘") → `message` 이벤트로 완성본 1회 (할루시네이션 검사 거침)
   - 욕설 입력 → `blocked` 이벤트
   - "ORD-123 환불 요청" → `confirmation_required` 이벤트 → 확인 버튼 → `/chat/confirm` 처리
2. 프론트 채팅 UI에서 위 4가지 흐름이 화면에 올바르게 반영되는지 확인.

## 7. 범위 밖 (다음 세션)

- `frontend/app/admin/page.tsx` (문서 업로드)
- `frontend/app/approve/page.tsx` (관리자 승인 폴링)
- `app.state` + `Depends` 리팩터링
- LangSmith (환경변수만으로 자동 추적, 코드 변경 없음)

## 8. 학습 가이드

메모리 규약(`phase-learning-guide-convention`)에 따라, 구현 완료 후
`study/06_phase6_learning_guide.md`에 한국어 초보자 가이드를 작성한다.
