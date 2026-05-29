"""
Phase 3 Step 2: 장기 기억 주입 미들웨어 (inject_memory)

목적:
  - 사용자의 저장된 선호도(Long-term Memory)를 system prompt에 동적으로 주입
  - create_react_agent의 prompt 파라미터를 callable로 바꿔서 요청마다 다른 system prompt 사용

Phase 2 vs Phase 3 prompt 비교:
  Phase 2: prompt = "당신은 고객 지원 에이전트입니다..."   ← 고정 문자열, 모든 사용자 동일
  Phase 3: prompt = inject_memory                          ← callable, 사용자별 선호도 추가

inject_memory 작동 방식:
  고객 A (user_id="cust-001"):
    store에서 ("user_preferences", "cust-001") 조회
    → "language: 한국어, style: 간결하게" 발견
    → system prompt 끝에 선호도 추가
    → GPT가 자동으로 한국어 + 간결한 스타일로 답변

  고객 B (user_id="cust-002"):
    store에서 ("user_preferences", "cust-002") 조회
    → 저장된 선호도 없음
    → 기본 system prompt만 사용

make_inject_memory 팩토리 패턴:
  store를 파라미터로 받아서 inject_memory를 반환.
  inject_memory가 store를 클로저(closure)로 캡처해서 순환 import 없이 사용 가능.

  순환 import 문제:
    middleware.py → agent.py (store 가져오려고) → middleware.py (inject_memory 가져오려고) → 무한 루프 ❌
  해결:
    agent.py가 store를 만들어서 make_inject_memory(store)로 직접 전달 ✅
"""

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.store.base import BaseStore

# 기본 System Prompt (Phase 2의 _SYSTEM_PROMPT를 여기로 이동)
# inject_memory가 이 문자열 끝에 사용자 선호도를 동적으로 추가함
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
        """
        매 요청마다 호출. user_id로 store를 조회해서 system prompt에 선호도 추가.

        Args:
            state: LangGraph Agent 내부 상태 (state["messages"]로 대화 이력 접근)
            config: 실행 설정 (config["configurable"]["user_id"]로 사용자 식별)

        Returns:
            [SystemMessage(prompt + 선호도)] + 기존 메시지 목록
        """
        user_id = config["configurable"].get("user_id", "anonymous")
        namespace = ("user_preferences", user_id)

        # store에서 해당 사용자의 모든 선호도 조회
        items = store.search(namespace)

        # 선호도가 있으면 system prompt에 추가
        memory_text = ""
        if items:
            preferences = "\n".join(
                f"- {item.key}: {item.value['value']}" for item in items
            )
            memory_text = f"\n\n[사용자 선호도 - 반드시 반영하세요]\n{preferences}"

        system_content = SYSTEM_PROMPT + memory_text

        # SystemMessage를 맨 앞에, 기존 대화 이력은 뒤에
        return [SystemMessage(content=system_content)] + list(state["messages"])

    return inject_memory
