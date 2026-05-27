"""
Phase 2 Step 3: 채팅 API (Chat Endpoint)

목적:
  - 고객의 질문을 받아 Agent에게 전달하고 답변 반환
  - POST /chat 엔드포인트

요청/응답 형식:
  POST /chat
    요청: {
      "message": "환불은 어떻게 해요?",
      "thread_id": "user-session-123",
      "user_id": "customer-456"
    }

    성공 응답: {
      "success": true,
      "message": "Chat completed successfully",
      "data": {
        "response": "환불은 30일 이내에...",
        "thread_id": "user-session-123",
        "status": "completed"
      }
    }

    실패 응답: {
      "success": false,
      "message": "에러 메시지",
      "data": null
    }

thread_id:
  - 같은 thread_id = 같은 대화 세션
  - Phase 2에서는 대화 이력을 저장하지 않으므로 사실상 사용 안 됨
  - Phase 3(Memory)에서 InMemorySaver checkpointer가 thread_id로 대화 이력 관리

user_id:
  - Phase 3 Long-term Memory에서 사용자별 선호도 저장에 사용
  - Phase 2에서는 받기만 하고 활용 안 함
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agent.agent import get_agent

router = APIRouter()


class ChatRequest(BaseModel):
    """
    POST /chat 요청 바디 스키마.

    Pydantic BaseModel:
      - 자동 타입 검증 (message가 없으면 422 에러)
      - 자동 JSON 파싱
      - OpenAPI(Swagger) 문서 자동 생성
    """
    message: str
    thread_id: str = "default"   # 대화 세션 ID (Phase 3에서 활용)
    user_id: str = "anonymous"   # 사용자 ID (Phase 3에서 활용)


@router.post("/chat")
async def chat(request: ChatRequest):
    """
    고객 메시지를 Agent에게 전달하고 답변 반환.

    흐름:
      1. 요청 파싱 (message, thread_id, user_id)
      2. Agent 호출 (search_documents Tool 내부 실행)
      3. 마지막 AI 메시지 추출
      4. 응답 반환

    Args:
        request: ChatRequest (message, thread_id, user_id)

    Returns:
        성공: {"success": true, "data": {"response": "...", ...}}
        실패: {"success": false, "message": "에러 내용"}
    """
    try:
        agent = get_agent()

        # config: LangGraph Agent에 전달하는 실행 설정
        # thread_id로 대화 세션 구분 (Phase 3에서 checkpointer가 이걸 활용)
        config = {"configurable": {"thread_id": request.thread_id}}

        # Agent 비동기 실행
        # messages 형식: [("human", "질문"), ("ai", "답변"), ...]
        result = await agent.invoke(
            {"messages": [("human", request.message)]},
            config=config,
        )

        # result["messages"]: 전체 대화 이력 (질문 + Tool 호출 + 답변)
        # [-1]: 마지막 메시지 = Agent의 최종 답변
        ai_message = result["messages"][-1].content

        return {
            "success": True,
            "message": "Chat completed successfully",
            "data": {
                "response": ai_message,
                "thread_id": request.thread_id,
                "status": "completed",
            }
        }

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": str(e),
                "data": None,
            }
        )
