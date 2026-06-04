"""
Before Guardrail → agent.invoke(context=AgentContext(user_id)) → After Guardrail
PII 마스킹은 에이전트 내부 PIIMiddleware가 처리 (입력/출력 모두)

user_id는 context_schema=AgentContext로 선언된 AgentContext를 통해 전달.
thread_id는 checkpointer용으로 config["configurable"]에 전달.
"""

import json

from langchain_core.messages import ToolMessage
from langgraph.types import Command  # interrupt된 그래프를 재개할 때 사용
from fastapi import APIRouter, HTTPException
from sse_starlette import EventSourceResponse

from agent.agent import get_agent
from agent.context import AgentContext
from agent.middleware import check_hallucination
from agent.streaming import (
    extract_block_reason,
    extract_interrupt_action,
    is_final_answer_chunk,
    is_search_tool_result,
)
from models.chat import (
    ChatRequest,
    ChatResponse,
    ConfirmRequest,
    ConfirmResponse,
)
from models.common import ErrorResponse

router = APIRouter(tags=["Chat"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        422: {"model": ErrorResponse, "description": "요청 검증 실패 (message 누락 등)"},
        500: {"model": ErrorResponse, "description": "에이전트 처리 중 오류"},
    },
)
async def chat(request: ChatRequest):
    """
    고객 메시지를 미들웨어 파이프라인을 통해 처리하고 안전한 답변을 반환.

    흐름:
      1. Agent 실행 (내부에서 block_inappropriate_input(Before Guardrail), inject_memory,
         HumanInTheLoopMiddleware, PIIMiddleware 자동 실행)
      1-1. Before Guardrail 차단 감지 → 차단 응답으로 즉시 반환
      1-2. Human-in-the-loop interrupt 감지 → 사용자 본인 확인 요청으로 즉시 반환
      2. 검색 컨텍스트 추출 (search_documents ToolMessage 수집)
      3. After Guardrail: 할루시네이션 검증 (컨텍스트 있을 때만)

    Returns:
        status="completed":             정상 처리
        status="blocked":               Before Guardrail(욕설 차단 미들웨어)에 의해 차단됨
        status="confirmation_required": 환불 신청 등 → 사용자 본인 확인 필요 (POST /chat/confirm로 재개)
    """
    try:
        agent = get_agent()

        # [1] Agent 실행
        # 욕설 차단(Before Guardrail)은 이제 에이전트 내부 block_inappropriate_input
        # 미들웨어가 담당한다. 차단 시 모델 호출 없이 단락되며 result["blocked"]=True가 된다.
        # thread_id: checkpointer용 (단기 기억)
        # context:   AgentContext로 user_id 전달 → inject_memory + ToolRuntime에서 사용
        result = await agent.ainvoke(
            {"messages": [("human", request.message)]},
            config={"configurable": {"thread_id": request.thread_id}},
            context=AgentContext(user_id=request.user_id),
        )

        # [1-1] Before Guardrail 차단 감지
        # 미들웨어가 욕설을 차단하면 모델/도구를 건너뛰고 단락하며,
        # state에 blocked=True와 block_reason(거절 메시지)을 남긴다.
        if result.get("blocked"):
            return {
                "data": {
                    "response": result.get("block_reason", ""),
                    "thread_id": request.thread_id,
                    "status": "blocked",
                },
                "isSuccess": True,
                "code": "SUCCESS",
                "message": "Chat completed successfully",
            }

        # [1-2] Human-in-the-loop interrupt 감지 (사용자 본인 확인)
        # submit_refund_request 호출 시 HumanInTheLoopMiddleware가 일시정지시킴.
        # 반드시 result["messages"][-1] 접근 전에 분기할 것:
        #   interrupt 시 마지막 메시지는 tool_call을 담은 AIMessage(content 비어있음)이므로
        #   할루시네이션 검증으로 흘러가면 안 됨.
        #
        # 여기서는 관리자 큐에 저장하지 않는다. interrupt 상태는 checkpointer(thread_id)가
        # 들고 있고, 사용자가 /chat/confirm으로 확인/취소하면 그때 재개된다.
        # interrupts 구조:
        # [
        #   Interrupt(
        #     value={
        #       "action_requests": [
        #         {
        #           "name": "submit_refund_request",
        #           "args": {"order_id": "ORD-123", "amount": 50000, "reason": "불량"},
        #           "description": "도구 설명"
        #         }
        #       ],
        #       "review_configs": [...]
        #     }
        #   )
        # ]
        interrupts = result.get("__interrupt__")
        if interrupts:
            # interrupts[0].value["action_requests"][0] 접근 흐름:
            #   interrupts[0]                         → Interrupt 객체
            #   .value                                → HITLRequest 딕셔너리
            #   ["action_requests"]                   → action 리스트
            #   [0]                                   → 첫 번째 action 딕셔너리
            action = interrupts[0].value["action_requests"][0]
            return {
                "data": {
                    "thread_id": request.thread_id,
                    "status": "confirmation_required",
                    "confirmation": {"tool": action["name"], "args": action["args"]},
                },
                "isSuccess": True,
                "code": "SUCCESS",
                "message": "Confirmation required",
            }

        # AI가 생성한 최종 답변을 추출 (마지막 메시지의 content)
        # 예: "고객님, 환불은 30일 이내에 가능합니다."
        ai_message = result["messages"][-1].content

        # [2] 검색 컨텍스트 추출
        # Agent 실행 중 여러 tool이 호출될 수 있음 (submit_refund_request, search_documents 등)
        # 이 중에서 search_documents 결과만 필터링하여 리스트로 수집
        # 예: ["문서A 내용...", "문서B 내용..."]
        search_contexts = [
            msg.content
            for msg in result["messages"]
            if isinstance(msg, ToolMessage) and msg.name == "search_documents"
        ]

        # [3] After Guardrail: 할루시네이션 검증
        # AI 답변이 실제 검색된 문서와 일치하는지 확인
        # 검색 결과가 있을 때만 검증 (RAG 기반 답변만 검증)
        if search_contexts:
            # 여러 문서들을 하나의 긴 텍스트로 합침
            combined_context = "\n\n---\n\n".join(search_contexts)
            # AI 답변과 combined_context를 비교해서 거짓 정보가 없는지 검증
            # 할루시네이션 발견 시 GPT-4o-mini가 수정된 답변을 반환
            ai_message = check_hallucination(ai_message, combined_context)

        return {
            "data": {
                "response": ai_message,
                "thread_id": request.thread_id,
                "status": "completed",
            },
            "isSuccess": True,
            "code": "SUCCESS",
            "message": "Chat completed successfully",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/chat/confirm",
    response_model=ConfirmResponse,
    responses={
        422: {"model": ErrorResponse, "description": "요청 검증 실패 (thread_id/decision 누락 등)"},
        500: {"model": ErrorResponse, "description": "에이전트 재개 중 오류"},
    },
)
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
        # Command(resume=...): interrupt된 에이전트를 재개
        # - resume: 멈춘 지점부터 다시 시작
        # - decisions: HumanInTheLoopMiddleware로 사용자의 선택 전달
        #   ├─ "approve": submit_refund_request 실행 → 신청 접수
        #   └─ "reject": 도구 건너뜀 → 신청하지 않음
        #
        # thread_id: 멈춘 상태를 checkpointer에서 조회 (어느 대화에서 멈췄는지)
        # context: user_id 다시 전달 (inject_memory + tool에서 사용)
        result = await agent.ainvoke(
            Command(resume={"decisions": [{"type": request.decision}]}),
            config={"configurable": {"thread_id": request.thread_id}},
            context=AgentContext(user_id=request.user_id),
        )

        ai_message = result["messages"][-1].content
        status = "submitted" if request.decision == "approve" else "cancelled"
        return {
            "data": {
                "response": ai_message,
                "thread_id": request.thread_id,
                "status": status,
            },
            "isSuccess": True,
            "code": "SUCCESS",
            "message": "Confirmation processed successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/chat/stream",
    response_class=EventSourceResponse,
    responses={
        200: {
            "description": "SSE stream. 이벤트 목록: token | message | blocked | confirmation_required | done | error",
            "content": {
                "text/event-stream": {
                    "schema": {
                        "type": "string",
                        "example": (
                            "event: token\ndata: {\"content\": \"안녕하세요\"}\n\n"
                            "event: done\ndata: {\"thread_id\": \"abc\", \"status\": \"completed\"}\n\n"
                        ),
                    }
                }
            },
        },
        422: {
            "model": ErrorResponse,
            "description": "요청 검증 실패 (message 누락 등). 스트림 시작 전 발생.",
        },
    },
)
async def chat_stream(request: ChatRequest):
    """고객 메시지를 SSE로 스트리밍 처리한다.

    단일 엔드포인트가 agent.astream 을 관찰하며 내부 분기한다:
      - 욕설 차단      → event:blocked 후 종료
        (에이전트 내부 block_inappropriate_input 미들웨어가 단락 → updates 스트림에서 감지)
      - 일반 답변      → event:token 으로 토큰 실시간 전송
      - RAG 답변(검색) → 토큰 버퍼링 → 할루시네이션 검사본을 event:message 1회 전송
      - 환불 interrupt → event:confirmation_required 후 종료 (재개는 기존 POST /chat/confirm)
    종료 시 event:done, 오류 시 event:error.

    학습용 한계(설계 문서 기재): 스트리밍된 token 은 PIIMiddleware 출력 마스킹과
    할루시네이션 검사 '이전' 단계다. 출력 PII 마스킹·할루시네이션 교정의 완전한 보장은
    비스트리밍 POST /chat 경로에서만 이뤄진다. 입력 마스킹(apply_to_input)에 의존한다.

    이벤트 프로토콜 (data는 모두 JSON 문자열):
      token                 {"content": "..."}
      message               {"response": "...", "thread_id": "...", "status": "completed"}
      blocked               {"response": "...", "thread_id": "..."}
      confirmation_required {"thread_id": "...", "tool": "...", "args": {...}}
      done                  {"thread_id": "...", "status": "completed"}
      error                 {"detail": "..."}
    """

    async def event_generator():
        try:
            agent = get_agent()
            config = {"configurable": {"thread_id": request.thread_id}}

            used_search = False          # search_documents 사용 여부
            search_contexts: list[str] = []  # 할루시네이션 검사용 검색 컨텍스트
            answer_buffer: list[str] = []    # 검색 사용 시 최종 답변 토큰 버퍼
            interrupt_action = None          # 환불 interrupt action {name,args}
            blocked_reason = None            # Before Guardrail 차단 사유

            # [1] astream 으로 실행하며 관찰
            # 욕설 차단(Before Guardrail)은 에이전트 내부 미들웨어가 담당하므로,
            # updates 스트림에서 blocked 신호를 감지한다 (라우터 선검사 불필요).
            # stream_mode=["updates","messages"]: 토큰(messages) + 차단/interrupt(updates) 동시 수신
            async for mode, payload in agent.astream(
                {"messages": [("human", request.message)]},
                config=config,
                context=AgentContext(user_id=request.user_id),
                stream_mode=["updates", "messages"],
            ):
                if mode == "updates":
                    reason = extract_block_reason(payload)
                    if reason is not None:
                        blocked_reason = reason
                        break  # 욕설 차단 → 스트림 중단
                    action = extract_interrupt_action(payload)
                    if action is not None:
                        interrupt_action = action
                        break  # 환불 본인 확인 필요 → 스트림 중단
                elif mode == "messages":
                    chunk, metadata = payload
                    if is_search_tool_result(chunk):
                        used_search = True
                        search_contexts.append(chunk.content)
                    elif is_final_answer_chunk(chunk, metadata):
                        if used_search:
                            # RAG 답변: 흘리지 않고 버퍼링 (검사 후 한 번에 전송)
                            answer_buffer.append(chunk.content)
                        else:
                            # 일반 답변: 토큰 실시간 전송
                            yield {
                                "event": "token",
                                "data": json.dumps(
                                    {"content": chunk.content}, ensure_ascii=False
                                ),
                            }

            # [2] 스트림 종료 후 분기
            if blocked_reason is not None:
                yield {
                    "event": "blocked",
                    "data": json.dumps(
                        {"response": blocked_reason, "thread_id": request.thread_id},
                        ensure_ascii=False,
                    ),
                }
                return

            if interrupt_action is not None:
                yield {
                    "event": "confirmation_required",
                    "data": json.dumps(
                        {
                            "thread_id": request.thread_id,
                            "tool": interrupt_action["name"],
                            "args": interrupt_action["args"],
                        },
                        ensure_ascii=False,
                    ),
                }
                return

            if used_search and answer_buffer:
                # RAG 답변: 검색 컨텍스트로 할루시네이션 검사 후 완성본 전송
                # answer_buffer가 비어 있으면(검색만 하고 최종 답변 토큰 없음) 검사를 건너뛰고
                # 아래 done 이벤트로 흘려보냄 (빈 message 방지)
                combined_context = "\n\n---\n\n".join(search_contexts)
                answer = "".join(answer_buffer)
                checked = check_hallucination(answer, combined_context)
                yield {
                    "event": "message",
                    "data": json.dumps(
                        {
                            "response": checked,
                            "thread_id": request.thread_id,
                            "status": "completed",
                        },
                        ensure_ascii=False,
                    ),
                }

            yield {
                "event": "done",
                "data": json.dumps(
                    {"thread_id": request.thread_id, "status": "completed"},
                    ensure_ascii=False,
                ),
            }

        except Exception as e:
            # 스트림 시작 후에는 상태코드 변경 불가 → error 이벤트로 전달
            yield {
                "event": "error",
                "data": json.dumps({"detail": str(e)}, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())
