"""
미들웨어 실행 순서 (에이전트 내부):
  wrap_model_call 순서: inject_memory → PIIMiddleware(email) → PIIMiddleware(card)
  after_model 순서:  PIIMiddleware(card) → PIIMiddleware(email)

PIIMiddleware 커스텀 detector 사유:
  기본 detector는 한국어 앞뒤 이메일과 하이픈 카드번호를 탐지 못함.
  커스텀 regex detector로 두 한계를 모두 해결.
"""

from langchain.agents import create_agent
from langchain.agents.middleware import PIIMiddleware
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from agent.context import AgentContext
from agent.middleware import SYSTEM_PROMPT, inject_memory
from agent.tools import get_user_preferences, save_user_preference, search_documents

_llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0,
    streaming=True,
)

_checkpointer = InMemorySaver()
_store = InMemoryStore()

_agent = create_agent(
    model=_llm,
    tools=[search_documents, save_user_preference, get_user_preferences],
    system_prompt=SYSTEM_PROMPT,
    middleware=[
        inject_memory,
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
