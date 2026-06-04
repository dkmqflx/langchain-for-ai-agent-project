"""
미들웨어 실행 순서 (에이전트 내부):
  block_inappropriate_input: before_agent 훅 — 진입 시 1회. 욕설/부적절 입력이면
                            모델 호출 없이 jump_to="end"로 단락하고 state["blocked"]=True 설정.
                            (모든 진입점 /chat·/chat/stream에 자동 적용 — 라우터 중복 제거)
  inject_memory:            wrap_model_call 훅 — 모델 호출을 감싸 system_prompt에 선호도 주입
  HumanInTheLoopMiddleware: after_model 훅 — 모델이 submit_refund_request 도구 호출을 내면
                            실행 직전에 interrupt()로 일시정지 (사용자 본인 확인 대기)
  PIIMiddleware:            before_model(입력 마스킹) / after_model(출력 마스킹) 훅
    before_model 순서: PIIMiddleware(email) → PIIMiddleware(card)
    after_model 순서:  PIIMiddleware(card) → PIIMiddleware(email)

PIIMiddleware 커스텀 detector 사유:
  기본 detector는 한국어 앞뒤 이메일과 하이픈 카드번호를 탐지 못함.
  커스텀 regex detector로 두 한계를 모두 해결.

Human-in-the-loop (사용자 본인 확인):
  HumanInTheLoopMiddleware는 checkpointer + thread_id가 필수 (둘 다 이미 구성됨).
  submit_refund_request 호출 시 interrupt 발동 → chat.py가 감지 → 사용자가 /chat/confirm으로
  확인/취소 → Command(resume)로 재개. (관리자 승인은 별도 refund 라우터에서 비동기 처리)
"""

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware, PIIMiddleware
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from agent.context import AgentContext
from agent.middleware import SYSTEM_PROMPT, block_inappropriate_input, inject_memory
from agent.tools import (
    get_user_preferences,
    save_user_preference,
    search_documents,
    submit_refund_request,
)

_llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0,
    streaming=True,
)

_checkpointer = InMemorySaver()
_store = InMemoryStore()

_agent = create_agent(
    model=_llm,
    tools=[search_documents, save_user_preference, get_user_preferences, submit_refund_request],
    system_prompt=SYSTEM_PROMPT,
    middleware=[
        block_inappropriate_input,  # Before Guardrail: 욕설 입력 시 모델 호출 없이 단락
        inject_memory,
        HumanInTheLoopMiddleware(
            interrupt_on={
                "submit_refund_request": {"allowed_decisions": ["approve", "reject"]},
            },
        ),
        PIIMiddleware(
            "email",
            detector=r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
            strategy="redact",
            apply_to_input=True,
            apply_to_output=True,
        ),
        PIIMiddleware(
            "credit_card",
            detector=r"(?<!\d)\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}(?!\d)",
            strategy="mask",
            apply_to_input=True,
            apply_to_output=True,
        ),
    ],
    checkpointer=_checkpointer,
    store=_store,
    context_schema=AgentContext,
)


def get_agent():
    return _agent
