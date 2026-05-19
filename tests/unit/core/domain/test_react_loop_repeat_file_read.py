from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.enums import MessageRole
from taskforce.core.domain.planning import _react_loop


def _make_agent(max_steps: int = 5) -> MagicMock:
    agent = MagicMock()
    agent.max_steps = max_steps
    agent.max_parallel_tools = 1
    agent._openai_tools = [
        {"type": "function", "function": {"name": "file_read"}}
    ]
    agent._planner = None
    agent.planner = None
    agent.tools = {}
    agent.state_manager = AsyncMock()
    agent.state_store = AsyncMock()
    agent.record_heartbeat = AsyncMock()
    agent.tool_result_message_factory = MagicMock()
    agent.tool_result_message_factory.build_messages = AsyncMock(
        return_value=[
            {"role": "tool", "tool_call_id": "call", "content": "result"}
        ]
    )
    agent._execute_tool = AsyncMock(
        return_value={
            "success": True,
            "path": "D:\\cases\\mail.eml",
            "content": "mail content",
            "size": 12,
        }
    )

    messages: list[dict[str, Any]] = []
    context = MagicMock()
    context.messages = messages
    context.append_message = MagicMock(
        side_effect=lambda m: messages.append(m)
    )
    context.prepare_for_llm = AsyncMock()
    agent.context = context
    agent._sub_agent_event_sink = None
    return agent


def _make_logger() -> MagicMock:
    logger = MagicMock()
    for level in ("debug", "info", "warning", "error"):
        setattr(logger, level, MagicMock())
    return logger


@pytest.mark.asyncio
async def test_repeat_file_read_injects_cache_nudge() -> None:
    agent = _make_agent()
    logger = _make_logger()
    calls = [
        {
            "id": "call-1",
            "type": "function",
            "function": {
                "name": "file_read",
                "arguments": '{"path":"D:\\\\cases\\\\mail.eml"}',
            },
        },
        {
            "id": "call-2",
            "type": "function",
            "function": {
                "name": "file_read",
                "arguments": '{"path":"d:/cases/mail.eml"}',
            },
        },
    ]
    call_count = 0

    async def fake_complete(**_: Any) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return {
                "success": True,
                "tool_calls": [calls[call_count - 1]],
                "content": "",
            }
        return {"success": True, "tool_calls": None, "content": "Done."}

    agent.llm_provider = MagicMock()
    agent.llm_provider.complete = AsyncMock(side_effect=fake_complete)
    if hasattr(agent.llm_provider, "complete_stream"):
        del agent.llm_provider.complete_stream

    mission = "Read the mail once and write the draft."
    messages = agent.context.messages
    messages.extend(
        [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": mission},
        ]
    )
    state: dict[str, Any] = {}

    async for _ in _react_loop(
        agent, mission, "sess-repeat", messages, state, 0, logger
    ):
        pass

    nudges = [
        message
        for message in messages
        if message.get("role") == MessageRole.USER.value
        and "already read this file" in message.get("content", "").lower()
    ]
    assert len(nudges) == 1
    assert "d:/cases/mail.eml" in nudges[0]["content"]
    assert "d:/cases/mail.eml" in state["evidence_cache"]
    assert state["file_read_metrics"]["unique_paths"] == 1
    assert state["file_read_metrics"]["repeat_count"] == 1
    assert agent._execute_tool.call_count == 1
    logger.info.assert_any_call(
        "react_loop.repeat_file_read_nudge_injected",
        session_id="sess-repeat",
        step=1,
        path="d:/cases/mail.eml",
        file_read_repeat_count=1,
    )


@pytest.mark.asyncio
async def test_terminal_tool_failure_marks_tool_unavailable() -> None:
    agent = _make_agent()
    logger = _make_logger()
    call_count = 0
    agent._execute_tool = AsyncMock(
        return_value={
            "success": False,
            "error": "Playwright import failed",
            "error_kind": "tool_unavailable",
            "terminal_failure": True,
        }
    )

    async def fake_complete(**_: Any) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "success": True,
                "tool_calls": [
                    {
                        "id": "browser-call",
                        "type": "function",
                        "function": {
                            "name": "browser",
                            "arguments": (
                                '{"action":"navigate",'
                                '"url":"https://mail.google.com"}'
                            ),
                        },
                    }
                ],
                "content": "",
            }
        return {
            "success": True,
            "tool_calls": None,
            "content": "Blocked by setup.",
        }

    agent.llm_provider = MagicMock()
    agent.llm_provider.complete = AsyncMock(side_effect=fake_complete)
    if hasattr(agent.llm_provider, "complete_stream"):
        del agent.llm_provider.complete_stream

    mission = "Create a browser draft."
    messages = agent.context.messages
    messages.extend(
        [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": mission},
        ]
    )

    async for _ in _react_loop(
        agent, mission, "sess-browser", messages, {}, 0, logger
    ):
        pass

    assert any(
        "browser is unavailable" in message.get("content", "")
        for message in messages
        if message.get("role") == MessageRole.USER.value
    )
    assert any(
        "currently unavailable due to repeated failures: browser"
        in message.get("content", "")
        for message in messages
        if message.get("role") == MessageRole.USER.value
    )
