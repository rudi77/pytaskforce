"""
Unit tests for Web Tools

Tests WebSearchTool and WebFetchTool functionality.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from taskforce.infrastructure.tools.native.web_tools import (
    WebFetchTool,
    WebSearchTool,
)


class TestWebSearchTool:
    """Test suite for WebSearchTool."""

    @pytest.fixture
    def tool(self):
        """Create a WebSearchTool instance."""
        return WebSearchTool()

    def test_tool_metadata(self, tool):
        """Test tool metadata properties."""
        assert tool.name == "web_search"
        assert "Search the web" in tool.description
        assert tool.requires_approval is False

    def test_parameters_schema(self, tool):
        """Test parameter schema structure."""
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert "num_results" in schema["properties"]
        assert "query" in schema["required"]

    @pytest.mark.asyncio
    async def test_search_with_results(self, tool):
        """Test web search with mock results."""
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(
            return_value={
                "Abstract": "Test abstract",
                "Heading": "Test heading",
                "AbstractURL": "https://example.com",
                "RelatedTopics": [
                    {
                        "Text": "Topic 1 - Description",
                        "FirstURL": "https://example.com/1",
                    },
                    {
                        "Text": "Topic 2 - Description",
                        "FirstURL": "https://example.com/2",
                    },
                ],
            }
        )

        with patch("aiohttp.ClientSession") as mock_session:
            mock_get = AsyncMock()
            mock_get.__aenter__.return_value = mock_response
            mock_session.return_value.__aenter__.return_value.get.return_value = mock_get

            result = await tool.execute(query="test query", num_results=3)

            assert result["success"] is True
            assert result["query"] == "test query"
            assert len(result["results"]) > 0
            assert "count" in result

    @pytest.mark.asyncio
    async def test_search_error_handling(self, tool):
        """Test error handling during search."""
        with patch("aiohttp.ClientSession") as mock_session:
            mock_session.return_value.__aenter__.return_value.get.side_effect = (
                Exception("Network error")
            )

            result = await tool.execute(query="test query")

            assert result["success"] is False
            assert "error" in result

    def test_validate_params_success(self, tool):
        """Test parameter validation with valid params."""
        valid, error = tool.validate_params(query="test")

        assert valid is True
        assert error is None

    def test_validate_params_missing_query(self, tool):
        """Test parameter validation with missing query."""
        valid, error = tool.validate_params()

        assert valid is False
        assert "query" in error


class TestWebFetchTool:
    """Test suite for WebFetchTool."""

    @pytest.fixture
    def tool(self):
        """Create a WebFetchTool instance."""
        return WebFetchTool()

    def test_tool_metadata(self, tool):
        """Test tool metadata properties."""
        assert tool.name == "web_fetch"
        assert "Fetch and extract content" in tool.description
        assert tool.requires_approval is False

    def test_parameters_schema(self, tool):
        """Test parameter schema structure."""
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "url" in schema["properties"]
        assert "url" in schema["required"]

    @pytest.mark.asyncio
    async def test_fetch_html_content(self, tool):
        """Test fetching HTML content."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.text = AsyncMock(
            return_value="<html><body><p>Test content</p></body></html>"
        )

        with patch("aiohttp.ClientSession") as mock_session:
            mock_get = AsyncMock()
            mock_get.__aenter__.return_value = mock_response
            mock_session.return_value.__aenter__.return_value.get.return_value = mock_get

            result = await tool.execute(url="https://example.com")

            assert result["success"] is True
            assert result["url"] == "https://example.com"
            assert result["status"] == 200
            assert "Test content" in result["content"]

    @pytest.mark.asyncio
    async def test_fetch_plain_text(self, tool):
        """Test fetching plain text content."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "text/plain"}
        mock_response.text = AsyncMock(return_value="Plain text content")

        with patch("aiohttp.ClientSession") as mock_session:
            mock_get = AsyncMock()
            mock_get.__aenter__.return_value = mock_response
            mock_session.return_value.__aenter__.return_value.get.return_value = mock_get

            result = await tool.execute(url="https://example.com/file.txt")

            assert result["success"] is True
            assert "Plain text content" in result["content"]

    @pytest.mark.asyncio
    async def test_fetch_timeout(self, tool):
        """Test timeout handling."""
        import asyncio

        with patch("aiohttp.ClientSession") as mock_session:
            mock_get = AsyncMock()
            mock_get.__aenter__.side_effect = asyncio.TimeoutError()
            mock_session.return_value.__aenter__.return_value.get.return_value = mock_get

            result = await tool.execute(url="https://example.com")

            assert result["success"] is False
            assert "timed out" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_fetch_error_handling(self, tool):
        """Test general error handling."""
        with patch("aiohttp.ClientSession") as mock_session:
            mock_session.return_value.__aenter__.return_value.get.side_effect = (
                Exception("Connection error")
            )

            result = await tool.execute(url="https://example.com")

            assert result["success"] is False
            assert "error" in result

    def test_validate_params_success(self, tool):
        """Test parameter validation with valid params."""
        valid, error = tool.validate_params(url="https://example.com")

        assert valid is True
        assert error is None

    def test_validate_params_missing_url(self, tool):
        """Test parameter validation with missing URL."""
        valid, error = tool.validate_params()

        assert valid is False
        assert "url" in error

