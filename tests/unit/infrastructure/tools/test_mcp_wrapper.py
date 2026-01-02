"""
Unit tests for MCP Tool Wrapper

Tests MCPToolWrapper adapter functionality with mocked MCPClient.
"""

from unittest.mock import AsyncMock

import pytest

from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.tools.mcp.wrapper import MCPToolWrapper


class TestMCPToolWrapper:
    """Test suite for MCPToolWrapper."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock MCPClient."""
        return AsyncMock()

    @pytest.fixture
    def tool_definition(self):
        """Create a sample MCP tool definition."""
        return {
            "name": "test_tool",
            "description": "A test tool for unit testing",
            "input_schema": {
                "type": "object",
                "properties": {
                    "param1": {
                        "type": "string",
                        "description": "First parameter",
                    },
                    "param2": {
                        "type": "integer",
                        "description": "Second parameter",
                    },
                },
                "required": ["param1"],
            },
        }

    @pytest.fixture
    def wrapper(self, mock_client, tool_definition):
        """Create an MCPToolWrapper instance."""
        return MCPToolWrapper(mock_client, tool_definition)

    def test_tool_metadata(self, wrapper):
        """Test tool metadata properties."""
        assert wrapper.name == "test_tool"
        assert "test tool" in wrapper.description.lower()
        assert wrapper.requires_approval is False
        assert wrapper.approval_risk_level == ApprovalRiskLevel.LOW

    def test_tool_metadata_with_custom_approval(self, mock_client, tool_definition):
        """Test tool metadata with custom approval settings."""
        wrapper = MCPToolWrapper(
            mock_client,
            tool_definition,
            requires_approval=True,
            risk_level=ApprovalRiskLevel.HIGH,
        )

        assert wrapper.requires_approval is True
        assert wrapper.approval_risk_level == ApprovalRiskLevel.HIGH

    def test_parameters_schema(self, wrapper):
        """Test parameter schema structure."""
        schema = wrapper.parameters_schema

        assert schema["type"] == "object"
        assert "param1" in schema["properties"]
        assert "param2" in schema["properties"]
        assert schema["properties"]["param1"]["type"] == "string"
        assert schema["properties"]["param2"]["type"] == "integer"
        assert "param1" in schema["required"]

    def test_parameters_schema_empty(self, mock_client):
        """Test parameter schema with empty input schema."""
        tool_def = {
            "name": "simple_tool",
            "description": "Simple tool",
            "input_schema": {},
        }
        wrapper = MCPToolWrapper(mock_client, tool_def)
        schema = wrapper.parameters_schema

        assert schema["type"] == "object"
        assert schema["properties"] == {}
        assert schema["required"] == []

    def test_parameters_schema_missing(self, mock_client):
        """Test parameter schema when input_schema is missing."""
        tool_def = {
            "name": "simple_tool",
            "description": "Simple tool",
        }
        wrapper = MCPToolWrapper(mock_client, tool_def)
        schema = wrapper.parameters_schema

        assert schema["type"] == "object"
        assert schema["properties"] == {}
        assert schema["required"] == []

    def test_get_approval_preview(self, wrapper):
        """Test approval preview generation."""
        preview = wrapper.get_approval_preview(param1="value1", param2=42)

        assert "test_tool" in preview
        assert "param1: value1" in preview
        assert "param2: 42" in preview

    @pytest.mark.asyncio
    async def test_execute_success(self, wrapper, mock_client):
        """Test successful tool execution."""
        mock_client.call_tool = AsyncMock(
            return_value={"success": True, "result": "Tool output"}
        )

        result = await wrapper.execute(param1="test", param2=123)

        assert result["success"] is True
        assert result["output"] == "Tool output"
        assert result["result"] == "Tool output"
        mock_client.call_tool.assert_called_once_with(
            "test_tool", {"param1": "test", "param2": 123}
        )

    @pytest.mark.asyncio
    async def test_execute_mcp_error(self, wrapper, mock_client):
        """Test tool execution with MCP error."""
        mock_client.call_tool = AsyncMock(
            return_value={
                "success": False,
                "error": "MCP server error",
                "error_type": "ServerError",
            }
        )

        result = await wrapper.execute(param1="test")

        assert result["success"] is False
        assert "MCP server error" in result["error"]
        assert result["error_type"] == "ServerError"

    @pytest.mark.asyncio
    async def test_execute_validation_error(self, wrapper, mock_client):
        """Test tool execution with validation error."""
        # Missing required parameter
        result = await wrapper.execute(param2=123)

        assert result["success"] is False
        assert "Missing required parameter: param1" in result["error"]
        assert result["error_type"] == "ValidationError"
        # Should not call MCP client
        mock_client.call_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_exception(self, wrapper, mock_client):
        """Test tool execution with exception."""
        mock_client.call_tool = AsyncMock(side_effect=Exception("Connection failed"))

        result = await wrapper.execute(param1="test")

        assert result["success"] is False
        assert "Connection failed" in result["error"]
        assert result["error_type"] == "Exception"

    def test_validate_params_success(self, wrapper):
        """Test parameter validation with valid params."""
        valid, error = wrapper.validate_params(param1="test", param2=123)

        assert valid is True
        assert error is None

    def test_validate_params_missing_required(self, wrapper):
        """Test parameter validation with missing required parameter."""
        valid, error = wrapper.validate_params(param2=123)

        assert valid is False
        assert "Missing required parameter: param1" in error

    def test_validate_params_wrong_type(self, wrapper):
        """Test parameter validation with wrong type."""
        valid, error = wrapper.validate_params(param1="test", param2="not_an_int")

        assert valid is False
        assert "param2" in error
        assert "integer" in error

    def test_validate_params_optional_missing(self, wrapper):
        """Test parameter validation with missing optional parameter."""
        valid, error = wrapper.validate_params(param1="test")

        assert valid is True
        assert error is None

    def test_validate_params_extra_params(self, wrapper):
        """Test parameter validation with extra parameters."""
        # Extra params should be allowed (MCP server will validate)
        valid, error = wrapper.validate_params(
            param1="test", param2=123, extra="value"
        )

        assert valid is True
        assert error is None

    def test_validate_params_type_checking(self, mock_client):
        """Test parameter validation for various types."""
        tool_def = {
            "name": "type_test_tool",
            "description": "Tool for testing type validation",
            "input_schema": {
                "type": "object",
                "properties": {
                    "str_param": {"type": "string"},
                    "int_param": {"type": "integer"},
                    "num_param": {"type": "number"},
                    "bool_param": {"type": "boolean"},
                    "obj_param": {"type": "object"},
                    "arr_param": {"type": "array"},
                },
                "required": [],
            },
        }
        wrapper = MCPToolWrapper(mock_client, tool_def)

        # Valid types
        valid, error = wrapper.validate_params(
            str_param="text",
            int_param=42,
            num_param=3.14,
            bool_param=True,
            obj_param={"key": "value"},
            arr_param=[1, 2, 3],
        )
        assert valid is True

        # Invalid string type
        valid, error = wrapper.validate_params(str_param=123)
        assert valid is False
        assert "str_param" in error

        # Invalid integer type
        valid, error = wrapper.validate_params(int_param="not_int")
        assert valid is False
        assert "int_param" in error

        # Number accepts both int and float
        valid, error = wrapper.validate_params(num_param=42)
        assert valid is True
        valid, error = wrapper.validate_params(num_param=3.14)
        assert valid is True

        # Invalid boolean type
        valid, error = wrapper.validate_params(bool_param="true")
        assert valid is False
        assert "bool_param" in error

        # Invalid object type
        valid, error = wrapper.validate_params(obj_param="not_object")
        assert valid is False
        assert "obj_param" in error

        # Invalid array type
        valid, error = wrapper.validate_params(arr_param="not_array")
        assert valid is False
        assert "arr_param" in error

