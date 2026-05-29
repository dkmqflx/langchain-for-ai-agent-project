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

thread_id (프론트에서 계속 같은 값을 보내야 함):
  - 같은 thread_id = 같은 대화 세션
  - InMemorySaver checkpointer가 thread_id로 대화 이력 관리 (단기 기억)
  - 프론트가 thread_id를 변경하면 새로운 대화 세션 시작
  - 예) "아까 말한 주문번호" → checkpointer가 이전 메시지에서 찾아줌

user_id:
  - Phase 3: InMemoryStore가 user_id로 사용자 선호도 저장/조회 (장기 기억)
  - inject_memory가 config["configurable"]["user_id"]로 store를 조회해 prompt에 반영
  - 예) "한국어로만 답변해줘" 저장 → 새 thread에서도 자동 반영
"""

from fastapi import APIRouter, HTTPException

from agent.agent import get_agent
from models.chat import ChatRequest

router = APIRouter()


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
        # thread_id: checkpointer가 대화 세션 구분에 사용 (단기 기억)
        # user_id:   inject_memory와 memory tools가 사용자 선호도 조회에 사용 (장기 기억)
        config = {
            "configurable": {
                "thread_id": request.thread_id,
                "user_id": request.user_id,
            }
        }

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
        raise HTTPException(status_code=500, detail=str(e))
