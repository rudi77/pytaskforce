import structlog

from taskforce.core.domain.lean_agent_components.message_history_manager import (
    MessageHistoryManager,
)
from taskforce.core.domain.token_budgeter import TokenBudgeter


class _DummyLLM:
    async def complete(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("LLM should not be called in this unit test")


def _make_manager() -> MessageHistoryManager:
    return MessageHistoryManager(
        token_budgeter=TokenBudgeter(
            max_input_tokens=10_000,
            compression_trigger=9_000,
        ),
        openai_tools=[],
        llm_provider=_DummyLLM(),
        model_alias="main",
        summary_threshold=20,
        logger=structlog.get_logger(__name__),
    )


def test_deterministic_compression_preserves_tool_call_pair() -> None:
    """
    Regression test: trimming must not keep a tool message without its matching
    assistant.tool_calls message (Azure/OpenAI rejects that payload).
    """
    manager = _make_manager()

    messages = [{"role": "system", "content": "sys"}]
    # Old filler to push the tool call pair across the boundary.
    for i in range(25):
        messages.append({"role": "user", "content": f"u{i}"})
        messages.append({"role": "assistant", "content": f"a{i}"})

    # Tool call pair that will be near the end.
    tool_call_id = "call_123"
    messages.append(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": tool_call_id, "type": "function", "function": {"name": "x", "arguments": "{}"}}
            ],
        }
    )
    messages.append(
        {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": "x",
            "content": '{"success": true}',
        }
    )
    # More recent messages that should be kept.
    for i in range(12):
        messages.append({"role": "user", "content": f"tail_u{i}"})

    compressed = manager.deterministic_compression(messages)

    # If tool message is present, the matching assistant tool_calls message must also be present.
    tool_indexes = [i for i, m in enumerate(compressed) if m.get("role") == "tool"]
    for tool_idx in tool_indexes:
        tool_msg = compressed[tool_idx]
        tool_id = tool_msg.get("tool_call_id")
        assert tool_id, "tool message missing tool_call_id"
        assert any(
            m.get("role") == "assistant"
            and any(tc.get("id") == tool_id for tc in (m.get("tool_calls") or []))
            for m in compressed[:tool_idx]
        ), "tool message has no preceding matching assistant.tool_calls"


