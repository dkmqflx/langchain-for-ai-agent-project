"""agent/streaming.py 순수 판별 함수 테스트 (네트워크/DB 불필요).

실행 (backend 디렉토리에서):
  uv run pytest tests/test_streaming.py -v
"""
from langchain_core.messages import AIMessageChunk, ToolMessage
from langgraph.types import Interrupt

from agent.streaming import (
    extract_block_reason,
    extract_interrupt_action,
    is_final_answer_chunk,
    is_search_tool_result,
)


# --- is_final_answer_chunk ---
def test_text_chunk_from_model_is_final():
    chunk = AIMessageChunk(content="환불은 ")
    assert is_final_answer_chunk(chunk, {"langgraph_node": "model"}) is True


def test_tool_call_chunk_is_not_final():
    chunk = AIMessageChunk(
        content="",
        tool_call_chunks=[{
            "name": "submit_refund_request", "args": "{}",
            "id": "call_1", "index": 0, "type": "tool_call_chunk",
        }],
    )
    assert is_final_answer_chunk(chunk, {"langgraph_node": "model"}) is False


def test_empty_content_is_not_final():
    chunk = AIMessageChunk(content="")
    assert is_final_answer_chunk(chunk, {"langgraph_node": "model"}) is False


def test_non_model_node_is_not_final():
    chunk = AIMessageChunk(content="hi")
    assert is_final_answer_chunk(chunk, {"langgraph_node": "tools"}) is False


def test_tool_message_is_not_final():
    tm = ToolMessage(content="문서", name="search_documents", tool_call_id="c1")
    assert is_final_answer_chunk(tm, {"langgraph_node": "tools"}) is False


# --- is_search_tool_result ---
def test_search_documents_toolmessage():
    tm = ToolMessage(content="문서내용", name="search_documents", tool_call_id="c1")
    assert is_search_tool_result(tm) is True


def test_other_tool_is_not_search():
    tm = ToolMessage(content="ok", name="submit_refund_request", tool_call_id="c2")
    assert is_search_tool_result(tm) is False


def test_ai_chunk_is_not_search():
    assert is_search_tool_result(AIMessageChunk(content="x")) is False


# --- extract_interrupt_action ---
def test_extracts_first_action():
    itr = Interrupt(value={
        "action_requests": [{
            "name": "submit_refund_request",
            "args": {"order_id": "ORD-1", "amount": 5000},
            "description": "d",
        }],
        "review_configs": [],
    })
    action = extract_interrupt_action({"__interrupt__": (itr,)})
    assert action["name"] == "submit_refund_request"
    assert action["args"]["order_id"] == "ORD-1"
    assert action["description"] == "d"


def test_no_interrupt_returns_none():
    assert extract_interrupt_action({"model": {"messages": []}}) is None


# --- extract_block_reason ---
# updates payload 구조는 probe로 확인: {노드이름: {jump_to, blocked, block_reason, messages}}
def test_extracts_block_reason():
    payload = {
        "block_inappropriate_input.before_agent": {
            "jump_to": "end",
            "blocked": True,
            "block_reason": "부적절한 언어가 포함되어 있어 처리할 수 없습니다. 다시 문의해 주세요.",
            "messages": [],
        }
    }
    assert extract_block_reason(payload) == (
        "부적절한 언어가 포함되어 있어 처리할 수 없습니다. 다시 문의해 주세요."
    )


def test_no_block_returns_none():
    assert extract_block_reason({"model": {"messages": []}}) is None


def test_block_false_returns_none():
    # blocked 키가 있어도 falsy면 차단 아님
    assert extract_block_reason({"model": {"blocked": False}}) is None
