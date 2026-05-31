"""스트리밍 분기를 위한 순수 판별 함수.

POST /chat/stream 이 agent.astream(stream_mode=["updates","messages"]) 스트림을
관찰하며 사용한다. I/O·네트워크 없음 → 단위 테스트 대상.

판별 근거 (langgraph 1.2.2 설치본 probe 확인):
  - messages 모드 payload = (message_chunk, metadata)
  - 최종 답변 토큰: AIMessageChunk, langgraph_node=="model", tool_call_chunks 비어있음, content 있음
  - 도구 호출 청크: content="", tool_call_chunks 비어있지 않음 → 최종 답변 아님
  - search_documents 결과: ToolMessage(name="search_documents")
  - 환불 interrupt: updates payload["__interrupt__"][0].value["action_requests"][0]
"""

from langchain_core.messages import AIMessageChunk, ToolMessage


def is_final_answer_chunk(chunk, metadata) -> bool:
    """이 청크가 사용자에게 보여줄 '최종 답변' 토큰인지 판별.

    도구 호출용 AIMessageChunk(content 비고 tool_call_chunks 있음)와
    중간 노드 출력은 제외한다.
    """
    return (
        isinstance(chunk, AIMessageChunk)
        and metadata.get("langgraph_node") == "model"
        and not chunk.tool_call_chunks
        and bool(chunk.content)
    )


def is_search_tool_result(chunk) -> bool:
    """search_documents 도구 결과(ToolMessage)인지 판별 (RAG 컨텍스트 수집용)."""
    return isinstance(chunk, ToolMessage) and chunk.name == "search_documents"


def extract_interrupt_action(update_payload):
    """updates 모드 payload에서 환불 interrupt action을 추출.

    Returns:
        {"name", "args", "description"} 딕셔너리, 또는 interrupt가 없으면 None.
    """
    interrupts = update_payload.get("__interrupt__")
    if not interrupts:
        return None
    return interrupts[0].value["action_requests"][0]
