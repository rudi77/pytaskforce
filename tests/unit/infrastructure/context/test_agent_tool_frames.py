"""Tests for the ctxman frames hook in AgentTool (sequential sub-agents)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from taskforce.core.domain.sub_agents import SubAgentResult
from taskforce.infrastructure.context.frame_binding import (
    FrameBinding,
    get_frame_binding,
)
from taskforce.infrastructure.tools.orchestration.agent_tool import AgentTool


def _make_spawner(observed_bindings: list[FrameBinding | None]) -> Mock:
    """Spawner mock that records the frame binding active during spawn."""

    async def spawn(spec: Any) -> SubAgentResult:
        observed_bindings.append(get_frame_binding())
        return SubAgentResult(
            session_id="sub-1",
            status="completed",
            success=True,
            final_message="sub result",
            error=None,
            error_kind=None,
            context_snapshot=None,
        )

    spawner = Mock()
    spawner.spawn = AsyncMock(side_effect=spawn)
    return spawner


def _make_parent_cm(*, frames_supported: bool = True) -> Mock:
    binding = FrameBinding(client=Mock(), session_id="parent-sess", frame_id="f1")
    parent_cm = Mock()
    parent_cm.frames_supported = frames_supported
    parent_cm.push_frame = AsyncMock(return_value=binding)
    parent_cm.pop_frame = AsyncMock()
    return parent_cm


@pytest.mark.spec("context-manager-ctxman.sequential_sub_agent_runs_in_frame")
async def test_sequential_sub_agent_runs_inside_parent_frame() -> None:
    observed: list[FrameBinding | None] = []
    spawner = _make_spawner(observed)
    tool = AgentTool(agent_factory=Mock(), sub_agent_spawner=spawner)
    parent_cm = _make_parent_cm()
    tool.set_parent_context_ref(parent_cm)

    result = await tool.execute(mission="do research", specialist="research")

    assert result["success"] is True
    parent_cm.push_frame.assert_awaited_once_with("research")
    # The binding was visible to the spawner (same task context)...
    assert observed == [parent_cm.push_frame.return_value]
    # ...and is cleared again after execution.
    assert get_frame_binding() is None
    parent_cm.pop_frame.assert_awaited_once()
    _, kwargs = parent_cm.pop_frame.await_args
    assert "completed" in kwargs["return_content"]


async def test_frame_popped_even_when_sub_agent_fails() -> None:
    spawner = Mock()
    spawner.spawn = AsyncMock(side_effect=RuntimeError("boom"))
    tool = AgentTool(agent_factory=Mock(), sub_agent_spawner=spawner)
    parent_cm = _make_parent_cm()
    tool.set_parent_context_ref(parent_cm)

    result = await tool.execute(mission="m", specialist="coding")
    assert result["success"] is False
    parent_cm.pop_frame.assert_awaited_once()
    _, kwargs = parent_cm.pop_frame.await_args
    assert "failed" in kwargs["return_content"]
    assert get_frame_binding() is None


async def test_no_frame_when_parent_cm_does_not_support_frames() -> None:
    observed: list[FrameBinding | None] = []
    spawner = _make_spawner(observed)
    tool = AgentTool(agent_factory=Mock(), sub_agent_spawner=spawner)
    parent_cm = _make_parent_cm(frames_supported=False)
    tool.set_parent_context_ref(parent_cm)

    await tool.execute(mission="m", specialist="rag")
    parent_cm.push_frame.assert_not_awaited()
    assert observed == [None]


async def test_no_frame_without_parent_context_ref() -> None:
    observed: list[FrameBinding | None] = []
    spawner = _make_spawner(observed)
    tool = AgentTool(agent_factory=Mock(), sub_agent_spawner=spawner)

    result = await tool.execute(mission="m")
    assert result["success"] is True
    assert observed == [None]


@pytest.mark.spec("context-manager-ctxman.degraded_push_falls_back_to_own_session")
async def test_degraded_push_frame_falls_back_to_plain_spawn() -> None:
    observed: list[FrameBinding | None] = []
    spawner = _make_spawner(observed)
    tool = AgentTool(agent_factory=Mock(), sub_agent_spawner=spawner)
    parent_cm = _make_parent_cm()
    parent_cm.push_frame = AsyncMock(return_value=None)  # degrade mode
    tool.set_parent_context_ref(parent_cm)

    result = await tool.execute(mission="m", specialist="x")
    assert result["success"] is True
    assert observed == [None]
    parent_cm.pop_frame.assert_not_awaited()
