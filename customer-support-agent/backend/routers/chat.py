"""
Before Guardrail → agent.invoke(context=AgentContext(user_id)) → After Guardrail
PII 마스킹은 에이전트 내부 PIIMiddleware가 처리 (입력/출력 모두)

user_id는 context_schema=AgentContext로 선언된 AgentContext를 통해 전달.
thread_id는 checkpointer용으로 config["configurable"]에 전달.
"""

from langchain_core.messages import ToolMessage
from fastapi import APIRouter, HTTPException

from agent.agent import get_agent
from agent.context import AgentContext
from agent.middleware import check_hallucination, is_blocked_input
from models.chat import ChatRequest

router = APIRouter()


@router.post("/chat")
async def chat(request: ChatRequest):
    """
    고객 메시지를 미들웨어 파이프라인을 통해 처리하고 안전한 답변을 반환.

    흐름:
      1. Before Guardrail: 욕설 차단 → 차단 시 즉시 반환
      2. Agent 실행 (내부에서 PIIMiddleware, InjectMemoryMiddleware 자동 실행)
      3. 검색 컨텍스트 추출 (search_documents ToolMessage 수집)
      4. After Guardrail: 할루시네이션 검증 (컨텍스트 있을 때만)

    Returns:
        status="completed": 정상 처리
        status="blocked":   Before Guardrail에 의해 차단됨
    """
    try:
        # [1] Before Guardrail: 욕설/부적절 콘텐츠 차단
        blocked, reason = is_blocked_input(request.message)
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

        # [2] Agent 실행
        # thread_id: checkpointer용 (단기 기억)
        # context:   AgentContext로 user_id 전달 → InjectMemoryMiddleware + ToolRuntime에서 사용
        result = await agent.invoke(
            {"messages": [("human", request.message)]},
            config={"configurable": {"thread_id": request.thread_id}},
            context=AgentContext(user_id=request.user_id),
        )

        ai_message = result["messages"][-1].content

        # [3] 검색 컨텍스트 추출
        search_contexts = [
            msg.content
            for msg in result["messages"]
            if isinstance(msg, ToolMessage) and msg.name == "search_documents"
        ]

        # [4] After Guardrail: 할루시네이션 검증
        if search_contexts:
            combined_context = "\n\n---\n\n".join(search_contexts)
            ai_message = check_hallucination(ai_message, combined_context)

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
