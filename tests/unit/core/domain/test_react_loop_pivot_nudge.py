"""Tests for the mid-loop pivot-nudge (#411 / QW7)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.enums import MessageRole
from taskforce.core.domain.models import StreamEvent
from taskforce.core.domain.planning import _react_loop
from taskforce.core.domain.planning.deliverable_check import build_pivot_nudge


def _make_agent(max_steps: int = 60) -> MagicMock:
    agent = MagicMock()
    agent.max_steps = max_steps
    agent.max_parallel_tools = 1
    agent._openai_tools = [{"type": "function", "function": {"name": "python"}}]
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
    agent._ctx_messages = _ctx_messages
    return agent


def _logger() -> MagicMock:
    m = MagicMock()
    for lvl in ("debug", "info", "warning", "error"):
        setattr(m, lvl, MagicMock())
    return m


class TestBuildPivotNudge:
    def test_mentions_each_file(self) -> None:
        nudge = build_pivot_nudge(["a.md", "b.json"], step=35)
        assert "`a.md`" in nudge and "`b.json`" in nudge

    def test_mentions_step_count(self) -> None:
        nudge = build_pivot_nudge(["x.md"], step=42)
        assert "42" in nudge

    def test_attempt_one_pushes_toward_incremental_write(self) -> None:
        nudge = build_pivot_nudge(["x.md"], step=30, attempt=1)
        assert "now" in nudge.lower()
        assert "draft" in nudge.lower() or "incomplete" in nudge.lower()

    def test_attempt_two_is_a_warning(self) -> None:
        nudge = build_pivot_nudge(["x.md"], step=30, attempt=2)
        assert "PIVOT WARNING" in nudge
        assert "MUST" in nudge

    def test_attempt_three_is_force_write(self) -> None:
        nudge = build_pivot_nudge(["x.md"], step=30, attempt=3)
        assert "FORCE WRITE" in nudge
        assert "FAILED" in nudge

    def test_research_count_mentioned_when_nonzero(self) -> None:
        nudge = build_pivot_nudge(["x.md"], step=30, research_calls=12)
        assert "12" in nudge


@pytest.mark.asyncio
async def test_pivot_nudge_fires_when_agent_loops_without_writing(tmp_path: Path) -> None:
    """40 python steps with no file_write → at least one pivot nudge."""
    agent = _make_agent(max_steps=45)
    logger = _logger()

    call_count = 0

    async def fake_complete(**_: Any) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        if call_count <= 40:
            # 40 python tool calls in a row — agent stuck analysing.
            # Vary args per call so the stall/signature-repeat detector
            # does not abort the loop before our pivot threshold (30).
            return {
                "success": True,
                "tool_calls": [
                    {
                        "id": f"tc_{call_count}",
                        "type": "function",
                        "function": {
                            "name": "python",
                            "arguments": json.dumps({"code": f"x = {call_count}"}),
                        },
                    }
                ],
                "content": "",
            }
        return {"success": True, "tool_calls": None, "content": "done"}

    agent.llm_provider = MagicMock()
    agent.llm_provider.complete = AsyncMock(side_effect=fake_complete)
    if hasattr(agent.llm_provider, "complete_stream"):
        del agent.llm_provider.complete_stream

    mission = f"Analyse the data. Write `report.md` in `{tmp_path.as_posix()}`."
    messages = agent.context.messages
    messages.extend(
        [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": mission},
        ]
    )

    async for _ in _react_loop(agent, mission, "sess-1", messages, {}, 0, logger):
        pass

    # Pivot-specific markers (deliverable-finalize nudge has different
    # wording — see _build_deliverable_nudge).
    pivot_nudges = [
        m
        for m in messages
        if m.get("role") == MessageRole.USER.value
        and any(marker in m.get("content", "") for marker in (
            "Stop researching",
            "PIVOT WARNING",
            "FORCE WRITE",
        ))
    ]
    assert len(pivot_nudges) >= 1, "expected at least one pivot nudge"
    assert len(pivot_nudges) <= 3, "pivot nudges must be hard-capped at _PIVOT_MAX=3"
    assert "report.md" in pivot_nudges[0]["content"]


@pytest.mark.asyncio
async def test_no_pivot_when_agent_writes_early(tmp_path: Path) -> None:
    """Agent writes the file on first step → no pivot nudge."""
    agent = _make_agent(max_steps=45)
    logger = _logger()

    call_count = 0

    async def fake_complete(**_: Any) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "success": True,
                "tool_calls": [
                    {
                        "id": "tc_1",
                        "type": "function",
                        "function": {
                            "name": "file_write",
                            "arguments": json.dumps(
                                {"path": str(tmp_path / "report.md"), "content": "hi"}
                            ),
                        },
                    }
                ],
                "content": "",
            }
        # Many more python calls — but since a write happened first,
        # the pivot nudge must NOT fire.
        if call_count <= 35:
            return {
                "success": True,
                "tool_calls": [
                    {
                        "id": f"tc_{call_count}",
                        "type": "function",
                        "function": {
                            "name": "python",
                            "arguments": json.dumps({"code": f"x = {call_count}"}),
                        },
                    }
                ],
                "content": "",
            }
        return {"success": True, "tool_calls": None, "content": "done"}

    async def fake_exec_tool(tool_name: str, args: Any, *_, **__):
        if tool_name == "file_write":
            (tmp_path / "report.md").write_text("hi", encoding="utf-8")
        return {"success": True, "output": "ok"}

    agent.llm_provider = MagicMock()
    agent.llm_provider.complete = AsyncMock(side_effect=fake_complete)
    agent._execute_tool = AsyncMock(side_effect=fake_exec_tool)
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

    pivot_nudges = [
        m
        for m in messages
        if m.get("role") == MessageRole.USER.value
        and ("still missing" in m.get("content", "") or "STILL missing" in m.get("content", ""))
    ]
    assert pivot_nudges == [], "no pivot nudge expected when agent wrote early"


@pytest.mark.asyncio
async def test_pivot_fires_on_research_burst_without_step_threshold(tmp_path: Path) -> None:
    """10 web_search calls in 5 react bursts → pivot fires via research counter
    even though step count is well below _PIVOT_STEP_FALLBACK=25."""
    import json
    agent = _make_agent(max_steps=40)
    logger = _logger()

    call_count = 0

    async def fake_complete(**_: Any) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        if call_count <= 10:
            # 2 web_search per step → research counter climbs fast
            return {
                "success": True,
                "tool_calls": [
                    {
                        "id": f"tc_{call_count}_a",
                        "type": "function",
                        "function": {
                            "name": "web_search",
                            "arguments": json.dumps({"query": f"q{call_count}a"}),
                        },
                    },
                    {
                        "id": f"tc_{call_count}_b",
                        "type": "function",
                        "function": {
                            "name": "web_search",
                            "arguments": json.dumps({"query": f"q{call_count}b"}),
                        },
                    },
                ],
                "content": "",
            }
        return {"success": True, "tool_calls": None, "content": "done"}

    agent.llm_provider = MagicMock()
    agent.llm_provider.complete = AsyncMock(side_effect=fake_complete)
    if hasattr(agent.llm_provider, "complete_stream"):
        del agent.llm_provider.complete_stream
    # max_parallel_tools needs to allow 2 simultaneous calls.
    agent.max_parallel_tools = 4

    mission = f"Research things. Write `out.md` in `{tmp_path.as_posix()}`."
    messages = agent.context.messages
    messages.extend(
        [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": mission},
        ]
    )

    async for _ in _react_loop(agent, mission, "sess-1", messages, {}, 0, logger):
        pass

    pivot_nudges = [
        m
        for m in messages
        if m.get("role") == MessageRole.USER.value
        and ("first version NOW" in m.get("content", "") or "PIVOT WARNING" in m.get("content", "") or "FORCE WRITE" in m.get("content", ""))
    ]
    assert len(pivot_nudges) >= 1, "research-burst should trigger pivot"
    # Escalating cap at 3.
    assert len(pivot_nudges) <= 3


@pytest.mark.asyncio
async def test_pivot_skipped_when_deliverable_exists_via_python_write(tmp_path: Path) -> None:
    """Agent writes the file via python (not file_write), then does many
    python calls. Disk-check sees the file → no pivot fires."""
    import json
    # Pre-create the deliverable to simulate a python write completing.
    (tmp_path / "out.md").write_text("done", encoding="utf-8")

    agent = _make_agent(max_steps=45)
    logger = _logger()

    call_count = 0

    async def fake_complete(**_: Any) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        if call_count <= 40:
            return {
                "success": True,
                "tool_calls": [
                    {
                        "id": f"tc_{call_count}",
                        "type": "function",
                        "function": {
                            "name": "python",
                            "arguments": json.dumps({"code": f"x = {call_count}"}),
                        },
                    }
                ],
                "content": "",
            }
        return {"success": True, "tool_calls": None, "content": "done"}

    agent.llm_provider = MagicMock()
    agent.llm_provider.complete = AsyncMock(side_effect=fake_complete)
    if hasattr(agent.llm_provider, "complete_stream"):
        del agent.llm_provider.complete_stream

    mission = f"Write `out.md` in `{tmp_path.as_posix()}`."
    messages = agent.context.messages
    messages.extend(
        [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": mission},
        ]
    )

    async for _ in _react_loop(agent, mission, "sess-1", messages, {}, 0, logger):
        pass

    pivot_nudges = [
        m
        for m in messages
        if m.get("role") == MessageRole.USER.value
        and "first version NOW" in m.get("content", "")
    ]
    assert pivot_nudges == [], "no pivot expected when deliverable already on disk"


@pytest.mark.asyncio
async def test_no_pivot_for_mission_without_deliverable() -> None:
    """No declared deliverable → no pivot even if agent loops on python forever."""
    agent = _make_agent(max_steps=45)
    logger = _logger()

    call_count = 0

    async def fake_complete(**_: Any) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        if call_count <= 40:
            return {
                "success": True,
                "tool_calls": [
                    {
                        "id": f"tc_{call_count}",
                        "type": "function",
                        "function": {
                            "name": "python",
                            "arguments": json.dumps({"code": f"x = {call_count}"}),
                        },
                    }
                ],
                "content": "",
            }
        return {"success": True, "tool_calls": None, "content": "done"}

    agent.llm_provider = MagicMock()
    agent.llm_provider.complete = AsyncMock(side_effect=fake_complete)
    if hasattr(agent.llm_provider, "complete_stream"):
        del agent.llm_provider.complete_stream

    mission = "Just count the primes under 100."
    messages = agent.context.messages
    messages.extend(
        [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": mission},
        ]
    )

    async for _ in _react_loop(agent, mission, "sess-1", messages, {}, 0, logger):
        pass

    pivot_nudges = [
        m
        for m in messages
        if m.get("role") == MessageRole.USER.value
        and ("still missing" in m.get("content", "") or "STILL missing" in m.get("content", ""))
    ]
    assert pivot_nudges == []
