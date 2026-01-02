"""
Unit tests for Story 4.1: System-Prompt Optimization & llm_generate Elimination.

Tests verify:
- Optimized prompt contains critical performance rules
- Standard agent excludes llm_generate tool by default
- RAG agent can opt-in to llm_generate via config
"""

from unittest.mock import MagicMock

import pytest

from taskforce.application.factory import AgentFactory
from taskforce.core.prompts.autonomous_prompts import GENERAL_AUTONOMOUS_KERNEL_PROMPT


class TestOptimizedPromptContent:
    """Tests for optimized system prompt content."""

    def test_prompt_contains_you_are_the_generator_rule(self):
        """Verify the optimized prompt contains 'YOU ARE THE GENERATOR' rule."""
        assert "YOU ARE THE GENERATOR" in GENERAL_AUTONOMOUS_KERNEL_PROMPT

    def test_prompt_contains_memory_first_rule(self):
        """Verify the optimized prompt contains 'MEMORY FIRST' rule."""
        assert "MEMORY FIRST" in GENERAL_AUTONOMOUS_KERNEL_PROMPT

    def test_prompt_mentions_llm_generate_prohibition(self):
        """Verify the prompt mentions llm_generate as forbidden."""
        assert "llm_generate" in GENERAL_AUTONOMOUS_KERNEL_PROMPT

    def test_prompt_contains_finish_step_instruction(self):
        """Verify the prompt contains finish_step instruction."""
        assert "finish_step" in GENERAL_AUTONOMOUS_KERNEL_PROMPT

    def test_prompt_contains_summary_field_guidance(self):
        """Verify the prompt emphasizes using summary field for direct answers."""
        assert "summary" in GENERAL_AUTONOMOUS_KERNEL_PROMPT.lower()
        # Verify it's in the context of the action schema
        assert '"summary"' in GENERAL_AUTONOMOUS_KERNEL_PROMPT

    def test_prompt_contains_previous_results_check(self):
        """Verify the prompt instructs checking PREVIOUS_RESULTS before tool calls."""
        assert "PREVIOUS_RESULTS" in GENERAL_AUTONOMOUS_KERNEL_PROMPT

    def test_prompt_contains_conversation_history_check(self):
        """Verify the prompt instructs checking CONVERSATION_HISTORY before tool calls."""
        assert "CONVERSATION_HISTORY" in GENERAL_AUTONOMOUS_KERNEL_PROMPT


class TestDefaultToolsExcludeLlmGenerate:
    """Tests for llm_generate exclusion from default tools."""

    def test_default_tools_exclude_llm_generate(self):
        """Verify _create_default_tools() does not include llm_generate."""
        factory = AgentFactory(config_dir="configs")
        mock_llm = MagicMock()

        tools = factory._create_default_tools(mock_llm)

        tool_names = [tool.name for tool in tools]
        assert "llm_generate" not in tool_names, (
            "llm_generate should be excluded from default tools"
        )

    def test_default_tools_count_is_nine(self):
        """Verify default tools has 9 tools (not 10)."""
        factory = AgentFactory(config_dir="configs")
        mock_llm = MagicMock()

        tools = factory._create_default_tools(mock_llm)

        # 9 tools: web_search, web_fetch, python, github, git,
        #          file_read, file_write, powershell, ask_user
        assert len(tools) == 9

    def test_default_tools_contains_expected_tools(self):
        """Verify default tools contains all expected tools (except llm_generate)."""
        factory = AgentFactory(config_dir="configs")
        mock_llm = MagicMock()

        tools = factory._create_default_tools(mock_llm)

        tool_names = [tool.name for tool in tools]
        expected_tools = [
            "web_search",
            "web_fetch",
            "python",
            "github",
            "git",
            "file_read",
            "file_write",
            "powershell",
            "ask_user",
        ]

        for expected in expected_tools:
            assert expected in tool_names, f"Tool {expected} not found in {tool_names}"


class TestLlmGenerateConfigFiltering:
    """Tests for include_llm_generate config flag filtering."""

    def test_native_tools_filter_llm_generate_by_default(self):
        """Verify _create_native_tools() filters llm_generate when not explicitly enabled."""
        factory = AgentFactory(config_dir="configs")
        mock_llm = MagicMock()

        # Config with llm_generate in tools but NO include_llm_generate flag
        config = {
            "tools": [
                {"type": "PythonTool", "module": "taskforce.infrastructure.tools.native.python_tool"},
                {"type": "LLMTool", "module": "taskforce.infrastructure.tools.native.llm_tool"},
                {"type": "FileReadTool", "module": "taskforce.infrastructure.tools.native.file_tools"},
            ]
        }

        tools = factory._create_native_tools(config, mock_llm)

        tool_names = [tool.name for tool in tools]
        assert "llm_generate" not in tool_names, (
            "llm_generate should be filtered out when include_llm_generate is not set"
        )
        assert "python" in tool_names
        assert "file_read" in tool_names

    def test_native_tools_include_llm_generate_when_enabled(self):
        """Verify _create_native_tools() includes llm_generate when explicitly enabled."""
        factory = AgentFactory(config_dir="configs")
        mock_llm = MagicMock()

        # Config with include_llm_generate: true
        config = {
            "agent": {"include_llm_generate": True},
            "tools": [
                {"type": "PythonTool", "module": "taskforce.infrastructure.tools.native.python_tool"},
                {"type": "LLMTool", "module": "taskforce.infrastructure.tools.native.llm_tool"},
            ]
        }

        tools = factory._create_native_tools(config, mock_llm)

        tool_names = [tool.name for tool in tools]
        assert "llm_generate" in tool_names, (
            "llm_generate should be included when include_llm_generate is True"
        )

    def test_native_tools_explicit_false_filters_llm_generate(self):
        """Verify _create_native_tools() filters llm_generate when explicitly set to False."""
        factory = AgentFactory(config_dir="configs")
        mock_llm = MagicMock()

        # Config with include_llm_generate: false explicitly
        config = {
            "agent": {"include_llm_generate": False},
            "tools": [
                {"type": "PythonTool", "module": "taskforce.infrastructure.tools.native.python_tool"},
                {"type": "LLMTool", "module": "taskforce.infrastructure.tools.native.llm_tool"},
            ]
        }

        tools = factory._create_native_tools(config, mock_llm)

        tool_names = [tool.name for tool in tools]
        assert "llm_generate" not in tool_names


class TestAgentCreationWithOptimization:
    """Tests for agent creation with the optimizations."""

    @pytest.mark.asyncio
    async def test_standard_agent_has_no_llm_generate(self):
        """Verify standard agent created via factory excludes llm_generate."""
        factory = AgentFactory(config_dir="configs")

        agent = await factory.create_agent(profile="dev")

        tool_names = list(agent.tools.keys())
        assert "llm_generate" not in tool_names, (
            "Standard agent should not have llm_generate tool"
        )

    @pytest.mark.asyncio
    async def test_agent_system_prompt_has_performance_rules(self):
        """Verify agent's system prompt contains the performance rules."""
        factory = AgentFactory(config_dir="configs")

        agent = await factory.create_agent(profile="dev")

        assert "YOU ARE THE GENERATOR" in agent.system_prompt
        assert "MEMORY FIRST" in agent.system_prompt

