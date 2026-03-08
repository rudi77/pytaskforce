"""Regression tests for coding profile behavior."""

from __future__ import annotations

from taskforce.application.infrastructure_builder import InfrastructureBuilder


def test_coding_analysis_profile_exists_and_is_read_only() -> None:
    builder = InfrastructureBuilder()
    profile = builder.load_profile("coding_analysis")
    tools = profile.get("tools", [])
    assert "file_read" in tools
    assert "grep" in tools
    assert "glob" in tools
    assert "file_write" not in tools
    assert "edit" not in tools
    assert "coding_worker" not in tools


def test_coding_agent_prompt_enforces_analysis_mode() -> None:
    builder = InfrastructureBuilder()
    profile = builder.load_profile("coding_agent")
    system_prompt = profile.get("system_prompt", "")
    assert "ANALYSIS MODE" in system_prompt
    assert "Do NOT call coding_worker" in system_prompt
