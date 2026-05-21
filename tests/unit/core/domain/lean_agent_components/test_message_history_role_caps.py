"""Role-aware hard caps on individual messages.

Long tool-role messages (raw search snippets, fetched HTML) are the
primary source of message-log bloat across multi-turn research
sessions. The MessageHistoryManager caps them per-role before falling
through to the more expensive LLM-based summarisation. These tests
pin the cap behaviour and the fact that tool/assistant caps are
independently tunable.
"""

from __future__ import annotations

import pytest
import structlog

from taskforce.core.domain.lean_agent_components.message_history_manager import (
    MessageHistoryManager,
)
from taskforce.core.domain.token_budgeter import TokenBudgeter


class _DummyLLM:
    async def complete(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("LLM should not be called in this unit test")


def _make_manager(
    *,
    tool_message_max_chars: int | None = None,
    assistant_message_max_chars: int | None = None,
) -> MessageHistoryManager:
    return MessageHistoryManager(
        token_budgeter=TokenBudgeter(
            logger=structlog.get_logger(__name__),
            max_input_tokens=10_000,
            compression_trigger=9_000,
        ),
        openai_tools=[],
        llm_provider=_DummyLLM(),
        model_alias="main",
        summary_threshold=20,
        logger=structlog.get_logger(__name__),
        tool_message_max_chars=tool_message_max_chars,
        assistant_message_max_chars=assistant_message_max_chars,
    )


@pytest.mark.spec("context-manager.role_caps_truncate_with_marker")
def test_tool_message_truncated_at_cap() -> None:
    """An oversized tool message is hard-capped with a truncation marker."""
    manager = _make_manager(tool_message_max_chars=100)

    long_tool_content = "snippet " * 200  # >> 100 chars
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "ask"},
        {"role": "tool", "content": long_tool_content, "name": "web_search"},
    ]

    capped = manager.cap_oversized_messages(messages)

    assert capped[2]["role"] == "tool"
    capped_content = capped[2]["content"]
    assert len(capped_content) < len(long_tool_content)
    assert "[truncated" in capped_content


def test_short_tool_message_passes_through_unchanged() -> None:
    """Tool messages within budget are not modified."""
    manager = _make_manager(tool_message_max_chars=200)

    short = "compact result"
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "tool", "content": short, "name": "web_search"},
    ]

    capped = manager.cap_oversized_messages(messages)

    assert capped[1]["content"] == short


@pytest.mark.spec("context-manager.role_caps_truncate_with_marker")
def test_assistant_cap_is_independent_of_tool_cap() -> None:
    """Tool and assistant caps apply independently."""
    manager = _make_manager(
        tool_message_max_chars=50,
        assistant_message_max_chars=10_000,
    )

    short_assistant = "short reasoning text"
    long_tool_content = "x" * 500
    messages = [
        {"role": "assistant", "content": short_assistant},
        {"role": "tool", "content": long_tool_content},
    ]

    capped = manager.cap_oversized_messages(messages)

    # Assistant left alone (fits its own cap)
    assert capped[0]["content"] == short_assistant
    # Tool truncated
    assert "[truncated" in capped[1]["content"]


def test_input_messages_are_not_mutated() -> None:
    """``cap_oversized_messages`` returns a new list and does not mutate input."""
    manager = _make_manager(tool_message_max_chars=20)

    original = "y" * 200
    messages = [{"role": "tool", "content": original}]

    capped = manager.cap_oversized_messages(messages)

    # Original dict is untouched.
    assert messages[0]["content"] == original
    # Capped is a new dict.
    assert capped[0] is not messages[0]
    assert "[truncated" in capped[0]["content"]


@pytest.mark.spec("context-manager.role_caps_truncate_with_marker")
def test_zero_cap_disables_truncation() -> None:
    """A cap of ``0`` disables truncation for that role (escape hatch)."""
    manager = _make_manager(tool_message_max_chars=0)

    long_tool = "z" * 5000
    messages = [{"role": "tool", "content": long_tool}]

    capped = manager.cap_oversized_messages(messages)

    assert capped[0]["content"] == long_tool
