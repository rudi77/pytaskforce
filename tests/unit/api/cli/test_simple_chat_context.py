"""Tests for /context command in SimpleChatRunner."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from rich.console import Console

from taskforce.api.cli.simple_chat import SimpleChatRunner
from taskforce.application.context_display_service import ContextSnapshot, ContextSection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _DummyAgent:
    """Minimal agent stub that satisfies SimpleChatRunner."""

    def __init__(self) -> None:
        self.state_manager = MagicMock()
        self.state_manager.load_state = AsyncMock(return_value={"conversation_history": []})
        self.token_budgeter = MagicMock()
        self.token_budgeter.max_input_tokens = 100_000
        self.model_alias = "main"
        self._openai_tools = []
        self.tools = {}

    def _build_system_prompt(self, **kwargs) -> str:
        return "<Base>\nYou are helpful.\n</Base>"

    async def close(self) -> None:
        pass


def _build_runner(agent: _DummyAgent | None = None) -> SimpleChatRunner:
    runner = SimpleChatRunner(
        session_id="test-session",
        profile="dev",
        agent=agent or _DummyAgent(),
        stream=True,
        user_context=None,
    )
    runner.console = Console(record=True, width=120)
    return runner


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_command_dispatches() -> None:
    """``/context`` should call _show_context and not exit."""
    runner = _build_runner()
    should_exit = await runner._handle_command("/context")
    assert should_exit is False


@pytest.mark.asyncio
async def test_ctx_alias_dispatches() -> None:
    """``/ctx`` should also dispatch to context display."""
    runner = _build_runner()
    should_exit = await runner._handle_command("/ctx")
    assert should_exit is False


@pytest.mark.asyncio
async def test_context_renders_output() -> None:
    """``/context`` should produce Rich output containing key sections."""
    runner = _build_runner()

    await runner._show_context()

    output = runner.console.export_text()
    assert "Context Snapshot" in output
    assert "System Prompt" in output


@pytest.mark.asyncio
async def test_context_without_agent() -> None:
    """``/context`` should warn when no agent is active."""
    runner = _build_runner()
    runner.agent = None

    await runner._show_context()

    output = runner.console.export_text()
    assert "No agent" in output


def test_render_context_snapshot() -> None:
    """_render_context_snapshot should produce a Rich panel with tree."""
    runner = _build_runner()

    snapshot = ContextSnapshot(
        sections=[
            ContextSection(name="System Prompt", content="...", token_estimate=500, subsections=[]),
            ContextSection(
                name="Conversation History (2 messages)",
                content="2 messages",
                token_estimate=300,
                subsections=[],
            ),
            ContextSection(
                name="Tool Definitions (3 tools)",
                content="3 tool schemas",
                token_estimate=200,
                subsections=[],
            ),
        ],
        total_tokens=1000,
        max_tokens=100_000,
        utilization_pct=1.0,
        model_alias="gpt-4o",
    )

    runner._render_context_snapshot(snapshot)

    output = runner.console.export_text()
    assert "System Prompt" in output
    assert "1,000" in output  # total tokens formatted
    assert "gpt-4o" in output


def test_help_includes_context_command() -> None:
    """Help text should mention /context."""
    runner = _build_runner()
    runner._show_help()

    output = runner.console.export_text()
    assert "/context" in output
