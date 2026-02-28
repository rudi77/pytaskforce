"""Tests for AgentTool dynamic specialist description."""

from __future__ import annotations

from unittest.mock import MagicMock

from taskforce.infrastructure.tools.orchestration.agent_tool import AgentTool


def _make_factory() -> MagicMock:
    """Create a mock AgentFactory."""
    factory = MagicMock()
    factory.config_dir = MagicMock()
    return factory


class TestAgentToolDescription:
    """Tests for AgentTool description property."""

    def test_description_with_specialist_index(self) -> None:
        """Description includes specialist index when provided."""
        index = "- `coding` - Code expert\n- `rag` - RAG expert"
        tool = AgentTool(
            agent_factory=_make_factory(),
            specialist_index=index,
        )
        desc = tool.description
        assert "coding" in desc
        assert "rag" in desc
        assert "Available specialists:" in desc

    def test_description_without_specialist_index(self) -> None:
        """Description uses static fallback when no index provided."""
        tool = AgentTool(agent_factory=_make_factory())
        desc = tool.description
        assert "'coding'" in desc
        assert "'rag'" in desc
        assert "'wiki'" in desc

    def test_description_with_none_index(self) -> None:
        """Explicitly passing None falls back to static description."""
        tool = AgentTool(
            agent_factory=_make_factory(),
            specialist_index=None,
        )
        desc = tool.description
        assert "'coding'" in desc

    def test_tool_name(self) -> None:
        """Tool name is always 'call_agent'."""
        tool = AgentTool(agent_factory=_make_factory())
        assert tool.name == "call_agent"

    def test_supports_parallelism(self) -> None:
        """AgentTool supports parallel execution."""
        tool = AgentTool(agent_factory=_make_factory())
        assert tool.supports_parallelism is True
