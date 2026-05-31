"""
Before Guardrail → agent.invoke(context=AgentContext(user_id)) → After Guardrail
PII 마스킹은 에이전트 내부 PIIMiddleware가 처리 (입력/출력 모두)

user_id는 context_schema=AgentContext로 선언된 AgentContext를 통해 전달.
thread_id는 checkpointer용으로 config["configurable"]에 전달.
"""

from langchain_core.messages import ToolMessage
from langgraph.types import Command
from fastapi import APIRouter, HTTPException

from agent.agent import get_agent
from agent.context import AgentContext
from agent.middleware import check_hallucination, is_blocked_input
from models.chat import ChatRequest, ConfirmRequest

router = APIRouter()


@router.post("/chat")
async def chat(request: ChatRequest):
    """
    고객 메시지를 미들웨어 파이프라인을 통해 처리하고 안전한 답변을 반환.

    흐름:
      1. Before Guardrail: 욕설 차단 → 차단 시 즉시 반환
      2. Agent 실행 (내부에서 inject_memory, HumanInTheLoopMiddleware, PIIMiddleware 자동 실행)
      2-1. Human-in-the-loop interrupt 감지 → 사용자 본인 확인 요청으로 즉시 반환
      3. 검색 컨텍스트 추출 (search_documents ToolMessage 수집)
      4. After Guardrail: 할루시네이션 검증 (컨텍스트 있을 때만)

    Returns:
        status="completed":             정상 처리
        status="blocked":               Before Guardrail에 의해 차단됨
        status="confirmation_required": 환불 신청 등 → 사용자 본인 확인 필요 (POST /chat/confirm로 재개)
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
        # context:   AgentContext로 user_id 전달 → inject_memory + ToolRuntime에서 사용
        result = await agent.ainvoke(
            {"messages": [("human", request.message)]},
            config={"configurable": {"thread_id": request.thread_id}},
            context=AgentContext(user_id=request.user_id),
        )

        # [2-1] Human-in-the-loop interrupt 감지 (사용자 본인 확인)
        # submit_refund_request 호출 시 HumanInTheLoopMiddleware가 일시정지시킴.
        # 반드시 result["messages"][-1] 접근 전에 분기할 것:
        #   interrupt 시 마지막 메시지는 tool_call을 담은 AIMessage(content 비어있음)이므로
        #   할루시네이션 검증으로 흘러가면 안 됨.
        #
        # 여기서는 관리자 큐에 저장하지 않는다. interrupt 상태는 checkpointer(thread_id)가
        # 들고 있고, 사용자가 /chat/confirm으로 확인/취소하면 그때 재개된다.
        interrupts = result.get("__interrupt__")
        if interrupts:
            # interrupt value = HITLRequest {"action_requests": [...], "review_configs": [...]}
            action = interrupts[0].value["action_requests"][0]
            return {
                "success": True,
                "message": "Confirmation required",
                "data": {
                    "thread_id": request.thread_id,
                    "status": "confirmation_required",
                    "confirmation": {"tool": action["name"], "args": action["args"]},
                },
            }

        # AI가 생성한 최종 답변을 추출 (마지막 메시지의 content)
        # 예: "고객님, 환불은 30일 이내에 가능합니다."
        ai_message = result["messages"][-1].content

        # [3] 검색 컨텍스트 추출
        # Agent 실행 중 여러 tool이 호출될 수 있음 (submit_refund_request, search_documents 등)
        # 이 중에서 search_documents 결과만 필터링하여 리스트로 수집
        # 예: ["문서A 내용...", "문서B 내용..."]
        search_contexts = [
            msg.content
            for msg in result["messages"]
            if isinstance(msg, ToolMessage) and msg.name == "search_documents"
        ]

        # [4] After Guardrail: 할루시네이션 검증
        # AI 답변이 실제 검색된 문서와 일치하는지 확인
        # 검색 결과가 있을 때만 검증 (RAG 기반 답변만 검증)
        if search_contexts:
            # 여러 문서들을 하나의 긴 텍스트로 합침
            combined_context = "\n\n---\n\n".join(search_contexts)
            # AI 답변과 combined_context를 비교해서 거짓 정보가 없는지 검증
            # 할루시네이션 발견 시 GPT-4o-mini가 수정된 답변을 반환
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


@router.post("/chat/confirm")
async def confirm(request: ConfirmRequest):
    """
    사용자 본인이 환불 신청을 확인(approve)하거나 취소(reject)하여 에이전트를 재개한다.

    /chat이 status="confirmation_required"를 반환한 뒤, 같은 thread_id로 호출한다.
    Command(resume=...)로 일시정지된 submit_refund_request 도구의 실행 여부가 결정된다:
      - approve: 도구 실행 → 환불 '신청' 레코드 생성 (status=pending) → 관리자 검토 대기
      - reject:  도구 건너뜀 → 신청하지 않음

    재개 시 context(user_id)를 다시 넘기는 이유:
      재개 후 모델이 한 번 더 호출되며 inject_memory(wrap_model_call)가 user_id를 사용하고,
      submit_refund_request 도구도 runtime.context.user_id로 신청자를 식별한다.

    알려진 한계(학습용):
      user_id를 클라이언트가 다시 보내므로, /chat의 원 요청자와 다른 값을 보내면
      신청이 엉뚱한 사용자로 기록될 수 있다. 프로덕션에서는 thread_id로 원 요청자를
      서버에서 조회하거나 인증 토큰에서 user_id를 도출해야 한다.

    Returns:
        status="submitted": 환불 신청 접수됨 (approve)
        status="cancelled": 환불 신청 취소됨 (reject)
    """
    try:
        agent = get_agent()
        result = await agent.ainvoke(
            Command(resume={"decisions": [{"type": request.decision}]}),
            config={"configurable": {"thread_id": request.thread_id}},
            context=AgentContext(user_id=request.user_id),
        )

        ai_message = result["messages"][-1].content
        status = "submitted" if request.decision == "approve" else "cancelled"
        return {
            "success": True,
            "message": "Confirmation processed successfully",
            "data": {
                "response": ai_message,
                "thread_id": request.thread_id,
                "status": status,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
