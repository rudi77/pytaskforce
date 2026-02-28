"""Tests for ContextDisplayService."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from taskforce.application.context_display_service import (
    CHARS_PER_TOKEN,
    ContextDisplayService,
    ContextSection,
    ContextSnapshot,
    ContextSubsection,
    _estimate_tokens,
    _extract_xml_section,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent(
    system_prompt: str = "<Base>\nYou are helpful.\n</Base>",
    tools: list | None = None,
    openai_tools: list | None = None,
    history: list | None = None,
    max_input_tokens: int = 100_000,
    model_alias: str = "main",
) -> MagicMock:
    """Create a minimal mock agent for snapshot building."""
    agent = MagicMock()
    agent._build_system_prompt = MagicMock(return_value=system_prompt)
    agent.model_alias = model_alias

    # Token budgeter
    budgeter = MagicMock()
    budgeter.max_input_tokens = max_input_tokens
    agent.token_budgeter = budgeter

    # State manager
    state = {"conversation_history": history or []}
    agent.state_manager = MagicMock()
    agent.state_manager.load_state = AsyncMock(return_value=state)

    # Tools
    agent._openai_tools = openai_tools or []
    agent.tools = {}

    return agent


# ---------------------------------------------------------------------------
# Unit tests: helpers
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    def test_empty_string(self) -> None:
        assert _estimate_tokens("") == 0

    def test_simple_string(self) -> None:
        text = "Hello, world!"  # 13 chars -> 3 tokens
        assert _estimate_tokens(text) == len(text) // CHARS_PER_TOKEN

    def test_long_string(self) -> None:
        text = "a" * 400  # 400 chars -> 100 tokens
        assert _estimate_tokens(text) == 100


class TestExtractXmlSection:
    def test_extracts_content(self) -> None:
        text = "<Base>\nSome content\n</Base>"
        result = _extract_xml_section(text, "Base")
        assert result == "Some content"

    def test_returns_none_for_missing_tag(self) -> None:
        text = "<Base>\nSome content\n</Base>"
        result = _extract_xml_section(text, "Mission")
        assert result is None

    def test_multiline_content(self) -> None:
        text = "<ToolsDescription>\nLine 1\nLine 2\nLine 3\n</ToolsDescription>"
        result = _extract_xml_section(text, "ToolsDescription")
        assert "Line 1" in result
        assert "Line 3" in result


# ---------------------------------------------------------------------------
# Integration tests: build_snapshot
# ---------------------------------------------------------------------------


class TestContextDisplayService:
    @pytest.mark.asyncio
    async def test_build_snapshot_returns_snapshot(self) -> None:
        agent = _make_agent()
        service = ContextDisplayService()

        snapshot = await service.build_snapshot(agent, "session-1")

        assert isinstance(snapshot, ContextSnapshot)
        assert len(snapshot.sections) == 3  # system prompt, history, tools

    @pytest.mark.asyncio
    async def test_snapshot_contains_system_prompt_section(self) -> None:
        agent = _make_agent(system_prompt="<Base>\nKernel prompt here.\n</Base>")
        service = ContextDisplayService()

        snapshot = await service.build_snapshot(agent, "session-1")

        system_section = snapshot.sections[0]
        assert system_section.name == "System Prompt"
        assert system_section.token_estimate > 0

    @pytest.mark.asyncio
    async def test_snapshot_parses_base_subsection(self) -> None:
        agent = _make_agent(system_prompt="<Base>\nKernel prompt here.\n</Base>")
        service = ContextDisplayService()

        snapshot = await service.build_snapshot(agent, "session-1")

        system_section = snapshot.sections[0]
        base_subs = [s for s in system_section.subsections if s.name == "Base Kernel Prompt"]
        assert len(base_subs) == 1
        assert "Kernel prompt here" in base_subs[0].content

    @pytest.mark.asyncio
    async def test_snapshot_parses_tools_description_subsection(self) -> None:
        prompt = (
            "<Base>\nHello\n</Base>\n\n"
            "<ToolsDescription>\n"
            "Tool: file_read\nDescription: Read files\n\n"
            "Tool: python\nDescription: Run python\n"
            "</ToolsDescription>"
        )
        agent = _make_agent(system_prompt=prompt)
        service = ContextDisplayService()

        snapshot = await service.build_snapshot(agent, "session-1")

        system_section = snapshot.sections[0]
        td_subs = [s for s in system_section.subsections if "Tool Descriptions" in s.name]
        assert len(td_subs) == 1
        assert "2 tools" in td_subs[0].name

    @pytest.mark.asyncio
    async def test_snapshot_history_section(self) -> None:
        history = [
            {"role": "user", "content": "Hello there!"},
            {"role": "assistant", "content": "Hi! How can I help?"},
        ]
        agent = _make_agent(history=history)
        service = ContextDisplayService()

        snapshot = await service.build_snapshot(agent, "session-1")

        history_section = snapshot.sections[1]
        assert "2 messages" in history_section.name
        assert len(history_section.subsections) == 2
        assert "user" in history_section.subsections[0].name
        assert "assistant" in history_section.subsections[1].name

    @pytest.mark.asyncio
    async def test_snapshot_tool_definitions_section(self) -> None:
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": "file_read",
                    "description": "Read a file from disk",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "python",
                    "description": "Execute Python code",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]
        agent = _make_agent(openai_tools=openai_tools)
        service = ContextDisplayService()

        snapshot = await service.build_snapshot(agent, "session-1")

        tool_section = snapshot.sections[2]
        assert "2 tools" in tool_section.name
        assert len(tool_section.subsections) == 2
        names = {s.name for s in tool_section.subsections}
        assert "file_read" in names
        assert "python" in names

    @pytest.mark.asyncio
    async def test_snapshot_total_tokens_and_utilization(self) -> None:
        agent = _make_agent(max_input_tokens=10_000)
        service = ContextDisplayService()

        snapshot = await service.build_snapshot(agent, "session-1")

        assert snapshot.max_tokens == 10_000
        assert snapshot.total_tokens >= 0
        assert 0.0 <= snapshot.utilization_pct <= 100.0

    @pytest.mark.asyncio
    async def test_snapshot_empty_history(self) -> None:
        agent = _make_agent(history=[])
        service = ContextDisplayService()

        snapshot = await service.build_snapshot(agent, "session-1")

        history_section = snapshot.sections[1]
        assert "0 messages" in history_section.name
        assert len(history_section.subsections) == 0

    @pytest.mark.asyncio
    async def test_snapshot_no_tools(self) -> None:
        agent = _make_agent(openai_tools=[])
        service = ContextDisplayService()

        snapshot = await service.build_snapshot(agent, "session-1")

        tool_section = snapshot.sections[2]
        assert "0 tools" in tool_section.name

    @pytest.mark.asyncio
    async def test_snapshot_with_plan_status(self) -> None:
        prompt = (
            "<Base>\nHello\n</Base>\n\n"
            "## CURRENT PLAN STATUS\n"
            "1. [x] Step one\n"
            "2. [ ] Step two\n"
        )
        agent = _make_agent(system_prompt=prompt)
        service = ContextDisplayService()

        snapshot = await service.build_snapshot(agent, "session-1")

        system_section = snapshot.sections[0]
        plan_subs = [s for s in system_section.subsections if s.name == "Plan Status"]
        assert len(plan_subs) == 1
        assert "Step one" in plan_subs[0].content

    @pytest.mark.asyncio
    async def test_snapshot_with_active_skill(self) -> None:
        prompt = (
            "<Base>\nHello\n</Base>\n\n"
            "# ACTIVE SKILL: smart-booking\n"
            "Process invoices automatically with high confidence.\n"
        )
        agent = _make_agent(system_prompt=prompt)
        service = ContextDisplayService()

        snapshot = await service.build_snapshot(agent, "session-1")

        system_section = snapshot.sections[0]
        skill_subs = [s for s in system_section.subsections if "Active Skill" in s.name]
        assert len(skill_subs) == 1
        assert "smart-booking" in skill_subs[0].name

    @pytest.mark.asyncio
    async def test_snapshot_model_alias(self) -> None:
        agent = _make_agent(model_alias="gpt-4o")
        service = ContextDisplayService()

        snapshot = await service.build_snapshot(agent, "session-1")

        assert snapshot.model_alias == "gpt-4o"

    @pytest.mark.asyncio
    async def test_snapshot_tool_message_in_history(self) -> None:
        history = [
            {"role": "user", "content": "Read the file"},
            {"role": "assistant", "content": None},
            {"role": "tool", "name": "file_read", "content": '{"output": "data"}'},
        ]
        agent = _make_agent(history=history)
        service = ContextDisplayService()

        snapshot = await service.build_snapshot(agent, "session-1")

        history_section = snapshot.sections[1]
        assert len(history_section.subsections) == 3
        tool_sub = history_section.subsections[2]
        assert "tool:file_read" in tool_sub.name
