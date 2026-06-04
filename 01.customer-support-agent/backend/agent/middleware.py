"""
Phase 3/4 미들웨어 모음

Phase 3: inject_memory — 장기 기억을 system prompt에 동적으로 주입
Phase 4: block_inappropriate_input (Before Guardrail), PIIMiddleware (langchain 내장),
         check_hallucination (After Guardrail)

=== create_agent 미들웨어 구조 ===

system_prompt=SYSTEM_PROMPT        ← 정적 문자열
middleware=[block_inappropriate_input, inject_memory, ..., PIIMiddleware(...)]
context_schema=AgentContext        ← context로 user_id 전달
ToolRuntime[AgentContext]          ← 도구에서 store/context 접근

=== 미들웨어 실행 순서 ===

요청 처리 파이프라인 (chat.py → 에이전트 내부):
  [1] block_inappropriate_input (before_agent) → Before Guardrail
        욕설/부적절 입력이면 모델을 호출하지 않고 jump_to="end"로 단락.
        state["blocked"]=True + 거절 메시지를 주입 → 라우터가 status="blocked"로 변환.
  [2] inject_memory (wrap_model_call)            → 장기 기억 주입
  [3] PIIMiddleware.before_model                 → 입력 PII 마스킹
        ---- 모델 호출 ----
  [4] PIIMiddleware.after_model                  → 출력 PII 마스킹
  [5] check_hallucination (라우터에서 호출)       → After Guardrail (에이전트 실행 후)

Before Guardrail을 라우터의 일반 함수가 아니라 before_agent 미들웨어로 둔 이유:
  공식 권장 방식(횡단 관심사는 미들웨어 훅)이며, /chat·/chat/stream 등 모든 진입점에
  자동 적용되어 라우터마다 중복 호출할 필요가 없다. (순수 키워드 스캔 로직은
  테스트 가능하도록 is_blocked_input 함수로 분리해 미들웨어가 호출한다.)
"""

from typing import Any, Callable

from typing_extensions import NotRequired

from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langchain.agents.middleware import (
    AgentState,
    ModelRequest,
    ModelResponse,
    before_agent,
    wrap_model_call,
)

# ─── System Prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """당신은 B2B SaaS 고객 지원 에이전트입니다.

역할:
  - 고객의 질문에 친절하고 정확하게 답변하세요.
  - 답변은 반드시 업로드된 회사 문서를 기반으로 하세요.
  - 문서에 없는 내용은 "관련 정보를 문서에서 찾을 수 없습니다."라고 답변하세요.

도구 사용:
  - 고객 질문에 답변하기 전에 항상 search_documents 도구로 관련 문서를 먼저 검색하세요.
  - 검색 결과가 없으면 문서에 관련 내용이 없다고 안내하세요.
  - 고객이 선호도(언어, 응답 스타일 등)를 요청하면 save_user_preference 도구로 저장하세요.
  - 고객이 환불·결제 취소를 요청하면 submit_refund_request 도구를 호출하세요.
    이 도구는 고객 본인 확인 후 환불 '신청'을 접수합니다 (실제 환불은 관리자 승인 후).
    접수 후에는 "신청이 접수되었으며 관리자 검토 후 결과를 알려드린다"고 안내하세요.
"""

# ─── Phase 3: inject_memory ────────────────────────────────────────────────────

@wrap_model_call
async def inject_memory(request: ModelRequest, handler: Callable) -> ModelResponse:
    """장기 기억을 system prompt에 동적으로 주입하는 미들웨어.

    async 함수인 이유: chat.py가 `await agent.ainvoke(...)`로 실행하므로
    sync 함수만 정의하면 base awrap_model_call이 NotImplementedError를 발생시킴.
    @wrap_model_call에 async 함수를 넘기면 awrap_model_call 훅으로 등록됨.
    """
    if not request.runtime.store or not request.runtime.context:
        return await handler(request)

    user_id = request.runtime.context.user_id
    namespace = ("user_preferences", user_id)
    items = request.runtime.store.search(namespace)

    if not items:
        return await handler(request)

    preferences = "\n".join(
        f"- {item.key}: {item.value['value']}" for item in items
    )
    memory_text = f"\n\n[사용자 선호도 - 반드시 반영하세요]\n{preferences}"

    # 기존 system_prompt(역할/도구 지침)를 보존하고 선호도를 덧붙임.
    # override(system_prompt=memory_text)만 하면 base 지침이 통째로 사라짐.
    base_prompt = request.system_prompt or ""
    request = request.override(system_prompt=base_prompt + memory_text)
    return await handler(request)


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
    입력 텍스트가 욕설·부적절 콘텐츠를 포함하는지 검사하는 순수 함수.

    네트워크·상태가 없어 단위 테스트가 쉽다. 미들웨어(block_inappropriate_input)가
    이 함수를 호출해 차단 여부를 판정한다.

    Returns:
        (True, 거절 메시지)  — 차단 대상
        (False, "")          — 정상 입력
    """
    text_lower = text.lower()
    for keyword in _BLOCKED_KEYWORDS:
        if keyword in text_lower:
            return True, "부적절한 언어가 포함되어 있어 처리할 수 없습니다. 다시 문의해 주세요."
    return False, ""


class GuardrailState(AgentState):
    """Before Guardrail 결과를 라우터로 전달하기 위한 확장 state.

    AgentState(messages 등)에 두 필드를 더한다. 둘 다 NotRequired이므로
    평소 invoke에는 넣을 필요가 없고, 차단 시에만 미들웨어가 채운다.
    라우터는 result.get("blocked")로 분기한다.
    """

    blocked: NotRequired[bool]
    block_reason: NotRequired[str]


@before_agent(state_schema=GuardrailState, can_jump_to=["end"])
def block_inappropriate_input(state: GuardrailState, runtime) -> dict[str, Any] | None:
    """Before Guardrail: 욕설/부적절 입력이면 모델 호출 없이 단락한다.

    before_agent 훅 — 에이전트 진입 시 1회 실행(모델 호출마다 도는 before_model과 다름).
    이번 요청의 입력만 검사해야 하므로 가장 최근 HumanMessage를 본다
    (messages[-1]은 도구 호출 후 ToolMessage일 수 있어 부적합).

    차단 시 반환:
      jump_to="end"  → 모델/도구 노드를 건너뛰고 즉시 종료
      blocked/block_reason → 라우터가 status="blocked"로 변환
      messages       → 거절 메시지를 대화 기록에 남김(마지막 메시지가 됨)
    """
    last_human = next(
        (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        None,
    )
    if last_human is None:
        return None

    blocked, reason = is_blocked_input(last_human.text)
    if blocked:
        return {
            "jump_to": "end",
            "blocked": True,
            "block_reason": reason,
            "messages": [AIMessage(content=reason)],
        }
    return None


# ─── Phase 4: After Guardrail (할루시네이션 검증) ────────────────────────────

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
    """
    prompt = _HALLUCINATION_PROMPT.format(context=context, answer=answer)
    response = _get_monitor_llm().invoke(prompt)
    if "HALLUCINATION" in response.content.upper():
        return _HALLUCINATION_FALLBACK
    return answer
