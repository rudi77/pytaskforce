"""Tests for SubAgentSpawner tool_overrides functionality."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskforce.application.sub_agent_spawner import SubAgentSpawner
from taskforce.core.domain.enums import EventType, ExecutionStatus
from taskforce.core.domain.models import StreamEvent
from taskforce.core.domain.sub_agents import SubAgentSpec
from taskforce.core.interfaces.tools import ApprovalRiskLevel


# ---------------------------------------------------------------------------
# Minimal fake tool that satisfies ToolProtocol
# ---------------------------------------------------------------------------


class FakeTool:
    """Minimal ToolProtocol stub for testing tool_overrides."""

    def __init__(self, tool_name: str) -> None:
        self._name = tool_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Fake {self._name} tool"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.NONE

    @property
    def supports_parallelism(self) -> bool:
        return False

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        return {"success": True}

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        return True, None


# ---------------------------------------------------------------------------
# Fake agent returned by the factory
# ---------------------------------------------------------------------------


@dataclass
class FakeExecutionResult:
    status: str = "completed"
    final_message: str = "done"


class FakeAgent:
    """Minimal agent stub with mutable tool attributes."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {"original": MagicMock()}
        self._openai_tools: list[dict] = []
        self._planner: Any = MagicMock()
        self._base_system_prompt: str = ""
        self.max_steps: int = 30
        self.tool_executor: Any = MagicMock()
        self.logger: Any = MagicMock()
        self.message_history_manager = MagicMock()
        self.message_history_manager._openai_tools = []
        self.prompt_builder = MagicMock()

    async def execute(self, mission: str, session_id: str) -> FakeExecutionResult:
        return FakeExecutionResult()

    async def execute_stream(
        self, mission: str, session_id: str
    ) -> AsyncIterator[StreamEvent]:
        # Minimal stream: a final answer followed by a COMPLETE event so
        # ``run_sub_agent_with_forwarding`` records a successful outcome.
        yield StreamEvent(
            event_type=EventType.FINAL_ANSWER,
            data={"content": "done"},
        )
        yield StreamEvent(
            event_type=EventType.COMPLETE,
            data={
                "status": ExecutionStatus.COMPLETED.value,
                "final_message": "done",
                "session_id": session_id,
            },
        )

    async def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestToolOverrides:
    """Tests for SubAgentSpawner.tool_overrides."""

    @pytest.fixture
    def fake_factory(self) -> MagicMock:
        factory = MagicMock()
        factory.config_dir = "/tmp/configs"
        factory.create_agent = AsyncMock(return_value=FakeAgent())
        return factory

    @pytest.fixture
    def sandbox_tools(self) -> list[FakeTool]:
        return [FakeTool("shell"), FakeTool("edit")]

    async def test_tool_overrides_replaces_agent_tools(
        self, fake_factory: MagicMock, sandbox_tools: list[FakeTool]
    ) -> None:
        """When tool_overrides is set, spawned agent tools are replaced."""
        spawner = SubAgentSpawner(
            agent_factory=fake_factory,
            tool_overrides=sandbox_tools,
        )

        spec = SubAgentSpec(
            mission="fix the bug",
            parent_session_id="parent-123",
        )

        result = await spawner.spawn(spec)
        assert result.success

        # Verify the agent's tools were replaced
        agent: FakeAgent = fake_factory.create_agent.return_value
        assert set(agent.tools.keys()) == {"shell", "edit"}
        assert agent._planner is None

    async def test_no_tool_overrides_keeps_original_tools(
        self, fake_factory: MagicMock
    ) -> None:
        """When tool_overrides is None, agent tools are unchanged."""
        spawner = SubAgentSpawner(
            agent_factory=fake_factory,
        )

        spec = SubAgentSpec(
            mission="fix the bug",
            parent_session_id="parent-123",
        )

        result = await spawner.spawn(spec)
        assert result.success

        # Verify tools were NOT replaced
        agent: FakeAgent = fake_factory.create_agent.return_value
        assert "original" in agent.tools

    async def test_tool_overrides_updates_openai_tools(
        self, fake_factory: MagicMock, sandbox_tools: list[FakeTool]
    ) -> None:
        """tool_overrides also updates _openai_tools and message_history_manager."""
        spawner = SubAgentSpawner(
            agent_factory=fake_factory,
            tool_overrides=sandbox_tools,
        )

        spec = SubAgentSpec(
            mission="fix the bug",
            parent_session_id="parent-123",
        )

        await spawner.spawn(spec)

        agent: FakeAgent = fake_factory.create_agent.return_value
        # _openai_tools should be a list of dicts (one per tool)
        assert len(agent._openai_tools) == 2
        tool_names = {t["function"]["name"] for t in agent._openai_tools}
        assert tool_names == {"shell", "edit"}


class TestSpecialistResolution:
    """Verify the spawner refuses to silently fall back to the parent profile.

    Regression: butler delegating to ``coding_agent`` used to recurse into
    butler-spawning-butler because ``_find_agent_config`` only searched
    ``custom/`` directories, while ``coding_agent.yaml`` lives at the
    package's top-level configs/ — causing infinite recursion.
    """

    @pytest.fixture
    def fake_factory(self, tmp_path) -> MagicMock:
        factory = MagicMock()
        factory.config_dir = str(tmp_path / "configs")
        (tmp_path / "configs").mkdir()
        factory.create_agent = AsyncMock(return_value=FakeAgent())
        return factory

    async def test_unresolvable_specialist_raises_instead_of_using_parent(
        self, fake_factory: MagicMock
    ) -> None:
        """Specialist that cannot be resolved must raise, not silently
        spawn the parent profile (which causes infinite recursion)."""
        spawner = SubAgentSpawner(
            agent_factory=fake_factory,
            profile="butler",
        )

        spec = SubAgentSpec(
            mission="please write a file",
            parent_session_id="parent-123",
            specialist="totally_unknown_specialist",
        )

        result = await spawner.spawn(spec)
        # Spawn catches the ValueError internally and returns a failed result
        assert not result.success
        assert "No agent config found" in (result.error or "")
        # And critically: agent_factory.create_agent must NOT have been called
        # with the parent profile as a fallback
        fake_factory.create_agent.assert_not_called()

    async def test_top_level_package_profile_is_resolved(
        self, fake_factory: MagicMock
    ) -> None:
        """Specialist matching a top-level package profile (e.g. coding_agent.yaml)
        must be found, not fall through to the parent profile."""
        with patch(
            "taskforce.application.sub_agent_spawner.SubAgentSpawner._find_agent_config"
        ) as mock_find:
            from pathlib import Path as _P

            mock_find.return_value = _P("/fake/agents/coding-agent/configs/coding_agent.yaml")

            spawner = SubAgentSpawner(
                agent_factory=fake_factory,
                profile="butler",
            )

            spec = SubAgentSpec(
                mission="write a skill file",
                parent_session_id="parent-123",
                specialist="coding_agent",
            )

            result = await spawner.spawn(spec)
            assert result.success
            # Must have used the resolved specialist config, not the parent profile
            create_kwargs = fake_factory.create_agent.call_args.kwargs
            assert create_kwargs["config"] == str(
                _P("/fake/agents/coding-agent/configs/coding_agent.yaml")
            )


class _RecoveringAgent(FakeAgent):
    """Emits a transient ERROR (with content_filter kind) followed by a
    successful FINAL_ANSWER and COMPLETE.

    Models the "first LLM call blocked, recovery on stripped history
    succeeded" path. The spawner must not leak the transient error_kind
    into the SubAgentResult — a successful outcome must report
    ``error=None, error_kind=None``.
    """

    async def execute_stream(
        self, mission: str, session_id: str
    ) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(
            event_type=EventType.ERROR,
            data={
                "message": "LLM call rejected (content_filter): ...",
                "error_kind": "content_filter",
                "non_retryable": True,
            },
        )
        yield StreamEvent(
            event_type=EventType.FINAL_ANSWER,
            data={"content": "recovered answer"},
        )
        yield StreamEvent(
            event_type=EventType.COMPLETE,
            data={
                "status": ExecutionStatus.COMPLETED.value,
                "final_message": "recovered answer",
                "session_id": session_id,
            },
        )


@pytest.mark.asyncio
async def test_successful_outcome_clears_transient_error_kind() -> None:
    """A transient mid-run ERROR must not bleed into a successful result."""
    factory = MagicMock()
    factory.config_dir = "/tmp/configs"
    factory.create_agent = AsyncMock(return_value=_RecoveringAgent())

    spawner = SubAgentSpawner(agent_factory=factory)
    spec = SubAgentSpec(mission="research X", parent_session_id="p")

    result = await spawner.spawn(spec)

    assert result.success is True
    assert result.final_message == "recovered answer"
    # Both error fields must be cleared on success — otherwise the
    # parent agent would see a stale "content_filter" tag and react as
    # if the specialist had failed.
    assert result.error is None
    assert result.error_kind is None
