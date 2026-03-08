"""Unit tests for planning helper utility functions."""

from __future__ import annotations

from taskforce.core.domain.planning_helpers import _is_no_progress_tool_output


def test_detects_no_progress_markers() -> None:
    assert _is_no_progress_tool_output("rg: 0 matches in 10 files")
    assert _is_no_progress_tool_output("No files found")
    assert _is_no_progress_tool_output("tool failed: not found")


def test_ignores_regular_informative_output() -> None:
    assert not _is_no_progress_tool_output("Updated src/taskforce/api/cli/commands/chat.py")
    assert not _is_no_progress_tool_output("Found 4 matches in 2 files")
