"""
Unit tests for MCP Client

Tests MCPClient connection management and tool execution with mocked MCP sessions.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskforce.infrastructure.tools.mcp.client import MCPClient


class TestMCPClient:
    """Test suite for MCPClient."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock MCP ClientSession."""
        session = AsyncMock()
        session.initialize = AsyncMock()
        return session

    @pytest.fixture
    def mock_tool_response(self):
        """Create a mock tool list response."""
        tool1 = MagicMock()
        tool1.name = "test_tool"
        tool1.description = "A test tool"
        tool1.inputSchema = {"type": "object", "properties": {"param": {"type": "string"}}}

        tool2 = MagicMock()
        tool2.name = "another_tool"
        tool2.description = "Another test tool"
        tool2.inputSchema = {"type": "object", "properties": {}}

        response = MagicMock()
        response.tools = [tool1, tool2]
        return response

    @pytest.mark.asyncio
    async def test_list_tools(self, mock_session, mock_tool_response):
        """Test listing tools from MCP server."""
        mock_session.list_tools = AsyncMock(return_value=mock_tool_response)

        client = MCPClient(mock_session, None, None)
        tools = await client.list_tools()

        assert len(tools) == 2
        assert tools[0]["name"] == "test_tool"
        assert tools[0]["description"] == "A test tool"
        assert "param" in tools[0]["input_schema"]["properties"]
        assert tools[1]["name"] == "another_tool"

    @pytest.mark.asyncio
    async def test_list_tools_caching(self, mock_session, mock_tool_response):
        """Test that tool list is cached after first call."""
        mock_session.list_tools = AsyncMock(return_value=mock_tool_response)

        client = MCPClient(mock_session, None, None)

        # First call
        tools1 = await client.list_tools()
        # Second call
        tools2 = await client.list_tools()

        # Should only call the session once
        mock_session.list_tools.assert_called_once()
        assert tools1 == tools2

    @pytest.mark.asyncio
    async def test_call_tool_success(self, mock_session):
        """Test successful tool execution."""
        # Mock tool response with content
        mock_content_item = MagicMock()
        mock_content_item.text = "Tool execution result"

        mock_response = MagicMock()
        mock_response.content = [mock_content_item]

        mock_session.call_tool = AsyncMock(return_value=mock_response)

        client = MCPClient(mock_session, None, None)
        result = await client.call_tool("test_tool", {"param": "value"})

        assert result["success"] is True
        assert "Tool execution result" in result["result"]
        mock_session.call_tool.assert_called_once_with("test_tool", {"param": "value"})

    @pytest.mark.asyncio
    async def test_call_tool_with_data_content(self, mock_session):
        """Test tool execution with data content."""
        # Mock tool response with data content
        mock_content_item = MagicMock()
        mock_content_item.data = {"key": "value"}
        delattr(mock_content_item, "text")  # Remove text attribute

        mock_response = MagicMock()
        mock_response.content = [mock_content_item]

        mock_session.call_tool = AsyncMock(return_value=mock_response)

        client = MCPClient(mock_session, None, None)
        result = await client.call_tool("test_tool", {"param": "value"})

        assert result["success"] is True
        assert "key" in result["result"]

    @pytest.mark.asyncio
    async def test_call_tool_failure(self, mock_session):
        """Test tool execution with error."""
        mock_session.call_tool = AsyncMock(side_effect=Exception("Tool execution failed"))

        client = MCPClient(mock_session, None, None)
        result = await client.call_tool("test_tool", {"param": "value"})

        assert result["success"] is False
        assert "Tool execution failed" in result["error"]
        assert result["error_type"] == "Exception"

    @pytest.mark.asyncio
    async def test_call_tool_empty_content(self, mock_session):
        """Test tool execution with empty content."""
        mock_response = MagicMock()
        mock_response.content = []

        mock_session.call_tool = AsyncMock(return_value=mock_response)

        client = MCPClient(mock_session, None, None)
        result = await client.call_tool("test_tool", {})

        assert result["success"] is True
        assert "result" in result

    @pytest.mark.asyncio
    async def test_close(self, mock_session):
        """Test client close method."""
        client = MCPClient(mock_session, None, None)
        await client.close()
        # Close is a no-op, just verify it doesn't raise

    @pytest.mark.asyncio
    @patch("taskforce.infrastructure.tools.mcp.client.stdio_client")
    @patch("taskforce.infrastructure.tools.mcp.client.ClientSession")
    async def test_create_stdio_context_manager(self, mock_session_class, mock_stdio_client):
        """Test stdio client creation via context manager."""
        # Setup mocks
        mock_read = MagicMock()
        mock_write = MagicMock()
        mock_stdio_client.return_value.__aenter__.return_value = (mock_read, mock_write)

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session_class.return_value.__aenter__.return_value = mock_session

        # Use the context manager
        async with MCPClient.create_stdio("python", ["server.py"]) as client:
            assert isinstance(client, MCPClient)
            assert client.session == mock_session

        # Verify initialization was called
        mock_session.initialize.assert_called_once()

    @pytest.mark.asyncio
    @patch("taskforce.infrastructure.tools.mcp.client.sse_client")
    @patch("taskforce.infrastructure.tools.mcp.client.ClientSession")
    async def test_create_sse_context_manager(self, mock_session_class, mock_sse_client):
        """Test SSE client creation via context manager."""
        # Setup mocks
        mock_read = MagicMock()
        mock_write = MagicMock()
        mock_sse_client.return_value.__aenter__.return_value = (mock_read, mock_write)

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session_class.return_value.__aenter__.return_value = mock_session

        # Use the context manager
        async with MCPClient.create_sse("http://localhost:8000/sse") as client:
            assert isinstance(client, MCPClient)
            assert client.session == mock_session

        # Verify initialization was called
        mock_session.initialize.assert_called_once()

