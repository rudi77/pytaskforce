"""Integration test for the deliverable-check hook in ``_react_loop`` (#405)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.enums import MessageRole
from taskforce.core.domain.models import StreamEvent
from taskforce.core.domain.planning import _react_loop


def _make_agent(max_steps: int = 4) -> MagicMock:
    """Minimal mock agent for ``_react_loop`` exercises."""
    agent = MagicMock()
    agent.max_steps = max_steps
    agent.max_parallel_tools = 1
    agent._openai_tools = []
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
    agent._prompt_cache = None
    agent.tool_result_message_factory = AsyncMock()
    agent.tool_result_message_factory.build_message = AsyncMock(
        return_value={"role": "tool", "content": "result"}
    )
    agent._execute_tool = AsyncMock()
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
    agent._ctx_messages = _ctx_messages
    return agent


def _make_logger() -> MagicMock:
    logger = MagicMock()
    for level in ("debug", "info", "warning", "error"):
        setattr(logger, level, MagicMock())
    return logger


@pytest.mark.asyncio
async def test_deliverable_nudge_injected_when_file_missing(tmp_path: Path) -> None:
    """LLM tries to finalize without writing the named file → loop nudges once."""
    agent = _make_agent(max_steps=4)
    logger = _make_logger()

    call_count = 0

    async def fake_complete(**_: Any) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"success": True, "tool_calls": None, "content": "Status: done."}
        return {"success": True, "tool_calls": None, "content": "Final answer."}

    agent.llm_provider = MagicMock()
    agent.llm_provider.complete = AsyncMock(side_effect=fake_complete)
    if hasattr(agent.llm_provider, "complete_stream"):
        del agent.llm_provider.complete_stream

    # Mission names a deliverable; tmp_path is a candidate dir but the file
    # is NOT created → must trigger one nudge before accepting completion.
    mission = (
        f"Analyze the data. Write your report to `out.md` in "
        f"`{tmp_path.as_posix()}`."
    )
    messages = agent.context.messages
    messages.extend(
        [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": mission},
        ]
    )

    events: list[StreamEvent] = []
    async for evt in _react_loop(agent, mission, "sess-1", messages, {}, 0, logger):
        events.append(evt)

    nudges = [
        m
        for m in messages
        if m.get("role") == MessageRole.USER.value
        and "do not exist on disk" in m.get("content", "")
    ]
    assert len(nudges) == 1, "expected exactly one deliverable nudge"
    assert "out.md" in nudges[0]["content"]
    # LLM was called at least twice — initial finalize attempt + post-nudge retry.
    assert call_count >= 2


@pytest.mark.asyncio
async def test_no_nudge_when_deliverable_exists(tmp_path: Path) -> None:
    (tmp_path / "out.md").write_text("done")
    agent = _make_agent(max_steps=3)
    logger = _make_logger()

    async def fake_complete(**_: Any) -> dict[str, Any]:
        return {"success": True, "tool_calls": None, "content": "All done."}

    agent.llm_provider = MagicMock()
    agent.llm_provider.complete = AsyncMock(side_effect=fake_complete)
    if hasattr(agent.llm_provider, "complete_stream"):
        del agent.llm_provider.complete_stream

    mission = f"Save findings to `out.md` in `{tmp_path.as_posix()}`."
    messages = agent.context.messages
    messages.extend(
        [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": mission},
        ]
    )

    async for _ in _react_loop(agent, mission, "sess-1", messages, {}, 0, logger):
        pass

    nudges = [
        m
        for m in messages
        if m.get("role") == MessageRole.USER.value
        and "do not exist on disk" in m.get("content", "")
    ]
    assert nudges == [], "no nudge expected when deliverable already exists"


@pytest.mark.asyncio
async def test_nudge_fires_only_once_per_mission(tmp_path: Path) -> None:
    """LLM ignores the nudge and re-finalizes → loop accepts and exits."""
    agent = _make_agent(max_steps=5)
    logger = _make_logger()

    async def fake_complete(**_: Any) -> dict[str, Any]:
        return {"success": True, "tool_calls": None, "content": "Done."}

    agent.llm_provider = MagicMock()
    agent.llm_provider.complete = AsyncMock(side_effect=fake_complete)
    if hasattr(agent.llm_provider, "complete_stream"):
        del agent.llm_provider.complete_stream

    mission = f"Write `report.md` in `{tmp_path.as_posix()}`."
    messages = agent.context.messages
    messages.extend(
        [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": mission},
        ]
    )

    async for _ in _react_loop(agent, mission, "sess-1", messages, {}, 0, logger):
        pass

    nudges = [
        m
        for m in messages
        if m.get("role") == MessageRole.USER.value
        and "do not exist on disk" in m.get("content", "")
    ]
    assert len(nudges) == 1, "nudge must fire exactly once even if LLM ignores it"


@pytest.mark.asyncio
async def test_ignored_nudge_marks_final_answer_as_salvaged(tmp_path: Path) -> None:
    """#407: deliverable still missing after the nudge → FINAL_ANSWER carries
    ``salvaged=True`` + ``salvage_reason='deliverable_missing'``."""
    from taskforce.core.domain.enums import EventType

    agent = _make_agent(max_steps=4)
    logger = _make_logger()

    async def fake_complete(**_: Any) -> dict[str, Any]:
        # Agent never writes the file — both attempts emit content only.
        return {"success": True, "tool_calls": None, "content": "Status: failed."}

    agent.llm_provider = MagicMock()
    agent.llm_provider.complete = AsyncMock(side_effect=fake_complete)
    if hasattr(agent.llm_provider, "complete_stream"):
        del agent.llm_provider.complete_stream

    mission = f"Write `report.md` in `{tmp_path.as_posix()}`."
    messages = agent.context.messages
    messages.extend(
        [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": mission},
        ]
    )

    events: list[StreamEvent] = []
    async for evt in _react_loop(agent, mission, "sess-1", messages, {}, 0, logger):
        events.append(evt)

    final_events = [e for e in events if e.event_type == EventType.FINAL_ANSWER]
    assert len(final_events) == 1
    data = final_events[0].data
    assert data.get("salvaged") is True
    assert data.get("salvage_reason") == "deliverable_missing"
    assert "report.md" in data.get("missing_deliverables", [])


@pytest.mark.asyncio
async def test_no_nudge_when_mission_has_no_deliverable() -> None:
    agent = _make_agent(max_steps=3)
    logger = _make_logger()

    async def fake_complete(**_: Any) -> dict[str, Any]:
        return {"success": True, "tool_calls": None, "content": "Here's the answer."}

    agent.llm_provider = MagicMock()
    agent.llm_provider.complete = AsyncMock(side_effect=fake_complete)
    if hasattr(agent.llm_provider, "complete_stream"):
        del agent.llm_provider.complete_stream

    mission = "What is 2 + 2?"
    messages = agent.context.messages
    messages.extend(
        [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": mission},
        ]
    )

    async for _ in _react_loop(agent, mission, "sess-1", messages, {}, 0, logger):
        pass

    nudges = [
        m
        for m in messages
        if m.get("role") == MessageRole.USER.value
        and "do not exist on disk" in m.get("content", "")
    ]
    assert nudges == []
