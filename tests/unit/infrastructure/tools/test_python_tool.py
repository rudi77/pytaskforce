"""
Unit tests for PythonTool

Tests isolated namespace execution, context handling, error recovery,
parameter validation, and tool-bridge integration.
"""

import pytest
from unittest.mock import AsyncMock, Mock

from taskforce.infrastructure.tools.native.python_tool import PythonTool
from taskforce.infrastructure.tools.native.tool_bridge import ToolBridge


class TestPythonTool:
    """Test suite for PythonTool."""

    @pytest.fixture
    def tool(self):
        """Create a PythonTool instance."""
        return PythonTool()

    def test_tool_metadata(self, tool):
        """Test tool metadata properties."""
        assert tool.name == "python"
        assert "Execute Python code" in tool.description
        assert "parameters_schema" in dir(tool)
        assert tool.requires_approval is True

    def test_parameters_schema(self, tool):
        """Test parameter schema structure."""
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "code" in schema["properties"]
        assert "context" in schema["properties"]
        assert "cwd" in schema["properties"]
        assert "code" in schema["required"]

    @pytest.mark.asyncio
    async def test_basic_execution(self, tool):
        """Test basic Python code execution."""
        result = await tool.execute(code="result = 2 + 2")

        assert result["success"] is True
        assert result["result"] == 4

    @pytest.mark.asyncio
    async def test_isolated_namespace(self, tool):
        """Verify variables don't persist between calls."""
        # First call sets x
        await tool.execute(code="x = 100; result = x")

        # Second call tries to use x - should fail
        result = await tool.execute(code="result = x")

        assert result["success"] is False
        assert "NameError" in result["type"]
        assert "not defined" in result["error"]

    @pytest.mark.asyncio
    async def test_context_parameter(self, tool):
        """Test context parameter exposes variables."""
        result = await tool.execute(code="result = data * 2", context={"data": 10})

        assert result["success"] is True
        assert result["result"] == 20

    @pytest.mark.asyncio
    async def test_missing_result_variable(self, tool):
        """Test error when 'result' variable is not set."""
        result = await tool.execute(code="x = 5")

        assert result["success"] is False
        assert "result" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_syntax_error(self, tool):
        """Test handling of syntax errors."""
        result = await tool.execute(code="result = 2 +")

        assert result["success"] is False
        assert "SyntaxError" in result["type"]

    @pytest.mark.asyncio
    async def test_import_error(self, tool):
        """Test handling of import errors."""
        result = await tool.execute(code="import nonexistent_module; result = 1")

        assert result["success"] is False
        assert "ImportError" in result["type"] or "ModuleNotFoundError" in result["type"]

    @pytest.mark.asyncio
    async def test_pre_imported_modules(self, tool):
        """Test that common modules are pre-imported."""
        result = await tool.execute(code="result = json.dumps({'test': 'value'})")

        assert result["success"] is True
        assert '"test"' in result["result"]

    @pytest.mark.asyncio
    async def test_pathlib_support(self, tool):
        """Test pathlib Path support."""
        result = await tool.execute(code="result = str(Path('test.txt'))")

        assert result["success"] is True
        assert "test.txt" in result["result"]

    @pytest.mark.asyncio
    async def test_error_hints_name_error(self, tool):
        """Test that helpful hints are provided for NameError."""
        result = await tool.execute(code="result = undefined_var")

        assert result["success"] is False
        assert "hints" in result
        assert len(result["hints"]) > 0
        assert any("ISOLATED namespace" in hint for hint in result["hints"])

    @pytest.mark.asyncio
    async def test_variables_returned(self, tool):
        """Test that user-defined variable names are returned."""
        result = await tool.execute(code="x = 10; y = 20; result = x + y")

        assert result["success"] is True
        assert "variables" in result
        # variables is a list of names (not values) to save tokens
        assert "x" in result["variables"]
        assert "y" in result["variables"]
        assert "result" in result["variables"]

    @pytest.mark.asyncio
    async def test_cwd_parameter(self, tool, tmp_path):
        """Test working directory parameter."""
        # Create a temp file in tmp_path
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        result = await tool.execute(code="result = open('test.txt').read()", cwd=str(tmp_path))

        assert result["success"] is True
        assert "test content" in result["result"]

    @pytest.mark.asyncio
    async def test_invalid_cwd(self, tool):
        """Test error handling for invalid working directory."""
        result = await tool.execute(code="result = 1", cwd="/nonexistent/directory")

        assert result["success"] is False
        assert "does not exist" in result["error"]

    def test_validate_params_success(self, tool):
        """Test parameter validation with valid params."""
        valid, error = tool.validate_params(code="result = 1")

        assert valid is True
        assert error is None

    def test_validate_params_missing_code(self, tool):
        """Test parameter validation with missing code."""
        valid, error = tool.validate_params()

        assert valid is False
        assert "code" in error

    def test_validate_params_invalid_type(self, tool):
        """Test parameter validation with invalid type."""
        valid, error = tool.validate_params(code=123)

        assert valid is False
        assert "string" in error

    @pytest.mark.asyncio
    async def test_sanitize_output(self, tool):
        """Test that outputs are sanitized for JSON/pickle safety."""
        result = await tool.execute(code="from pathlib import Path; result = Path('/test/path')")

        assert result["success"] is True
        assert isinstance(result["result"], str)

    @pytest.mark.asyncio
    async def test_list_comprehension(self, tool):
        """Test list comprehension execution."""
        result = await tool.execute(code="result = [x * 2 for x in range(5)]")

        assert result["success"] is True
        assert result["result"] == [0, 2, 4, 6, 8]

    @pytest.mark.asyncio
    async def test_dictionary_operations(self, tool):
        """Test dictionary operations."""
        result = await tool.execute(code="data = {'a': 1, 'b': 2}; result = data['a'] + data['b']")

        assert result["success"] is True
        assert result["result"] == 3


class TestToolBridge:
    """Tests for ToolBridge standalone functionality."""

    def _make_mock_tool(self, name: str, return_value: dict):
        """Create a mock ToolProtocol with async execute."""
        tool = Mock()
        tool.name = name
        tool.execute = AsyncMock(return_value=return_value)
        return tool

    def test_excludes_python_and_ask_user(self):
        """python and ask_user are excluded from the bridge."""
        tools = {
            "python": self._make_mock_tool("python", {}),
            "ask_user": self._make_mock_tool("ask_user", {}),
            "file_read": self._make_mock_tool("file_read", {"success": True}),
        }
        bridge = ToolBridge(tools=tools)
        assert bridge.available_tool_names == ["file_read"]

    def test_get_namespace_keys(self):
        """Namespace keys follow the tool_<name> pattern."""
        tools = {
            "file_read": self._make_mock_tool("file_read", {}),
            "shell": self._make_mock_tool("shell", {}),
        }
        bridge = ToolBridge(tools=tools)
        ns = bridge.get_namespace()
        assert "tool_file_read" in ns
        assert "tool_shell" in ns
        assert callable(ns["tool_file_read"])

    def test_description_suffix(self):
        """Description suffix lists bridged tools."""
        tools = {
            "file_read": self._make_mock_tool("file_read", {}),
            "web_search": self._make_mock_tool("web_search", {}),
        }
        bridge = ToolBridge(tools=tools)
        suffix = bridge.description_suffix()
        assert "tool_file_read" in suffix
        assert "tool_web_search" in suffix
        assert "Tool chaining" in suffix


class TestPythonToolWithBridge:
    """Tests for PythonTool with ToolBridge injected."""

    def _make_mock_tool(self, name: str, return_value: dict):
        tool = Mock()
        tool.name = name
        tool.execute = AsyncMock(return_value=return_value)
        return tool

    @pytest.fixture
    def bridge_tool(self):
        """PythonTool with a mock file_read bridge."""
        mock_file_read = self._make_mock_tool(
            "file_read", {"success": True, "output": "file contents"}
        )
        bridge = ToolBridge(tools={"file_read": mock_file_read})
        return PythonTool(tool_bridge=bridge)

    def test_description_includes_bridge(self, bridge_tool):
        """Description mentions tool chaining when bridge is present."""
        assert "Tool chaining" in bridge_tool.description
        assert "tool_file_read" in bridge_tool.description

    def test_description_without_bridge(self):
        """Description has no bridge suffix when no bridge is set."""
        tool = PythonTool()
        assert "Tool chaining" not in tool.description

    @pytest.mark.asyncio
    async def test_bridge_function_accessible(self, bridge_tool):
        """Bridge functions are accessible in the execution namespace."""
        # tool_file_read should be in scope and not raise NameError
        result = await bridge_tool.execute(code="result = str(tool_file_read)")
        assert result["success"] is True
        assert "function" in result["result"]

    @pytest.mark.asyncio
    async def test_bridge_call_invokes_tool(self, bridge_tool):
        """Calling a bridge function invokes the underlying tool."""
        # With loop=None, the bridge uses asyncio.run() which works from
        # a sync context (inside exec) since exec runs in the main thread
        # and there's no running loop inside exec.
        result = await bridge_tool.execute(
            code="r = tool_file_read(path='test.txt'); result = r['output']"
        )
        assert result["success"] is True
        assert result["result"] == "file contents"
