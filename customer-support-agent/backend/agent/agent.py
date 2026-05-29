"""
Phase 4 수정: create_react_agent → create_agent

create_react_agent (구):
  - prompt=callable로 동적 system prompt 주입
  - InjectedStore + RunnableConfig으로 도구에서 store/config 접근
  - middleware 파라미터 없음 → PIIMiddleware 사용 불가

create_agent (신):
  - system_prompt=정적 문자열, 동적 주입은 middleware로
  - ToolRuntime[AgentContext]로 도구에서 store/context 접근
  - middleware=[] 파라미터로 PIIMiddleware 등 공식 미들웨어 사용 가능
  - context_schema=AgentContext → invoke 시 context=AgentContext(...) 전달

미들웨어 실행 순서 (에이전트 내부):
  before_model 순서: InjectMemoryMiddleware → PIIMiddleware(email) → PIIMiddleware(card)
  after_model 순서:  PIIMiddleware(card) → PIIMiddleware(email) → InjectMemoryMiddleware(없음)

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
from agent.middleware import SYSTEM_PROMPT, InjectMemoryMiddleware
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
        InjectMemoryMiddleware(),
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
