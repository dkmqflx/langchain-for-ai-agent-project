"""
Phase 2 Step 2: ReAct Agent 설정

목적:
  - 고객 질문을 받아 search_documents Tool을 사용해 답변하는 Agent 생성
  - LangGraph의 create_react_agent 사용

ReAct(Reasoning + Acting) 패턴:
  1. Reasoning: "이 질문에 답하려면 문서를 검색해야겠다"
  2. Acting:    search_documents("환불 정책") 실행
  3. Reasoning: "검색 결과에 이런 내용이 있다. 이걸 바탕으로 답변하자"
  4. Acting:    최종 답변 반환

  예시:
    고객: "환불은 어떻게 해요?"
    Agent 사고:
      1. 환불 정책 문서를 검색해야겠다
      2. search_documents("환불 신청 방법") 호출
      3. "환불은 30일 이내에..." 결과 획득
      4. "고객님, 환불은 30일 이내에 신청 가능합니다..." 답변

create_react_agent:
  - LangGraph의 미리 만들어진 ReAct Agent
  - tools 리스트에 있는 도구를 자동으로 호출
  - Phase 2: checkpointer/store 없이 기본 구성 (Phase 3에서 추가)

Phase별 Agent 변화:
  Phase 2: create_react_agent(model, tools, prompt)         ← 현재
  Phase 3: checkpointer + store 추가 (대화 기억)
  Phase 4: middleware 추가 (PII, Guardrail)
  Phase 5: process_refund tool 추가 (Human-in-the-loop)
"""

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from agent.tools import search_documents

# [1] LLM 설정
# temperature=0: 창의적인 답변보다 일관된 정확한 답변 (고객 지원에 적합)
# streaming=True: 답변을 토큰 단위로 스트리밍 (Phase 6에서 활용)
_llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0,
    streaming=True,
)

# [2] System Prompt
# Agent의 역할과 행동 방식을 정의
# 문서에 없는 내용은 모른다고 답변하도록 명시 (할루시네이션 방지)
_SYSTEM_PROMPT = """당신은 B2B SaaS 고객 지원 에이전트입니다.

역할:
  - 고객의 질문에 친절하고 정확하게 답변하세요.
  - 답변은 반드시 업로드된 회사 문서를 기반으로 하세요.
  - 문서에 없는 내용은 "관련 정보를 문서에서 찾을 수 없습니다."라고 답변하세요.

도구 사용:
  - 고객 질문에 답변하기 전에 항상 search_documents 도구로 관련 문서를 먼저 검색하세요.
  - 검색 결과가 없으면 문서에 관련 내용이 없다고 안내하세요.
"""

# [3] ReAct Agent 생성
# tools=[search_documents]: 이 도구만 사용 가능 (Phase 5에서 process_refund 추가)
# Phase 2: checkpointer 없음 → 대화 이력 저장 안 됨 (Phase 3에서 추가)
_agent = create_react_agent(
    model=_llm,
    tools=[search_documents],
    prompt=_SYSTEM_PROMPT,
)


def get_agent():
    """
    Agent 인스턴스 반환 (모듈 레벨 싱글톤).

    매 요청마다 새 Agent를 만들지 않고 같은 인스턴스 재사용.

    Returns:
        CompiledGraph: LangGraph로 컴파일된 ReAct Agent
    """
    return _agent
