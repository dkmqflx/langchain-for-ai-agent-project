"""
Phase 4 수정: PII + Guardrail 미들웨어 파이프라인 통합

Phase 3 → Phase 4 변화:
  Phase 3:
    입력 → Agent → 응답
    (안전 장치 없음)

  Phase 4:
    입력 PII 마스킹
      → Before Guardrail (욕설 차단, 에이전트 실행 전 단락)
      → Agent 실행
      → 검색 컨텍스트 추출 (ToolMessage에서 search_documents 결과 수집)
      → After Guardrail (할루시네이션 검증, 컨텍스트 있을 때만)
      → 출력 PII 마스킹
      → 응답

검색 컨텍스트 추출 방식:
  agent.invoke() 결과의 result["messages"]를 순회하여
  ToolMessage 중 name="search_documents"인 것의 content를 모두 수집.
  에이전트가 여러 번 검색해도 전부 반영됨.
  모듈 레벨 dict 대신 이 방식을 쓰는 이유:
    - 상태 없음 → 메모리 누수, 동시 요청 레이스 컨디션 없음
    - 별도 cleanup 불필요

Before Guardrail가 단락(short-circuit)해야 하는 이유:
  차단 대상 메시지를 에이전트에 넘기면:
    - GPT API 비용 낭비
    - 욕설이 checkpointer에 저장되어 다음 대화에서 LLM이 볼 수 있음
  → 차단 시 agent.invoke() 호출 전에 즉시 반환
"""

from langchain_core.messages import ToolMessage
from fastapi import APIRouter, HTTPException

from agent.agent import get_agent
from agent.middleware import check_hallucination, is_blocked_input, mask_pii
from models.chat import ChatRequest

router = APIRouter()


@router.post("/chat")
async def chat(request: ChatRequest):
    """
    고객 메시지를 미들웨어 파이프라인을 통해 처리하고 안전한 답변을 반환.

    흐름:
      1. PII 마스킹 (입력)
      2. Before Guardrail: 욕설 차단 → 차단 시 즉시 반환
      3. Agent 실행
      4. 검색 컨텍스트 추출 (search_documents ToolMessage 수집)
      5. After Guardrail: 할루시네이션 검증 (컨텍스트 있을 때만)
      6. PII 마스킹 (출력)

    Returns:
        status="completed": 정상 처리
        status="blocked":   Before Guardrail에 의해 차단됨
    """
    try:
        # [1] 입력 PII 마스킹
        # 마스킹 후 텍스트가 checkpointer에 저장되므로 PII가 단기 기억에 남지 않음
        clean_message = mask_pii(request.message)

        # [2] Before Guardrail: 욕설/부적절 콘텐츠 차단
        # agent.invoke() 호출 전에 단락하여 불필요한 API 비용 방지
        blocked, reason = is_blocked_input(clean_message)
        if blocked:
            return {
                "success": True,
                "message": "Chat completed successfully",
                "data": {
                    "response": reason,
                    "thread_id": request.thread_id,
                    "status": "blocked",
                },
            }

        agent = get_agent()
        config = {
            "configurable": {
                "thread_id": request.thread_id,
                "user_id": request.user_id,
            }
        }

        # [3] Agent 실행
        result = await agent.invoke(
            {"messages": [("human", clean_message)]},
            config=config,
        )

        ai_message = result["messages"][-1].content

        # [4] 검색 컨텍스트 추출
        # search_documents가 여러 번 호출된 경우 모든 결과를 합침
        search_contexts = [
            msg.content
            for msg in result["messages"]
            if isinstance(msg, ToolMessage) and msg.name == "search_documents"
        ]

        # [5] After Guardrail: 할루시네이션 검증
        # 컨텍스트가 없으면 (문서 검색 없이 답변) 검증 생략
        # 검증 없이 건너뛰는 이유: 검색 컨텍스트 없이 판정하면 정상 답변을 HALLUCINATION으로 오탐
        if search_contexts:
            combined_context = "\n\n---\n\n".join(search_contexts)
            ai_message = check_hallucination(ai_message, combined_context)

        # [6] 출력 PII 마스킹
        # 에이전트가 입력에서 PII를 그대로 반복하는 경우 대비
        ai_message = mask_pii(ai_message)

        return {
            "success": True,
            "message": "Chat completed successfully",
            "data": {
                "response": ai_message,
                "thread_id": request.thread_id,
                "status": "completed",
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
