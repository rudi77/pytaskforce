"""Tests for the streaming tool-call accumulator in :func:`_react_loop`.

Regression tests for issue #155 — Telegram action gap. The streaming
ReAct loop must register a tool call from the LLM stream regardless of
whether the provider sends a ``tool_call_start`` event before the
``tool_call_delta`` / ``tool_call_end`` events. Otherwise the agent
"says it will do X" (streamed assistant tokens already shown to the
user) but the matching tool never executes.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.enums import EventType, MessageRole
from taskforce.core.domain.models import StreamEvent
from taskforce.core.domain.planning import _react_loop


def _make_agent(max_steps: int = 5) -> MagicMock:
    """Mirror the helper used elsewhere in the suite — minimal mock agent."""
    agent = MagicMock()
    agent.max_steps = max_steps
    agent.max_parallel_tools = 1
    agent._openai_tools = [{"type": "function", "function": {"name": "calendar_create"}}]
    agent._planner = None
    agent.planner = None
    agent.tools = {}
    agent.state_manager = AsyncMock()
    agent.state_store = AsyncMock()
    agent.record_heartbeat = AsyncMock()
    agent.message_history_manager = MagicMock()
    agent.message_history_manager.compress_messages = AsyncMock(side_effect=lambda m: m)
    agent.message_history_manager.preflight_budget_check = MagicMock(side_effect=lambda m: m)
    agent._build_system_prompt = MagicMock(return_value="system prompt")
    agent._truncate_output = MagicMock(side_effect=lambda x: x)
    agent.tool_result_message_factory = AsyncMock()
    agent.tool_result_message_factory.build_message = AsyncMock(
        return_value={"role": "tool", "content": "result"}
    )
    agent._execute_tool = AsyncMock(return_value={"success": True, "output": "ok"})
    agent.load_memory_context = AsyncMock()

    _ctx_messages: list[dict[str, Any]] = []
    context = MagicMock()
    context.messages = _ctx_messages
    context.set_system_prompt = MagicMock(
        side_effect=lambda p: (
            _ctx_messages.__setitem__(0, {"role": "system", "content": p})
            if _ctx_messages
            else _ctx_messages.append({"role": "system", "content": p})
        )
    )
    context.append_message = MagicMock(side_effect=lambda m: _ctx_messages.append(m))
    context.compress = AsyncMock()
    context.preflight_check = MagicMock()
    context.prepare_for_llm = AsyncMock()
    agent.context = context
    agent._sub_agent_event_sink = None
    return agent


def _make_logger() -> MagicMock:
    log = MagicMock()
    log.info = MagicMock()
    log.warning = MagicMock()
    log.debug = MagicMock()
    log.error = MagicMock()
    return log


async def _make_stream(chunks):
    for c in chunks:
        yield c


@pytest.mark.asyncio
async def test_tool_call_fires_when_start_event_missing() -> None:
    """If only ``tool_call_delta`` + ``tool_call_end`` are streamed (no
    ``tool_call_start``), the tool MUST still execute. The original bug
    silently dropped the call because the consumer required a prior start
    event to register the index.
    """
    agent = _make_agent(max_steps=3)
    logger = _make_logger()

    call_count = 0

    def stream_factory(**kwargs: Any):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Stream a tool call WITHOUT the tool_call_start event.
            return _make_stream(
                [
                    {
                        "type": "tool_call_delta",
                        "index": 0,
                        "id": "call_abc",
                        "arguments_delta": '{"title":"meeting"}',
                    },
                    {
                        "type": "tool_call_end",
                        "index": 0,
                        "id": "call_abc",
                        "name": "calendar_create",
                        "arguments": '{"title":"meeting"}',
                    },
                    {"type": "done", "usage": {}},
                ]
            )
        # Second LLM turn returns final content so the loop terminates.
        return _make_stream(
            [
                {"type": "token", "content": "Booked."},
                {"type": "done", "usage": {}},
            ]
        )

    agent.llm_provider = MagicMock()
    agent.llm_provider.complete_stream = MagicMock(side_effect=stream_factory)

    messages = agent.context.messages
    messages.extend(
        [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "Book a meeting"},
        ]
    )

    events: list[StreamEvent] = []
    async for evt in _react_loop(agent, "Book a meeting", "sess-155", messages, {}, 0, logger):
        events.append(evt)

    # The tool MUST have been executed exactly once with the parsed args.
    assert (
        agent._execute_tool.await_count == 1
    ), f"tool was not executed; call_count={agent._execute_tool.await_count}"
    name, args = agent._execute_tool.call_args.args[:2]
    assert name == "calendar_create"
    assert args == {"title": "meeting"}

    # And a TOOL_CALL event was emitted to the stream consumer (so the user
    # sees the action happen, not just streamed text).
    tool_call_events = [e for e in events if e.event_type == EventType.TOOL_CALL]
    assert len(tool_call_events) == 1
    assert tool_call_events[0].data["tool"] == "calendar_create"


@pytest.mark.asyncio
async def test_tool_call_fires_when_id_arrives_after_arguments() -> None:
    """First delta carries arguments only; ``tool_call_start`` arrives in a
    later chunk. The tool must still fire (issue #155).
    """
    agent = _make_agent(max_steps=3)
    logger = _make_logger()

    call_count = 0

    def stream_factory(**kwargs: Any):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_stream(
                [
                    # Arguments arrive before id/name are known.
                    {
                        "type": "tool_call_delta",
                        "index": 0,
                        "arguments_delta": '{"title":',
                    },
                    # Late start.
                    {
                        "type": "tool_call_start",
                        "index": 0,
                        "id": "call_late",
                        "name": "calendar_create",
                    },
                    {
                        "type": "tool_call_delta",
                        "index": 0,
                        "id": "call_late",
                        "arguments_delta": '"meeting"}',
                    },
                    {
                        "type": "tool_call_end",
                        "index": 0,
                        "id": "call_late",
                        "name": "calendar_create",
                        "arguments": '{"title":"meeting"}',
                    },
                    {"type": "done", "usage": {}},
                ]
            )
        return _make_stream(
            [
                {"type": "token", "content": "Done."},
                {"type": "done", "usage": {}},
            ]
        )

    agent.llm_provider = MagicMock()
    agent.llm_provider.complete_stream = MagicMock(side_effect=stream_factory)

    messages = agent.context.messages
    messages.extend(
        [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "Book a meeting"},
        ]
    )

    async for _ in _react_loop(agent, "Book a meeting", "sess-155b", messages, {}, 0, logger):
        pass

    assert agent._execute_tool.await_count == 1
    name, args = agent._execute_tool.call_args.args[:2]
    assert name == "calendar_create"
    assert args == {"title": "meeting"}


@pytest.mark.asyncio
async def test_no_silent_drop_when_chat_promises_action() -> None:
    """End-to-end: LLM streams "I will create a calendar entry" tokens
    AND a tool call. Both the user-visible final answer AND the tool
    must occur — no silent gap (issue #155 root cause).
    """
    agent = _make_agent(max_steps=3)
    logger = _make_logger()

    call_count = 0

    def stream_factory(**kwargs: Any):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_stream(
                [
                    # Provider streams content first…
                    {"type": "token", "content": "I will create a calendar entry."},
                    # …then a tool call, but with id arriving late.
                    {
                        "type": "tool_call_delta",
                        "index": 0,
                        "arguments_delta": '{"title":"meeting"}',
                    },
                    {
                        "type": "tool_call_end",
                        "index": 0,
                        "id": "call_z",
                        "name": "calendar_create",
                        "arguments": '{"title":"meeting"}',
                    },
                    {"type": "done", "usage": {}},
                ]
            )
        return _make_stream(
            [
                {"type": "token", "content": "Calendar entry created."},
                {"type": "done", "usage": {}},
            ]
        )

    agent.llm_provider = MagicMock()
    agent.llm_provider.complete_stream = MagicMock(side_effect=stream_factory)

    messages = agent.context.messages
    messages.extend(
        [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "Book a meeting"},
        ]
    )

    final_content = ""
    tool_called = False
    async for evt in _react_loop(agent, "Book a meeting", "sess-155c", messages, {}, 0, logger):
        if evt.event_type == EventType.TOOL_CALL:
            tool_called = True
        if evt.event_type == EventType.FINAL_ANSWER:
            final_content = evt.data.get("content", "")

    assert tool_called, "Bug #155 regression: tool never fired"
    assert agent._execute_tool.await_count == 1
    # And a final answer must be produced (the test contract — no silent
    # drop where the user gets a promise without an answer).
    assert "Calendar" in final_content or "created" in final_content.lower()


@pytest.mark.asyncio
async def test_role_user_after_tool_failure_is_unchanged() -> None:
    """Sanity: failed tool execution still surfaces a TOOL_RESULT event
    with success=False. (Used to guarantee the action gap fix didn't
    silently swallow tool exceptions.)
    """
    agent = _make_agent(max_steps=3)
    logger = _make_logger()

    agent._execute_tool = AsyncMock(return_value={"success": False, "error": "calendar API down"})

    call_count = 0

    def stream_factory(**kwargs: Any):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_stream(
                [
                    {
                        "type": "tool_call_start",
                        "index": 0,
                        "id": "call_q",
                        "name": "calendar_create",
                    },
                    {
                        "type": "tool_call_delta",
                        "index": 0,
                        "id": "call_q",
                        "arguments_delta": "{}",
                    },
                    {
                        "type": "tool_call_end",
                        "index": 0,
                        "id": "call_q",
                        "name": "calendar_create",
                        "arguments": "{}",
                    },
                    {"type": "done", "usage": {}},
                ]
            )
        return _make_stream(
            [
                {"type": "token", "content": "Sorry, calendar is down."},
                {"type": "done", "usage": {}},
            ]
        )

    agent.llm_provider = MagicMock()
    agent.llm_provider.complete_stream = MagicMock(side_effect=stream_factory)

    messages = agent.context.messages
    messages.extend(
        [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "Book a meeting"},
        ]
    )

    tool_results = []
    async for evt in _react_loop(agent, "Book a meeting", "sess-155d", messages, {}, 0, logger):
        if evt.event_type == EventType.TOOL_RESULT:
            tool_results.append(evt)

    assert len(tool_results) == 1
    assert tool_results[0].data.get("success") is False
    # And a retry nudge was injected (existing resilience behaviour).
    nudges = [
        m
        for m in messages
        if m.get("role") == MessageRole.USER.value
        and "calendar_create" in str(m.get("content", ""))
        and "failed" in str(m.get("content", ""))
    ]
    assert nudges, "expected a retry nudge after tool failure"


@pytest.mark.spec("react-loop.llm_stream_restart_emitted_on_content_filter")
@pytest.mark.asyncio
async def test_stream_restart_resets_accumulators_and_yields_downstream_event() -> None:
    """Issue #159 sub-item (a): when the LLM provider yields a
    ``stream_restart`` (content-filter recovery), the react loop must
    drop everything accumulated from the failed attempt AND surface a
    matching downstream event so UI consumers can clear their partial
    render.

    Without this the final assistant message ends up as
    "partial-attempt-tokens + recovered-attempt-tokens" concatenated.
    """
    agent = _make_agent(max_steps=3)
    logger = _make_logger()

    def stream_factory(**_kwargs: Any):
        # Single stream that emits partial content, then a restart, then
        # the clean retry tokens. Mirrors what LiteLLMService.complete_stream
        # yields when the first attempt content-filters mid-stream.
        return _make_stream(
            [
                {"type": "token", "content": "Hier sind die "},
                {"type": "token", "content": "halb"},
                {
                    "type": "stream_restart",
                    "reason": "content_filter",
                    "stage": "tool_results_only",
                },
                {"type": "token", "content": "Saubere Antwort."},
                {"type": "done", "usage": {}},
            ]
        )

    agent.llm_provider = MagicMock()
    agent.llm_provider.complete_stream = MagicMock(side_effect=stream_factory)

    messages = agent.context.messages
    messages.extend(
        [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "summarise"},
        ]
    )

    events: list[StreamEvent] = []
    async for evt in _react_loop(
        agent, "summarise", "sess-159a", messages, {}, 0, logger
    ):
        events.append(evt)

    restart_events = [
        e for e in events if e.event_type == EventType.LLM_STREAM_RESTART
    ]
    assert len(restart_events) == 1
    assert restart_events[0].data == {
        "reason": "content_filter",
        "stage": "tool_results_only",
    }

    # The final assistant message appended after the stream ends must
    # only contain the clean retry content — not the partial pre-restart
    # tokens.
    assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
    assert assistant_msgs, "expected an assistant message after stream end"
    final_assistant = assistant_msgs[-1]
    assert final_assistant.get("content") == "Saubere Antwort.", final_assistant
