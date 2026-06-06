# Phase 1 학습 가이드 — 백엔드 `/chat/stream`을 AI SDK Data Stream Protocol로 변환

> ⚠️ **이 Phase는 프론트엔드 코드가 아니라 백엔드를 수정합니다.**
> 문서는 `frontend/study/`에 있지만, 실제로 손대는 파일은
> `backend/routers/chat.py`와 `backend/agent/streaming.py`입니다.
> "프론트(`useChat`)가 받기를 기대하는 형식"을 백엔드가 그대로 내보내도록 만드는 단계라
> 프론트엔드 시리즈의 0번째 관문으로 분류합니다.
>
> **왜 가장 먼저, 그리고 단독으로?**
> 출력 "형식"만 바꾸고 에이전트 로직(가드레일·HITL·할루시네이션·PII)은 **건드리지 않습니다.**
> 형식 한 글자가 틀리면 `useChat`이 스트림을 파싱하지 못해 화면이 빕니다 — 그래서 가장 위험하고, 단독 Phase입니다.

---

## 선행 과제 (착수 전 반드시 확인) ✅ 이미 검증됨

plan.md는 "AI SDK가 v6라서 문서의 파트 표가 v5 표기일 수 있으니 재확인하라"고 두 번 경고합니다(plan 72·105행).
**이 가이드를 쓰면서 설치된 패키지(`ai@6.0.197`, `@ai-sdk/react@3.0.199`)의 실제 타입 정의로 모두 검증했습니다.**

검증 출처: `frontend/node_modules/ai/dist/index.d.ts`의 `UIMessageChunk` 유니온 타입.
→ 결론: **plan의 파트 형식은 v6와 일치합니다.** 아래 표는 "그 타입 정의에서 직접 뽑은 값"입니다(상상한 필드 아님).

---

## 학습 흐름도

```
고객 메시지 (POST /chat/stream)
     ↓
[기존] 에이전트 파이프라인 (가드레일·RAG·HITL·할루시네이션·PII)   ← 그대로 둠
     ↓
[기존] 커스텀 SSE 이벤트 (event: token / blocked / confirmation_required / done)
     ↓
[이번 Phase] 출력 어댑터: 커스텀 이벤트 → AI SDK "UI Message Stream" 파트로 매핑
     ↓
data: {"type":"text-delta","id":"0","delta":"안"}\n\n      ← 토큰
data: {"type":"data-blocked", ...}                        ← 커스텀 data 파트
data: [DONE]
     ↓
프론트엔드 useChat 가 그대로 소비
```

핵심 한 줄: **"로직은 그대로, 출구의 포장지만 교체."**

---

## Step 1: "왜 형식을 바꿔야 하나" 이해하기 (5분)

### 핵심 개념

`useChat`(AI SDK UI)은 아무 SSE나 받지 않습니다. **정해진 JSON 파트들의 스트림**만 이해합니다.
이걸 **Data Stream Protocol**(= UI Message Stream)이라고 부릅니다.

- 다른 언어/프레임워크 백엔드(FastAPI 등)는 이 형식을 **직접 emit**하고,
  프론트는 `useChat`을 그 엔드포인트로 가리키면 됩니다. (plan의 "C안")
- 즉 우리가 할 일은 번역기 하나를 백엔드 출구에 붙이는 것입니다.

### 학습 질문
- [ ] 왜 Next.js 프록시(B안)가 아니라 FastAPI 직접 emit(C안)을 택했나? (힌트: 레이어가 하나 줄어듦 + 공식 권장)
- [ ] `useChat`이 "정해진 형식"만 받는다는 게 왜 안전장치가 되나?

---

## Step 2: v6 파트 형식 익히기 (검증된 사실) (10분)

아래는 `ai@6.0.197`의 `UIMessageChunk` 타입에서 **실제로 확인한** 파트들입니다.

### 텍스트 파트 (답변 본문)
```jsonc
{ "type": "text-start", "id": "0" }                       // 텍스트 블록 시작
{ "type": "text-delta", "id": "0", "delta": "안녕" }       // 토큰 조각 (반복)
{ "type": "text-end",   "id": "0" }                       // 텍스트 블록 끝
```
- `id`는 같은 텍스트 블록을 묶는 키입니다. 한 답변이면 `"0"`으로 통일.
- 토큰은 `delta`에 **조각**으로 들어갑니다(누적 X, 조각만).

### 메시지 경계 파트
```jsonc
{ "type": "start" }    // (선택) 메시지 시작. messageId? 포함 가능
{ "type": "finish" }   // 메시지 끝. finishReason? 포함 가능
```

### 에러 파트
```jsonc
{ "type": "error", "errorText": "..." }   // 필드명은 errorText (message 아님!)
```

### 커스텀 data 파트 (이 프로젝트 고유 흐름)
```jsonc
// 타입은 반드시 "data-" 접두사. NAME은 우리가 정하는 이름.
{ "type": "data-blocked",      "data": { "reason": "..." } }
{ "type": "data-confirmation", "data": { "tool": "...", "args": {}, "thread_id": "..." } }
```
- 형태: `{ "type": "data-<이름>", "id?": "...", "data": <임의 JSON>, "transient?": bool }`
- `data-blocked`(욕설 차단)·`data-confirmation`(환불 본인확인)은 **표준에 없는 우리 도메인 신호**라
  표준 `data-*` 메커니즘으로 실어 보냅니다. → Phase 3에서 프론트가 이걸 받아 처리합니다.

### 종료 신호
```
data: [DONE]
```
- 모든 파트는 `data: <JSON>\n\n` 한 줄(SSE)로 보내고, 맨 끝에 `data: [DONE]`을 보냅니다.

### 응답 헤더 (검증된 정확한 값)
```
x-vercel-ai-ui-message-stream: v1
```
- `node_modules/ai/dist/index.js`에서 상수로 확인됨. 이 헤더가 없으면 `useChat`이 스트림으로 인식하지 못할 수 있습니다.

### 학습 질문
- [ ] `text-delta`의 `delta`는 누적 텍스트인가 조각인가?
- [ ] 에러 파트의 필드명은 `message`인가 `errorText`인가? (틀리면 조용히 무시됨)
- [ ] `data-confirmation`이 왜 표준 파트가 아니라 `data-*`로 가야 하나?

---

## Step 3: 기존 이벤트 → v6 파트 매핑표 (핵심 작업) (15분)

`streaming.py`가 지금 내보내는 커스텀 이벤트를 아래처럼 1:1로 바꿉니다.

| 기존 (커스텀 SSE) | → v6 파트 |
|---|---|
| 응답 시작 | `{"type":"start"}` 후 `{"type":"text-start","id":"0"}` |
| `event: token` `{content}` | `{"type":"text-delta","id":"0","delta":"<content>"}` |
| 답변 끝 | `{"type":"text-end","id":"0"}` |
| `event: blocked` | `{"type":"data-blocked","data":{"reason":"..."}}` |
| `event: confirmation_required` | `{"type":"data-confirmation","data":{"tool":"...","args":{...},"thread_id":"..."}}` |
| `event: done` | `{"type":"finish"}` 후 `data: [DONE]` |
| 예외 | `{"type":"error","errorText":"..."}` |

### RAG 답변 버퍼링 처리 (가장 헷갈리는 부분)
현재 백엔드는 **검색(RAG) 답변일 때** 토큰을 바로 흘리지 않고, 모았다가 할루시네이션 검사 후 한 번에 내보냅니다.
프로토콜로 옮길 때도 그 동작을 유지합니다:

- **일반 답변**: `text-delta`를 토큰마다 실시간 emit (스트리밍 그대로).
- **RAG 답변**: deltas를 보류 → 검사 통과한 최종본을
  `text-start` → `text-delta`(전체를 한 덩어리로) → `text-end` 로 **1회** emit.

### 유지되는 알려진 한계 (별도 개선 금지)
- 출력 PII 마스킹·할루시네이션 교정 "보장"은 비스트리밍 `POST /chat`에서만.
  스트리밍 경로의 이 한계는 plan/설계 문서에 이미 적힌 사항이라 **그대로 둡니다.**

### 학습 질문
- [ ] 일반 답변과 RAG 답변의 emit 방식이 다른 이유는?
- [ ] RAG 답변을 실시간 스트리밍하면 무슨 문제가 생기나? (힌트: 검사 전 잘못된 문장이 화면에 먼저 뜸)

---

## Step 4: `chat.py` / `streaming.py`에서 손볼 곳 (10분)

### 코드 읽기 팁
- `backend/agent/streaming.py`: 토큰/인터럽트를 판별해 SSE를 만드는 헬퍼. **여기가 번역기의 본체.**
  기존 `event: token` 생성 부분을 `text-delta` JSON 생성으로 바꾸는 게 핵심.
- `backend/routers/chat.py`의 `POST /chat/stream`: 응답 헤더에
  `x-vercel-ai-ui-message-stream: v1`을 추가하고, 종료 시 `data: [DONE]`을 보냄.
- **CRLF 함정**(backend/CLAUDE.md에 기록됨): `sse-starlette`는 이벤트 구분자를 `\r\n\r\n`으로 내보냅니다.
  프론트 fetch 기반 클라이언트가 `\n\n`만 보면 화면이 빕니다 — v6 `useChat`이 어떻게 끊어 읽는지와 충돌하지 않는지 확인.

### CORS
- `backend/main.py`에 CORS가 이미 설정됨. `localhost:3000` Origin이 허용 목록에 있는지만 점검(목록 추가만, 새로 만들지 말 것).

---

## 검증 (Verification)

```bash
# 1) 스트림 형식 + 헤더 확인
curl -N -H "Content-Type: application/json" \
  -d '{"message":"안녕"}' http://localhost:8000/chat/stream -i
```
확인 항목:
- [ ] 응답 헤더에 `x-vercel-ai-ui-message-stream: v1`.
- [ ] 본문이 `data: {"type":"text-delta",...}` 형식으로 흐른다.
- [ ] 마지막이 `data: [DONE]`.

```bash
# 2) 욕설 입력 → data-blocked 파트
curl -N -d '{"message":"<욕설>"}' http://localhost:8000/chat/stream
# 3) 환불 요청 → data-confirmation 파트
curl -N -d '{"message":"환불해줘 ORD-123"}' http://localhost:8000/chat/stream
```
- [ ] 욕설 → `data-blocked` 등장.
- [ ] 환불 → `data-confirmation` 등장(tool/args/thread_id 포함).
- [ ] 비스트리밍 `POST /chat`은 영향 없음(기존 테스트 통과).

```bash
cd backend && uv run pytest tests/ -q          # 기존 테스트 회귀 확인
```

---

## 검증 체크리스트 (개념 이해)

- [ ] Data Stream Protocol이 "정해진 JSON 파트의 스트림"이라는 걸 설명할 수 있다.
- [ ] `text-start/delta/end`의 역할과 `id`의 의미를 안다.
- [ ] 커스텀 신호는 `data-*` 파트로 보낸다는 규칙을 안다.
- [ ] RAG 답변만 버퍼링→1회 emit 하는 이유를 안다.
- [ ] 헤더·`[DONE]`·CRLF 함정을 안다.

---

## 커밋

```
feat(backend): emit ai sdk data stream protocol on /chat/stream
```

## 다음 단계
- **Phase 2**: 이 엔드포인트에 `useChat`을 연결해 토큰을 실시간 렌더 (단, `next build` 선결 과제 먼저).
- **Phase 3**: 여기서 만든 `data-blocked`/`data-confirmation`을 프론트가 받아 처리.
