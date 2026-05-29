"""
Phase 3 수정: checkpointer(단기 기억) + store(장기 기억) 추가

Phase 2 → Phase 3 변화:
  Phase 2:
    create_react_agent(model, tools, prompt="고정 문자열")
    → 대화 기억 없음, 모든 사용자에게 동일한 prompt

  Phase 3:
    create_react_agent(model, tools, prompt=inject_memory, checkpointer=..., store=...)
    → 단기 기억: 같은 thread_id면 이전 대화 기억
    → 장기 기억: user_id로 저장된 선호도를 prompt에 자동 반영

단기 기억 (InMemorySaver / checkpointer):
  비유: 상담사의 메모장
    상담사가 고객과 대화하면서 메모를 남김.
    같은 고객(thread_id)이 다시 말하면 메모를 보고 이전 내용 기억.
    새 고객(다른 thread_id)이 오면 새 메모장 시작.

  동작:
    thread_id="session-1": [질문1, 답변1, 질문2, 답변2, ...] → checkpointer에 저장
    thread_id="session-1": 다음 질문 → checkpointer에서 이전 대화 로드 → 이어서 답변

장기 기억 (InMemoryStore / store):
  비유: 고객 프로필 카드
    상담사가 고객의 선호도를 카드에 기록해 보관함.
    다음번 전화(새 thread_id)에서도 카드를 꺼내 보고 선호도 반영.

  동작:
    user_id="cust-001": save_user_preference("language", "한국어") → store에 저장
    새 대화(다른 thread_id): inject_memory가 store 조회 → "한국어" 선호도를 prompt에 추가

싱글톤으로 유지해야 하는 이유:
  checkpointer와 store는 앱 생명주기 동안 하나만 존재해야 함.
  요청마다 새로 만들면 저장된 상태가 초기화됨.
"""

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import create_react_agent
from langgraph.store.memory import InMemoryStore

from agent.middleware import make_inject_memory
from agent.tools import get_user_preferences, save_user_preference, search_documents

# [1] LLM 설정 (Phase 2와 동일)
_llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0,
    streaming=True,
)

# [2] 단기 기억 (Short-term Memory)
# thread_id 기반으로 대화 이력을 체크포인트에 저장
# 같은 thread_id: 이전 메시지 이어받음
# 다른 thread_id: 새 대화 시작
_checkpointer = InMemorySaver()

# [3] 장기 기억 (Long-term Memory)
# user_id 기반으로 사용자 선호도 저장
# thread_id가 달라도 (새 대화여도) user_id가 같으면 선호도 유지
_store = InMemoryStore()

# [4] ReAct Agent 생성
# prompt: 고정 문자열 → callable (inject_memory)로 변경
#   매 요청마다 호출되어 user_id로 장기 기억 조회 후 system prompt에 주입
# checkpointer: 단기 기억 저장소 주입
# store: 장기 기억 저장소 주입 (tools의 InjectedStore에서도 접근)
_agent = create_react_agent(
    model=_llm,
    tools=[search_documents, save_user_preference, get_user_preferences],
    prompt=make_inject_memory(_store),
    checkpointer=_checkpointer,
    store=_store,
)


def get_agent():
    """
    Agent 인스턴스 반환 (모듈 레벨 싱글톤).

    Returns:
        CompiledGraph: checkpointer + store가 연결된 LangGraph ReAct Agent
    """
    return _agent
