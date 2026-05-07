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
        error_kind=None,
    )

    payload = tool._format_spawner_result(result)

    assert payload["result"] == "abcdefghijklmnopqrstuvwxyz"


def test_format_spawner_result_propagates_error_kind_on_failure() -> None:
    """Failed sub-agent results must carry error_kind so the parent agent
    knows *why* the specialist died (e.g. content_filter)."""
    tool = _make_tool(summarize_results=False)
    result = SimpleNamespace(
        success=False,
        final_message="",
        session_id="s3",
        status="failed",
        error="LLM call rejected (content_filter): Azure ContentPolicyViolationError",
        error_kind="content_filter",
    )

    payload = tool._format_spawner_result(result)

    assert payload["success"] is False
    assert payload["error_kind"] == "content_filter"
    assert "content_filter" in payload["error"]


def test_format_spawner_result_clears_error_kind_on_success() -> None:
    """Even when SubAgentResult somehow carries a stale error_kind, a
    successful outcome must report ``error_kind=None`` to the parent."""
    tool = _make_tool(summarize_results=False)
    result = SimpleNamespace(
        success=True,
        final_message="recovered answer",
        session_id="s4",
        status="completed",
        error="leftover error text",
        error_kind="content_filter",
    )

    payload = tool._format_spawner_result(result)

    assert payload["success"] is True
    assert payload["error"] is None
    assert payload["error_kind"] is None
