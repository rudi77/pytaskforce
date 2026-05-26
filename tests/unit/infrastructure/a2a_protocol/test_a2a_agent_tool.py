"""Tests for the call_a2a_agent orchestration tool."""

from __future__ import annotations

from typing import Any

import pytest

from taskforce.core.domain.a2a import (
    A2aArtifact,
    A2aPeer,
    A2aTaskHandle,
    A2aTaskState,
)
from taskforce.infrastructure.a2a.peer_registry import InMemoryA2aPeerRegistry
from taskforce.infrastructure.a2a.runtime import A2aRuntime
from taskforce.infrastructure.tools.orchestration.a2a_agent_tool import A2aAgentTool


class _StubClient:
    def __init__(self, handle: A2aTaskHandle) -> None:
        self._handle = handle

    async def run_sync(self, peer: A2aPeer, mission: str, **kw: Any) -> A2aTaskHandle:
        return self._handle

    async def run_stream(self, *a: Any, **k: Any):  # pragma: no cover
        if False:
            yield {}

    async def close(self) -> None:
        pass


def _runtime_with(handle: A2aTaskHandle) -> A2aRuntime:
    peers = InMemoryA2aPeerRegistry([A2aPeer(name="demo", base_url="http://x")])
    return A2aRuntime(client=_StubClient(handle), peers=peers)


@pytest.mark.asyncio
async def test_tool_returns_completed_state_and_artifacts() -> None:
    handle = A2aTaskHandle(
        task_id="task-1",
        peer="demo",
        state=A2aTaskState.COMPLETED,
        output_text="done",
        artifacts=(A2aArtifact(name="result.json", mime_type="application/json", path="/tmp/x"),),
    )
    tool = A2aAgentTool(runtime=_runtime_with(handle))
    result = await tool._execute(peer="demo", mission="run it")

    assert result["success"] is True
    assert result["state"] == "completed"
    assert result["task_id"] == "task-1"
    assert result["output_text"] == "done"
    assert result["needs_user_input"] is False
    assert result["needs_auth"] is False
    assert len(result["output_artifacts"]) == 1
    assert result["output_artifacts"][0]["name"] == "result.json"


@pytest.mark.asyncio
async def test_tool_surfaces_input_required_with_hint() -> None:
    handle = A2aTaskHandle(
        task_id="t2",
        peer="demo",
        state=A2aTaskState.INPUT_REQUIRED,
        output_text="What's the file path?",
    )
    tool = A2aAgentTool(runtime=_runtime_with(handle))
    result = await tool._execute(peer="demo", mission="paused")

    assert result["success"] is True
    assert result["state"] == "input-required"
    assert result["needs_user_input"] is True
    assert "Call call_a2a_agent again" in (result["resume_hint"] or "")
    assert "t2" in (result["resume_hint"] or "")


@pytest.mark.asyncio
async def test_tool_returns_error_for_unknown_peer() -> None:
    handle = A2aTaskHandle(task_id="", peer="demo", state=A2aTaskState.UNKNOWN)
    tool = A2aAgentTool(runtime=_runtime_with(handle))
    result = await tool._execute(peer="ghost", mission="x")

    assert result["success"] is False
    assert "Unknown A2A peer" in result.get("error_message", "") or "Unknown A2A peer" in str(
        result
    )
