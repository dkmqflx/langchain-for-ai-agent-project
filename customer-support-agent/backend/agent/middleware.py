"""
Phase 3/4 미들웨어 모음

Phase 3: inject_memory — 장기 기억을 system prompt에 동적으로 주입
Phase 4: mask_pii, is_blocked_input, check_hallucination — 안전성 레이어

=== Phase 3: inject_memory ===

작동 방식:
  고객 A (user_id="cust-001"):
    store에서 ("user_preferences", "cust-001") 조회
    → "language: 한국어" 발견 → system prompt 끝에 추가
    → GPT가 자동으로 한국어로 답변

  고객 B (user_id="cust-002"):
    저장된 선호도 없음 → 기본 system prompt만 사용

make_inject_memory 팩토리 패턴:
  agent.py가 store를 만들어서 전달 → middleware.py가 클로저로 캡처
  순환 import(middleware → agent → middleware) 방지 ✅

=== Phase 4: 안전성 레이어 ===

요청 처리 파이프라인:
  [입력 PII 마스킹] → [Before Guardrail] → [Agent] → [After Guardrail] → [출력 PII 마스킹]

  mask_pii:          이메일/카드번호를 정규식으로 탐지해 치환
  is_blocked_input:  키워드 기반 욕설 차단 (에이전트 실행 전 단락)
  check_hallucination: GPT-4o-mini 감시자가 답변의 할루시네이션 검증
                       search_documents 결과가 있을 때만 실행 (컨텍스트 없으면 검증 불가)

할루시네이션 검증 설계:
  - 에이전트가 search_documents를 한 번 이상 호출했을 때만 실행
  - 여러 번 호출 시 모든 결과를 합쳐서 검증 (마지막 결과만 쓰면 오탐 발생)
  - HALLUCINATION 판정 시 교정된 메시지로 대체 (환각 내용 그대로 노출 방지)

입력/출력 모두에 PII 마스킹을 적용하는 이유:
  - 입력 마스킹: checkpointer(단기 기억)에 PII가 저장되지 않도록
  - 출력 마스킹: 에이전트가 PII를 그대로 반복하는 경우 대비
"""

import re

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.store.base import BaseStore

# ─── System Prompt (Phase 3 inject_memory가 이 문자열 끝에 선호도를 동적으로 추가) ───

SYSTEM_PROMPT = """당신은 B2B SaaS 고객 지원 에이전트입니다.

역할:
  - 고객의 질문에 친절하고 정확하게 답변하세요.
  - 답변은 반드시 업로드된 회사 문서를 기반으로 하세요.
  - 문서에 없는 내용은 "관련 정보를 문서에서 찾을 수 없습니다."라고 답변하세요.

도구 사용:
  - 고객 질문에 답변하기 전에 항상 search_documents 도구로 관련 문서를 먼저 검색하세요.
  - 검색 결과가 없으면 문서에 관련 내용이 없다고 안내하세요.
  - 고객이 선호도(언어, 응답 스타일 등)를 요청하면 save_user_preference 도구로 저장하세요.
"""

# ─── Phase 3: inject_memory ───────────────────────────────────────────────────

def make_inject_memory(store: BaseStore):
    """
    장기 기억 주입 함수를 반환하는 팩토리.

    Args:
        store: InMemoryStore 인스턴스 (agent.py에서 생성해서 전달)

    Returns:
        inject_memory: create_react_agent의 prompt 파라미터로 사용 가능한 callable
                       시그니처: (state, config) -> list[BaseMessage]
    """
    def inject_memory(state, config: RunnableConfig) -> list:
        user_id = config["configurable"].get("user_id", "anonymous")
        namespace = ("user_preferences", user_id)

        items = store.search(namespace)

        memory_text = ""
        if items:
            preferences = "\n".join(
                f"- {item.key}: {item.value['value']}" for item in items
            )
            memory_text = f"\n\n[사용자 선호도 - 반드시 반영하세요]\n{preferences}"

        system_content = SYSTEM_PROMPT + memory_text
        return [SystemMessage(content=system_content)] + list(state["messages"])

    return inject_memory


# ─── Phase 4: PII 마스킹 ──────────────────────────────────────────────────────

# 이메일: user@example.com 패턴
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# 카드번호: 16자리 숫자 (하이픈·공백 구분자 허용)
# 앞 12자리는 마스킹, 마지막 4자리는 노출
# \b 대신 lookahead/lookbehind 사용: 한국어 등 유니코드 문자도 \w로 분류되어
# \b가 한글-숫자 경계에서 예상대로 작동하지 않기 때문
_CARD_RE = re.compile(r"(?<!\d)(\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?)(\d{4})(?!\d)")


def mask_pii(text: str) -> str:
    """
    텍스트에서 이메일과 카드번호를 마스킹한다.

    이메일 → [EMAIL REDACTED]
    카드번호 → ****-****-****-1234  (마지막 4자리만 노출)
    """
    text = _EMAIL_RE.sub("[EMAIL REDACTED]", text)
    text = _CARD_RE.sub(r"****-****-****-\2", text)
    return text


# ─── Phase 4: Before Guardrail (욕설/부적절 콘텐츠 차단) ─────────────────────

# 실제 서비스에서는 전용 필터 라이브러리로 교체 권장 (현재는 학습용 최소 목록)
_BLOCKED_KEYWORDS = [
    # 한국어
    "씨발", "개새끼", "병신", "지랄", "꺼져", "죽어", "바보", "멍청이",
    # 영어
    "fuck", "shit", "asshole", "bastard", "kill yourself",
]


def is_blocked_input(text: str) -> tuple[bool, str]:
    """
    입력 텍스트가 욕설·부적절 콘텐츠를 포함하는지 검사한다.

    Returns:
        (True, 거절 메시지)  — 차단 대상
        (False, "")          — 정상 입력
    """
    text_lower = text.lower()
    for keyword in _BLOCKED_KEYWORDS:
        if keyword in text_lower:
            return True, "부적절한 언어가 포함되어 있어 처리할 수 없습니다. 다시 문의해 주세요."
    return False, ""


# ─── Phase 4: After Guardrail (할루시네이션 검증) ────────────────────────────

# 감시자 모델: 첫 호출 시 한 번만 생성 (모듈 임포트 시 API 키가 없어도 됨)
_monitor_llm: ChatOpenAI | None = None


def _get_monitor_llm() -> ChatOpenAI:
    global _monitor_llm
    if _monitor_llm is None:
        _monitor_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    return _monitor_llm

_HALLUCINATION_PROMPT = """당신은 AI 답변 품질 검사관입니다.

아래 [컨텍스트]에 근거하지 않은 사실이 [답변]에 포함되어 있으면 "HALLUCINATION"이라고만 답하세요.
컨텍스트에 기반한 정확한 답변이라면 "OK"라고만 답하세요.

[컨텍스트]
{context}

[답변]
{answer}"""

_HALLUCINATION_FALLBACK = (
    "관련 정보를 문서에서 찾을 수 없습니다. "
    "더 구체적인 질문을 해주시거나, 관련 문서가 업로드되어 있는지 확인해 주세요."
)


def check_hallucination(answer: str, context: str) -> str:
    """
    에이전트 답변이 검색된 컨텍스트에 근거하는지 GPT-4o-mini로 검증한다.

    search_documents 결과가 있을 때만 호출할 것 (컨텍스트 없으면 오탐 발생).
    여러 번 검색된 경우 모든 결과를 합쳐서 전달해야 정확한 판정 가능.

    Returns:
        정상: 원본 answer 그대로
        할루시네이션: _HALLUCINATION_FALLBACK 메시지
    """
    prompt = _HALLUCINATION_PROMPT.format(context=context, answer=answer)
    response = _get_monitor_llm().invoke(prompt)
    if "HALLUCINATION" in response.content.upper():
        return _HALLUCINATION_FALLBACK
    return answer
