"""Tests for ParallelAgentTool."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest

from taskforce.core.domain.sub_agents import SubAgentResult, SubAgentSpec
from taskforce.infrastructure.tools.orchestration.parallel_agent_tool import (
    ParallelAgentTool,
)


@dataclass
class _FakeSpawnerCall:
    """Records a spawn() invocation."""

    spec: SubAgentSpec


class FakeSpawner:
    """Test double for SubAgentSpawnerProtocol."""

    def __init__(
        self,
        results: list[SubAgentResult] | None = None,
        delay: float = 0.0,
        fail_indices: set[int] | None = None,
    ) -> None:
        self.calls: list[_FakeSpawnerCall] = []
        self._results = results or []
        self._delay = delay
        self._fail_indices = fail_indices or set()
        self._call_count = 0

    async def spawn(self, spec: SubAgentSpec) -> SubAgentResult:
        idx = self._call_count
        self._call_count += 1
        self.calls.append(_FakeSpawnerCall(spec=spec))

        if self._delay > 0:
            await asyncio.sleep(self._delay)

        if idx in self._fail_indices:
            raise RuntimeError(f"Spawner failed for mission {idx}")

        if idx < len(self._results):
            return self._results[idx]

        return SubAgentResult(
            session_id=f"session-{idx}",
            status="completed",
            success=True,
            final_message=f"Result for: {spec.mission}",
        )


def _make_tool(
    spawner: FakeSpawner | None = None,
    max_concurrency: int = 3,
) -> ParallelAgentTool:
    """Create ParallelAgentTool with a fake spawner."""
    return ParallelAgentTool(
        sub_agent_spawner=spawner or FakeSpawner(),
        profile="dev",
        default_max_concurrency=max_concurrency,
    )


class TestParallelAgentToolProperties:
    """Tests for tool metadata properties."""

    def test_name(self) -> None:
        tool = _make_tool()
        assert tool.name == "call_agents_parallel"

    def test_requires_approval_false(self) -> None:
        """Parallel tool does not require approval (manages internally)."""
        tool = _make_tool()
        assert tool.requires_approval is False

    def test_supports_parallelism_false(self) -> None:
        """Tool manages its own parallelism, so supports_parallelism is False."""
        tool = _make_tool()
        assert tool.supports_parallelism is False

    def test_requires_parent_session(self) -> None:
        tool = _make_tool()
        assert tool.requires_parent_session is True


class TestParallelAgentToolExecution:
    """Tests for parallel execution behavior."""

    @pytest.mark.asyncio
    async def test_empty_missions_returns_error(self) -> None:
        """Empty missions list returns an error."""
        tool = _make_tool()
        result = await tool.execute(missions=[])
        assert result["success"] is False
        assert "No missions" in result["error"]

    @pytest.mark.asyncio
    async def test_single_mission(self) -> None:
        """Single mission executes successfully."""
        spawner = FakeSpawner()
        tool = _make_tool(spawner=spawner)

        result = await tool.execute(
            missions=[{"mission": "Implement feature X"}],
            _parent_session_id="parent-1",
        )

        assert result["success"] is True
        assert result["total"] == 1
        assert result["succeeded"] == 1
        assert result["failed"] == 0
        assert len(spawner.calls) == 1
        assert spawner.calls[0].spec.mission == "Implement feature X"

    @pytest.mark.asyncio
    async def test_multiple_missions_all_succeed(self) -> None:
        """Multiple missions all execute successfully."""
        spawner = FakeSpawner()
        tool = _make_tool(spawner=spawner)

        missions = [
            {"mission": "Task A", "specialist": "coding_worker"},
            {"mission": "Task B", "specialist": "coding_worker"},
            {"mission": "Task C", "specialist": "coding_worker"},
        ]
        result = await tool.execute(
            missions=missions,
            _parent_session_id="parent-1",
        )

        assert result["success"] is True
        assert result["total"] == 3
        assert result["succeeded"] == 3
        assert result["failed"] == 0
        assert len(spawner.calls) == 3

    @pytest.mark.asyncio
    async def test_partial_failure(self) -> None:
        """One failing mission does not cancel others."""
        spawner = FakeSpawner(fail_indices={1})
        tool = _make_tool(spawner=spawner)

        missions = [
            {"mission": "Task A"},
            {"mission": "Task B (will fail)"},
            {"mission": "Task C"},
        ]
        result = await tool.execute(
            missions=missions,
            _parent_session_id="parent-1",
        )

        assert result["success"] is False
        assert result["total"] == 3
        assert result["succeeded"] == 2
        assert result["failed"] == 1

        # Verify the failed result has error info
        failed = [r for r in result["results"] if not r.get("success")]
        assert len(failed) == 1
        assert "Spawner failed" in failed[0]["error"]

    @pytest.mark.asyncio
    async def test_specialist_passed_to_spawner(self) -> None:
        """Specialist from mission spec is passed through to the spawner."""
        spawner = FakeSpawner()
        tool = _make_tool(spawner=spawner)

        await tool.execute(
            missions=[{"mission": "Review code", "specialist": "coding_reviewer"}],
            _parent_session_id="parent-1",
        )

        assert spawner.calls[0].spec.specialist == "coding_reviewer"

    @pytest.mark.asyncio
    async def test_planning_strategy_passed_to_spawner(self) -> None:
        """Planning strategy from mission spec is passed through."""
        spawner = FakeSpawner()
        tool = _make_tool(spawner=spawner)

        await tool.execute(
            missions=[
                {"mission": "Complex task", "planning_strategy": "plan_and_execute"}
            ],
            _parent_session_id="parent-1",
        )

        assert spawner.calls[0].spec.planning_strategy == "plan_and_execute"

    @pytest.mark.asyncio
    async def test_concurrency_limit_respected(self) -> None:
        """Concurrency limit controls max parallel sub-agents."""
        concurrent_count = 0
        max_concurrent = 0
        lock = asyncio.Lock()

        original_spawner = FakeSpawner(delay=0.05)

        class TrackingSpawner:
            async def spawn(self, spec: SubAgentSpec) -> SubAgentResult:
                nonlocal concurrent_count, max_concurrent
                async with lock:
                    concurrent_count += 1
                    max_concurrent = max(max_concurrent, concurrent_count)
                try:
                    return await original_spawner.spawn(spec)
                finally:
                    async with lock:
                        concurrent_count -= 1

        tool = _make_tool(spawner=TrackingSpawner(), max_concurrency=2)

        missions = [
            {"mission": f"Task {i}"} for i in range(5)
        ]
        result = await tool.execute(
            missions=missions,
            _parent_session_id="parent-1",
        )

        assert result["success"] is True
        assert result["total"] == 5
        assert max_concurrent <= 2

    @pytest.mark.asyncio
    async def test_parent_session_id_forwarded(self) -> None:
        """Parent session ID is forwarded to sub-agent specs."""
        spawner = FakeSpawner()
        tool = _make_tool(spawner=spawner)

        await tool.execute(
            missions=[{"mission": "Test"}],
            _parent_session_id="session-abc",
        )

        assert spawner.calls[0].spec.parent_session_id == "session-abc"

    @pytest.mark.asyncio
    async def test_validate_params_requires_missions(self) -> None:
        """validate_params rejects calls without missions."""
        tool = _make_tool()
        valid, error = tool.validate_params()
        assert valid is False
        assert "missions" in error
