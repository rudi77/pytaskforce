"""
Unit tests for ToolMapper
==========================

Tests the tool name to full tool definition mapping.
"""

import pytest

from taskforce.application.tool_mapper import ToolMapper, get_tool_mapper


class TestToolMapper:
    """Test suite for ToolMapper."""

    def test_map_tools_single(self):
        """Test mapping a single tool name."""
        mapper = ToolMapper()
        tools = mapper.map_tools(["web_search"])

        assert len(tools) == 1
        assert tools[0]["type"] == "WebSearchTool"
        assert tools[0]["module"] == "taskforce.infrastructure.tools.native.web_tools"
        assert tools[0]["params"] == {}

    def test_map_tools_multiple(self):
        """Test mapping multiple tool names."""
        mapper = ToolMapper()
        tools = mapper.map_tools(["web_search", "python", "file_read"])

        assert len(tools) == 3
        assert tools[0]["type"] == "WebSearchTool"
        assert tools[1]["type"] == "PythonTool"
        assert tools[2]["type"] == "FileReadTool"

    def test_map_tools_empty(self):
        """Test mapping empty tool list."""
        mapper = ToolMapper()
        tools = mapper.map_tools([])

        assert len(tools) == 0

    def test_map_tools_unknown(self):
        """Test mapping unknown tool names (should be skipped)."""
        mapper = ToolMapper()
        tools = mapper.map_tools(["web_search", "unknown_tool", "python"])

        # Unknown tools are skipped
        assert len(tools) == 2
        assert tools[0]["type"] == "WebSearchTool"
        assert tools[1]["type"] == "PythonTool"

    def test_map_tools_llm_with_params(self):
        """Test mapping LLM tool includes default params."""
        mapper = ToolMapper()
        tools = mapper.map_tools(["llm"])

        assert len(tools) == 1
        assert tools[0]["type"] == "LLMTool"
        assert tools[0]["params"]["model_alias"] == "main"

    def test_get_tool_name(self):
        """Test getting tool name from tool type."""
        mapper = ToolMapper()

        assert mapper.get_tool_name("WebSearchTool") == "web_search"
        assert mapper.get_tool_name("PythonTool") == "python"
        assert mapper.get_tool_name("FileReadTool") == "file_read"
        assert mapper.get_tool_name("UnknownTool") is None

    def test_get_tool_mapper_singleton(self):
        """Test singleton instance."""
        mapper1 = get_tool_mapper()
        mapper2 = get_tool_mapper()

        assert mapper1 is mapper2

    def test_all_tools_defined(self):
        """Test that all expected tools are defined."""
        mapper = ToolMapper()
        expected_tools = [
            "web_search",
            "web_fetch",
            "python",
            "file_read",
            "file_write",
            "git",
            "github",
            "powershell",
            "ask_user",
            "llm",
        ]

        for tool_name in expected_tools:
            tools = mapper.map_tools([tool_name])
            assert len(tools) == 1, f"Tool {tool_name} not found"
            assert "type" in tools[0]
            assert "module" in tools[0]
            assert "params" in tools[0]

    def test_tool_definitions_immutable(self):
        """Test that tool definitions are copied (not shared references)."""
        mapper = ToolMapper()
        tools1 = mapper.map_tools(["web_search"])
        tools2 = mapper.map_tools(["web_search"])

        # Modify first result
        tools1[0]["params"]["test"] = "value"

        # Second result should not be affected
        assert "test" not in tools2[0]["params"]

