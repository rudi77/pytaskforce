"""Tests for SubAgentSpawner tool_overrides functionality."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskforce.application.sub_agent_spawner import SubAgentSpawner
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
