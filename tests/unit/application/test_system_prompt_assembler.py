"""Tests for SystemPromptAssembler."""

from __future__ import annotations

from unittest.mock import MagicMock

from taskforce.application.system_prompt_assembler import SystemPromptAssembler
from taskforce.core.prompts.autonomous_prompts import LEAN_KERNEL_PROMPT


def _make_mock_tool(name: str = "test_tool", description: str = "A test tool") -> MagicMock:
    """Create a mock tool with required attributes."""
    tool = MagicMock()
    tool.name = name
    tool.description = description
    tool.parameters_schema = {"type": "object", "properties": {}}
    return tool


class TestSystemPromptAssembler:
    """Tests for the system prompt assembler."""

    def test_basic_assembly_includes_kernel(self) -> None:
        """Assembled prompt should contain the kernel prompt."""
        assembler = SystemPromptAssembler()
        prompt = assembler.assemble(tools=[])
        assert LEAN_KERNEL_PROMPT in prompt

    def test_coding_specialist(self) -> None:
        """Coding specialist prompt content should be present."""
        assembler = SystemPromptAssembler()
        prompt = assembler.assemble(tools=[], specialist="coding")
        # Check for distinctive content from the coding specialist prompt
        assert "Senior Software Engineer" in prompt

    def test_rag_specialist(self) -> None:
        """RAG specialist prompt content should be present."""
        assembler = SystemPromptAssembler()
        prompt = assembler.assemble(tools=[], specialist="rag")
        assert "RAG Specialist" in prompt

    def test_wiki_specialist(self) -> None:
        """Wiki specialist prompt content should be present."""
        assembler = SystemPromptAssembler()
        prompt = assembler.assemble(tools=[], specialist="wiki")
        assert "DevOps Wiki Assistant" in prompt

    def test_unknown_specialist_ignored(self) -> None:
        """Unknown specialist key should not add any extra content."""
        assembler = SystemPromptAssembler()
        prompt_none = assembler.assemble(tools=[])
        prompt_unknown = assembler.assemble(tools=[], specialist="nonexistent")
        assert prompt_none == prompt_unknown

    def test_custom_prompt_appended(self) -> None:
        """Custom prompt should appear in assembled result."""
        assembler = SystemPromptAssembler()
        custom = "You are a specialized helper for data analysis."
        prompt = assembler.assemble(tools=[], custom_prompt=custom)
        assert custom in prompt
        assert LEAN_KERNEL_PROMPT in prompt

    def test_custom_prompt_overrides_specialist(self) -> None:
        """When custom_prompt is given, specialist should NOT be added."""
        assembler = SystemPromptAssembler()
        prompt = assembler.assemble(
            tools=[],
            specialist="coding",
            custom_prompt="Custom instructions",
        )
        # Custom prompt takes priority — coding specialist should NOT be present
        assert "Custom instructions" in prompt
        assert "Senior Software Engineer" not in prompt

    def test_tools_included_in_prompt(self) -> None:
        """Tool descriptions should appear in the assembled prompt."""
        assembler = SystemPromptAssembler()
        tool = _make_mock_tool("my_search", "Search for things")
        prompt = assembler.assemble(tools=[tool])
        assert "my_search" in prompt

    def test_no_tools_no_crash(self) -> None:
        """Empty tools list should not cause an error."""
        assembler = SystemPromptAssembler()
        prompt = assembler.assemble(tools=[])
        assert isinstance(prompt, str)
        assert len(prompt) > 0
