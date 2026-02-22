"""
Unit tests for ToolRegistry (Mapper Functionality)
===================================================

Tests the tool name to full tool definition mapping.
"""


from taskforce.application.tool_registry import ToolRegistry, get_tool_registry


class TestToolRegistry:
    """Test suite for ToolRegistry mapper functionality."""

    def test_map_tools_single(self):
        """Test mapping a single tool name."""
        registry = ToolRegistry()
        tools = registry.map_tools(["web_search"])

        assert len(tools) == 1
        assert tools[0]["type"] == "WebSearchTool"
        assert tools[0]["module"] == "taskforce.infrastructure.tools.native.web_tools"
        assert tools[0]["params"] == {}

    def test_map_tools_multiple(self):
        """Test mapping multiple tool names."""
        registry = ToolRegistry()
        tools = registry.map_tools(["web_search", "python", "file_read"])

        assert len(tools) == 3
        assert tools[0]["type"] == "WebSearchTool"
        assert tools[1]["type"] == "PythonTool"
        assert tools[2]["type"] == "FileReadTool"

    def test_map_tools_empty(self):
        """Test mapping empty tool list."""
        registry = ToolRegistry()
        tools = registry.map_tools([])

        assert len(tools) == 0

    def test_map_tools_unknown(self):
        """Test mapping unknown tool names (should be skipped)."""
        registry = ToolRegistry()
        tools = registry.map_tools(["web_search", "unknown_tool", "python"])

        # Unknown tools are skipped
        assert len(tools) == 2
        assert tools[0]["type"] == "WebSearchTool"
        assert tools[1]["type"] == "PythonTool"

    def test_map_tools_llm_with_params(self):
        """Test mapping LLM tool includes default params."""
        registry = ToolRegistry()
        tools = registry.map_tools(["llm"])

        assert len(tools) == 1
        assert tools[0]["type"] == "LLMTool"
        assert tools[0]["params"]["model_alias"] == "main"

    def test_get_tool_name(self):
        """Test getting tool name from tool type."""
        registry = ToolRegistry()

        assert registry.get_tool_name("WebSearchTool") == "web_search"
        assert registry.get_tool_name("PythonTool") == "python"
        assert registry.get_tool_name("FileReadTool") == "file_read"
        assert registry.get_tool_name("UnknownTool") is None

    def test_get_tool_registry_returns_instance(self):
        """Test that get_tool_registry returns an instance."""
        registry1 = get_tool_registry()
        registry2 = get_tool_registry()

        assert isinstance(registry1, ToolRegistry)
        assert isinstance(registry2, ToolRegistry)

    def test_all_tools_defined(self):
        """Test that all expected tools are defined."""
        registry = ToolRegistry()
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
            tools = registry.map_tools([tool_name])
            assert len(tools) == 1, f"Tool {tool_name} not found"
            assert "type" in tools[0]
            assert "module" in tools[0]
            assert "params" in tools[0]

    def test_tool_definitions_immutable(self):
        """Test that tool definitions are copied (not shared references)."""
        registry = ToolRegistry()
        tools1 = registry.map_tools(["web_search"])
        tools2 = registry.map_tools(["web_search"])

        # Modify first result
        tools1[0]["params"]["test"] = "value"

        # Second result should not be affected
        assert "test" not in tools2[0]["params"]
