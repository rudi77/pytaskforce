"""Tests for auto_approve behavior on SubAgentTool and AgentTool."""

from __future__ import annotations

from unittest.mock import MagicMock

from taskforce.infrastructure.tools.orchestration.agent_tool import AgentTool
from taskforce.infrastructure.tools.orchestration.sub_agent_tool import SubAgentTool


def _make_agent_tool(*, auto_approve: bool = False) -> AgentTool:
    """Create AgentTool with minimal mocked dependencies."""
    factory = MagicMock()
    return AgentTool(
        agent_factory=factory,
        auto_approve=auto_approve,
    )


def _make_sub_agent_tool(*, auto_approve: bool = False) -> SubAgentTool:
    """Create SubAgentTool with minimal mocked dependencies."""
    agent_tool = _make_agent_tool(auto_approve=auto_approve)
    return SubAgentTool(
        agent_tool=agent_tool,
        specialist="coding_worker",
        name="coding_worker",
        auto_approve=auto_approve,
    )


class TestAgentToolAutoApprove:
    """Tests for AgentTool auto_approve flag."""

    def test_requires_approval_default(self) -> None:
        """By default, AgentTool requires approval."""
        tool = _make_agent_tool()
        assert tool.requires_approval is True

    def test_requires_approval_with_auto_approve(self) -> None:
        """When auto_approve is True, approval is not required."""
        tool = _make_agent_tool(auto_approve=True)
        assert tool.requires_approval is False

    def test_supports_parallelism_always_true(self) -> None:
        """AgentTool always supports parallelism."""
        tool = _make_agent_tool()
        assert tool.supports_parallelism is True

    def test_auto_approve_enables_parallel_execution(self) -> None:
        """auto_approve=True makes the tool eligible for parallel execution.

        The parallel execution gate in _execute_tool_calls checks:
            supports_parallelism=True AND requires_approval=False
        """
        tool = _make_agent_tool(auto_approve=True)
        assert tool.supports_parallelism is True
        assert tool.requires_approval is False


class TestSubAgentToolAutoApprove:
    """Tests for SubAgentTool auto_approve flag."""

    def test_requires_approval_default(self) -> None:
        """By default, SubAgentTool requires approval."""
        tool = _make_sub_agent_tool()
        assert tool.requires_approval is True

    def test_requires_approval_with_auto_approve(self) -> None:
        """When auto_approve is True, approval is not required."""
        tool = _make_sub_agent_tool(auto_approve=True)
        assert tool.requires_approval is False

    def test_supports_parallelism_always_true(self) -> None:
        """SubAgentTool always supports parallelism."""
        tool = _make_sub_agent_tool()
        assert tool.supports_parallelism is True

    def test_auto_approve_enables_parallel_execution(self) -> None:
        """auto_approve=True makes the tool eligible for parallel execution."""
        tool = _make_sub_agent_tool(auto_approve=True)
        assert tool.supports_parallelism is True
        assert tool.requires_approval is False
