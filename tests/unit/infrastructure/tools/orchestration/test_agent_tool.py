"""Tests for AgentTool result summarization behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from taskforce.infrastructure.tools.orchestration.agent_tool import AgentTool


def _make_tool(*, summarize_results: bool, summary_max_length: int = 20) -> AgentTool:
    """Create AgentTool with minimal mocked dependencies."""
    factory = MagicMock()
    return AgentTool(
        agent_factory=factory,
        summarize_results=summarize_results,
        summary_max_length=summary_max_length,
    )


def test_format_spawner_result_truncates_when_enabled() -> None:
    """Spawner results are truncated when summarize_results is enabled."""
    tool = _make_tool(summarize_results=True, summary_max_length=12)
    result = SimpleNamespace(
        success=True,
        final_message="abcdefghijklmnopqrstuvwxyz",
        session_id="s1",
        status="completed",
        error=None,
    )

    payload = tool._format_spawner_result(result)

    assert payload["success"] is True
    assert payload["result"].startswith("abcdefghijkl")
    assert "[Result truncated" in payload["result"]


def test_format_spawner_result_keeps_full_text_when_disabled() -> None:
    """Spawner results stay unchanged when summarize_results is disabled."""
    tool = _make_tool(summarize_results=False, summary_max_length=12)
    result = SimpleNamespace(
        success=True,
        final_message="abcdefghijklmnopqrstuvwxyz",
        session_id="s2",
        status="completed",
        error=None,
    )

    payload = tool._format_spawner_result(result)

    assert payload["result"] == "abcdefghijklmnopqrstuvwxyz"
