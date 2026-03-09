"""
Integration tests for parallel sub-agent execution.

Tests the full parallel dispatch flow: parent agent spawns multiple
sub-agents concurrently via ParallelAgentTool and via auto_approve
flag on SubAgentTool.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskforce.application.factory import AgentFactory
from taskforce.core.domain.models import ExecutionResult
from taskforce.core.domain.sub_agents import SubAgentResult, SubAgentSpec
from taskforce.infrastructure.tools.orchestration.parallel_agent_tool import (
    ParallelAgentTool,
)
from taskforce.infrastructure.tools.orchestration.sub_agent_tool import SubAgentTool


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def coding_agent_config(tmp_path):
    """Config that mirrors coding_agent.yaml with parallel tools."""
    return {
        "agent": {
            "type": "generic",
            "specialist": "coding",
            "planning_strategy": "native_react",
            "max_steps": 50,
            "max_parallel_tools": 3,
        },
        "tools": [
            "file_read",
            "grep",
            "glob",
            {"type": "sub_agent", "name": "coding_worker", "auto_approve": True},
            {"type": "sub_agent", "name": "coding_analyst", "auto_approve": True},
            {"type": "sub_agent", "name": "coding_reviewer"},
            {"type": "parallel_agent", "max_concurrency": 3},
        ],
        "llm": {"config_path": "configs/llm_config.yaml", "default_model": "main"},
        "persistence": {"type": "file", "work_dir": str(tmp_path)},
        "logging": {"level": "INFO"},
    }


def _make_mock_sub_agent(session_id: str, message: str) -> MagicMock:
    """Create a mock sub-agent that completes with given message."""
    agent = MagicMock()
    agent.max_steps = 25
    agent.execute = AsyncMock(
        return_value=ExecutionResult(
            status="completed",
            session_id=session_id,
            final_message=message,
            execution_history=[],
        )
    )
    agent.close = AsyncMock()
    return agent


# ---------------------------------------------------------------------------
# Tests: Profile wiring (auto_approve + parallel_agent in coding_agent)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coding_agent_has_parallel_tool(coding_agent_config, tmp_path):
    """Coding agent config wires the call_agents_parallel tool."""
    factory = AgentFactory()

    with patch.object(factory, "_load_profile", return_value=coding_agent_config):
        agent = await factory.create_agent(profile="coding_agent")

    tool_names = [t.name for t in agent.tools.values()]
    assert "call_agents_parallel" in tool_names


@pytest.mark.asyncio
async def test_coding_agent_worker_auto_approved(coding_agent_config, tmp_path):
    """coding_worker with auto_approve=true has requires_approval=False."""
    factory = AgentFactory()

    with patch.object(factory, "_load_profile", return_value=coding_agent_config):
        agent = await factory.create_agent(profile="coding_agent")

    worker_tool = agent.tools.get("coding_worker")
    assert worker_tool is not None
    assert worker_tool.requires_approval is False
    assert worker_tool.supports_parallelism is True


@pytest.mark.asyncio
async def test_coding_agent_analyst_auto_approved(coding_agent_config, tmp_path):
    """coding_analyst with auto_approve=true has requires_approval=False."""
    factory = AgentFactory()

    with patch.object(factory, "_load_profile", return_value=coding_agent_config):
        agent = await factory.create_agent(profile="coding_agent")

    analyst_tool = agent.tools.get("coding_analyst")
    assert analyst_tool is not None
    assert analyst_tool.requires_approval is False
    assert analyst_tool.supports_parallelism is True


@pytest.mark.asyncio
async def test_coding_agent_reviewer_requires_approval(coding_agent_config, tmp_path):
    """coding_reviewer without auto_approve keeps requires_approval=True."""
    factory = AgentFactory()

    with patch.object(factory, "_load_profile", return_value=coding_agent_config):
        agent = await factory.create_agent(profile="coding_agent")

    reviewer_tool = agent.tools.get("coding_reviewer")
    assert reviewer_tool is not None
    assert reviewer_tool.requires_approval is True


# ---------------------------------------------------------------------------
# Tests: Parallel dispatch via ParallelAgentTool (end-to-end with mock spawner)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parallel_dispatch_runs_concurrently():
    """Verify multiple missions execute concurrently (not sequentially)."""
    timestamps: list[tuple[str, float]] = []
    lock = asyncio.Lock()

    class TimingSpawner:
        """Records start/end times to prove concurrency."""

        async def spawn(self, spec: SubAgentSpec) -> SubAgentResult:
            start = asyncio.get_event_loop().time()
            async with lock:
                timestamps.append((f"{spec.mission}-start", start))
            await asyncio.sleep(0.05)  # Simulate work
            end = asyncio.get_event_loop().time()
            async with lock:
                timestamps.append((f"{spec.mission}-end", end))
            return SubAgentResult(
                session_id=f"session-{spec.mission}",
                status="completed",
                success=True,
                final_message=f"Done: {spec.mission}",
            )

    tool = ParallelAgentTool(
        sub_agent_spawner=TimingSpawner(),
        profile="dev",
        default_max_concurrency=3,
    )

    missions = [
        {"mission": "A", "specialist": "coding_worker"},
        {"mission": "B", "specialist": "coding_worker"},
        {"mission": "C", "specialist": "coding_worker"},
    ]
    result = await tool.execute(missions=missions, _parent_session_id="parent-test")

    assert result["success"] is True
    assert result["total"] == 3
    assert result["succeeded"] == 3

    # Prove concurrency: all start times should be close together.
    # If sequential, total time would be ≥0.15s. With concurrency, ≈0.05s.
    starts = [t for label, t in timestamps if label.endswith("-start")]
    ends = [t for label, t in timestamps if label.endswith("-end")]
    total_elapsed = max(ends) - min(starts)
    assert total_elapsed < 0.12, (
        f"Expected concurrent execution (<0.12s), got {total_elapsed:.3f}s"
    )


@pytest.mark.asyncio
async def test_parallel_dispatch_aggregates_partial_failures():
    """Verify partial failures are reported without cancelling siblings."""

    class PartialFailSpawner:
        _count = 0

        async def spawn(self, spec: SubAgentSpec) -> SubAgentResult:
            self._count += 1
            if self._count == 2:
                raise RuntimeError("Worker 2 crashed")
            return SubAgentResult(
                session_id=f"session-{self._count}",
                status="completed",
                success=True,
                final_message=f"Done #{self._count}",
            )

    tool = ParallelAgentTool(
        sub_agent_spawner=PartialFailSpawner(),
        profile="dev",
        default_max_concurrency=3,
    )

    missions = [{"mission": f"Task {i}"} for i in range(3)]
    result = await tool.execute(missions=missions, _parent_session_id="parent-test")

    assert result["success"] is False
    assert result["succeeded"] == 2
    assert result["failed"] == 1

    failed = [r for r in result["results"] if not r.get("success")]
    assert len(failed) == 1
    assert "Worker 2 crashed" in failed[0]["error"]


@pytest.mark.asyncio
async def test_parallel_dispatch_session_hierarchy():
    """Parent session ID propagates to all sub-agent specs."""
    captured_specs: list[SubAgentSpec] = []

    class CapturingSpawner:
        async def spawn(self, spec: SubAgentSpec) -> SubAgentResult:
            captured_specs.append(spec)
            return SubAgentResult(
                session_id=f"child-{len(captured_specs)}",
                status="completed",
                success=True,
                final_message="OK",
            )

    tool = ParallelAgentTool(
        sub_agent_spawner=CapturingSpawner(),
        profile="dev",
    )

    missions = [
        {"mission": "A", "specialist": "coding_worker"},
        {"mission": "B", "specialist": "coding_analyst"},
    ]
    await tool.execute(missions=missions, _parent_session_id="orchestrator-abc")

    assert len(captured_specs) == 2
    for spec in captured_specs:
        assert spec.parent_session_id == "orchestrator-abc"


# ---------------------------------------------------------------------------
# Tests: SubAgentTool parallel eligibility (auto_approve gate)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_approve_satisfies_parallel_gate():
    """With auto_approve, SubAgentTool passes the parallel execution gate check."""
    from taskforce.infrastructure.tools.orchestration import AgentTool

    factory = MagicMock()
    spawner = MagicMock()

    agent_tool = AgentTool(
        agent_factory=factory,
        sub_agent_spawner=spawner,
        auto_approve=True,
    )
    sub_tool = SubAgentTool(
        agent_tool=agent_tool,
        specialist="coding_worker",
        name="coding_worker",
        auto_approve=True,
    )

    # Simulate the parallel gate check from _execute_tool_calls
    can_parallel = (
        getattr(sub_tool, "supports_parallelism", False)
        and not sub_tool.requires_approval
    )
    assert can_parallel is True


@pytest.mark.asyncio
async def test_default_approval_blocks_parallel_gate():
    """Without auto_approve, SubAgentTool blocks the parallel gate."""
    from taskforce.infrastructure.tools.orchestration import AgentTool

    factory = MagicMock()
    spawner = MagicMock()

    agent_tool = AgentTool(
        agent_factory=factory,
        sub_agent_spawner=spawner,
        auto_approve=False,
    )
    sub_tool = SubAgentTool(
        agent_tool=agent_tool,
        specialist="coding_reviewer",
        name="coding_reviewer",
        auto_approve=False,
    )

    can_parallel = (
        getattr(sub_tool, "supports_parallelism", False)
        and not sub_tool.requires_approval
    )
    assert can_parallel is False
