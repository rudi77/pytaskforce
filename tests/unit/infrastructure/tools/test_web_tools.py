"""
Unit tests for Web Tools

Tests WebSearchTool and WebFetchTool functionality with mocked aiohttp sessions.
Verifies SSRF validation integration, HTML stripping, error handling.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.tools.native.web_tools import WebFetchTool, WebSearchTool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_aiohttp_response(
    *,
    json_data=None,
    text_data="",
    status=200,
    content_type="text/html",
    raise_on_json=False,
):
    """Create a mock aiohttp response context manager."""
    response = AsyncMock()
    response.status = status
    response.headers = {"Content-Type": content_type}

    if raise_on_json:
        response.json = AsyncMock(side_effect=Exception("JSON parse error"))
    else:
        response.json = AsyncMock(return_value=json_data or {})

    response.text = AsyncMock(return_value=text_data)

    # Make it an async context manager
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=response)
    ctx.__aclose__ = AsyncMock()
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _mock_session(response_ctx):
    """Create a mock aiohttp.ClientSession as an async context manager."""
    session = MagicMock()
    session.get = MagicMock(return_value=response_ctx)

    session_ctx = AsyncMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    return session_ctx


# ---------------------------------------------------------------------------
# WebSearchTool tests
# ---------------------------------------------------------------------------


class TestWebSearchToolMetadata:
    """Test WebSearchTool metadata properties."""

    @pytest.fixture
    def tool(self):
        return WebSearchTool()

    def test_name(self, tool):
        assert tool.name == "web_search"

    def test_description(self, tool):
        assert "search" in tool.description.lower()

    def test_parameters_schema(self, tool):
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert "num_results" in schema["properties"]
        assert schema["required"] == ["query"]

    def test_requires_approval(self, tool):
        assert tool.requires_approval is False

    def test_approval_risk_level(self, tool):
        assert tool.approval_risk_level == ApprovalRiskLevel.LOW

    def test_supports_parallelism(self, tool):
        assert tool.supports_parallelism is True

    def test_get_approval_preview(self, tool):
        preview = tool.get_approval_preview(query="python tutorials", num_results=3)
        assert "python tutorials" in preview
        assert "3" in preview


class TestWebSearchToolValidation:
    """Test WebSearchTool parameter validation."""

    @pytest.fixture
    def tool(self):
        return WebSearchTool()

    def test_valid_params(self, tool):
        valid, error = tool.validate_params(query="test search")
        assert valid is True
        assert error is None

    def test_missing_query(self, tool):
        valid, error = tool.validate_params()
        assert valid is False
        assert "query" in error

    def test_non_string_query(self, tool):
        valid, error = tool.validate_params(query=42)
        assert valid is False
        assert "string" in error


class TestWebSearchToolExecution:
    """Test WebSearchTool execution with mocked aiohttp."""

    @pytest.fixture
    def tool(self):
        return WebSearchTool()

    async def test_search_with_abstract(self, tool):
        """Test search returning abstract result."""
        json_data = {
            "Abstract": "Python is a programming language.",
            "Heading": "Python",
            "AbstractURL": "https://en.wikipedia.org/wiki/Python",
            "RelatedTopics": [],
        }

        resp_ctx = _mock_aiohttp_response(json_data=json_data)
        session_ctx = _mock_session(resp_ctx)

        with patch("aiohttp.ClientSession", return_value=session_ctx):
            result = await tool.execute(query="python programming")

        assert result["success"] is True
        assert result["query"] == "python programming"
        assert result["count"] >= 1
        assert result["results"][0]["title"] == "Python"
        assert "programming language" in result["results"][0]["snippet"]

    async def test_search_with_related_topics(self, tool):
        """Test search returning related topics."""
        json_data = {
            "Abstract": "",
            "RelatedTopics": [
                {"Text": "Topic One - Description of topic one", "FirstURL": "https://example.com/1"},
                {"Text": "Topic Two - Description of topic two", "FirstURL": "https://example.com/2"},
                {"Text": "Topic Three - Description", "FirstURL": "https://example.com/3"},
            ],
        }

        resp_ctx = _mock_aiohttp_response(json_data=json_data)
        session_ctx = _mock_session(resp_ctx)

        with patch("aiohttp.ClientSession", return_value=session_ctx):
            result = await tool.execute(query="test", num_results=2)

        assert result["success"] is True
        assert len(result["results"]) <= 2

    async def test_search_empty_results(self, tool):
        """Test search with no results."""
        json_data = {"Abstract": "", "RelatedTopics": []}

        resp_ctx = _mock_aiohttp_response(json_data=json_data)
        session_ctx = _mock_session(resp_ctx)

        with patch("aiohttp.ClientSession", return_value=session_ctx):
            result = await tool.execute(query="xyznonexistentquery123")

        assert result["success"] is True
        assert result["count"] == 0
        assert result["results"] == []

    async def test_search_handles_exception(self, tool):
        """Test that network errors are handled gracefully."""
        with patch(
            "aiohttp.ClientSession",
            side_effect=Exception("Network error"),
        ):
            result = await tool.execute(query="test")

        assert result["success"] is False
        assert "error" in result

    async def test_search_skips_non_dict_related_topics(self, tool):
        """Test that non-dict related topics are skipped."""
        json_data = {
            "Abstract": "",
            "RelatedTopics": [
                "plain string entry",
                {"Text": "Valid topic", "FirstURL": "https://example.com"},
            ],
        }

        resp_ctx = _mock_aiohttp_response(json_data=json_data)
        session_ctx = _mock_session(resp_ctx)

        with patch("aiohttp.ClientSession", return_value=session_ctx):
            result = await tool.execute(query="test")

        assert result["success"] is True
        # Only the dict entry with "Text" should be included
        assert result["count"] == 1


# ---------------------------------------------------------------------------
# WebFetchTool tests
# ---------------------------------------------------------------------------


class TestWebFetchToolMetadata:
    """Test WebFetchTool metadata properties."""

    @pytest.fixture
    def tool(self):
        return WebFetchTool()

    def test_name(self, tool):
        assert tool.name == "web_fetch"

    def test_description(self, tool):
        assert "fetch" in tool.description.lower()

    def test_parameters_schema(self, tool):
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "url" in schema["properties"]
        assert schema["required"] == ["url"]

    def test_requires_approval(self, tool):
        assert tool.requires_approval is False

    def test_approval_risk_level(self, tool):
        assert tool.approval_risk_level == ApprovalRiskLevel.LOW

    def test_supports_parallelism(self, tool):
        assert tool.supports_parallelism is True

    def test_get_approval_preview(self, tool):
        preview = tool.get_approval_preview(url="https://example.com")
        assert "https://example.com" in preview


class TestWebFetchToolValidation:
    """Test WebFetchTool parameter validation."""

    @pytest.fixture
    def tool(self):
        return WebFetchTool()

    def test_valid_params(self, tool):
        valid, error = tool.validate_params(url="https://example.com")
        assert valid is True
        assert error is None

    def test_missing_url(self, tool):
        valid, error = tool.validate_params()
        assert valid is False
        assert "url" in error

    def test_non_string_url(self, tool):
        valid, error = tool.validate_params(url=123)
        assert valid is False
        assert "string" in error


class TestWebFetchToolExecution:
    """Test WebFetchTool execution with mocked aiohttp."""

    @pytest.fixture
    def tool(self):
        return WebFetchTool()

    async def test_fetch_html_content(self, tool):
        """Test fetching HTML content with tag stripping."""
        html = "<html><body><script>alert(1)</script><p>Hello World</p></body></html>"

        resp_ctx = _mock_aiohttp_response(
            text_data=html, content_type="text/html; charset=utf-8"
        )
        session_ctx = _mock_session(resp_ctx)

        with patch(
            "taskforce.infrastructure.tools.native.web_tools.validate_url_for_ssrf",
            return_value=(True, None),
        ):
            with patch("aiohttp.ClientSession", return_value=session_ctx):
                result = await tool.execute(url="https://example.com")

        assert result["success"] is True
        assert result["url"] == "https://example.com"
        assert result["status"] == 200
        assert "Hello World" in result["content"]
        # script tags should be stripped
        assert "alert" not in result["content"]
        assert "<script" not in result["content"]
        assert "text/html" in result["content_type"]

    async def test_fetch_plain_text(self, tool):
        """Test fetching plain text content."""
        text_content = "This is plain text response."

        resp_ctx = _mock_aiohttp_response(
            text_data=text_content, content_type="text/plain"
        )
        session_ctx = _mock_session(resp_ctx)

        with patch(
            "taskforce.infrastructure.tools.native.web_tools.validate_url_for_ssrf",
            return_value=(True, None),
        ):
            with patch("aiohttp.ClientSession", return_value=session_ctx):
                result = await tool.execute(url="https://example.com/data.txt")

        assert result["success"] is True
        assert result["content"] == text_content

    async def test_fetch_truncates_long_content(self, tool):
        """Test that content is truncated to 5000 characters."""
        long_text = "x" * 10000

        resp_ctx = _mock_aiohttp_response(
            text_data=long_text, content_type="text/plain"
        )
        session_ctx = _mock_session(resp_ctx)

        with patch(
            "taskforce.infrastructure.tools.native.web_tools.validate_url_for_ssrf",
            return_value=(True, None),
        ):
            with patch("aiohttp.ClientSession", return_value=session_ctx):
                result = await tool.execute(url="https://example.com/big")

        assert result["success"] is True
        assert len(result["content"]) == 5000
        assert result["length"] == 10000

    async def test_ssrf_blocked_url(self, tool):
        """Test that SSRF-blocked URLs are rejected before fetching."""
        with patch(
            "taskforce.infrastructure.tools.native.web_tools.validate_url_for_ssrf",
            return_value=(False, "URL resolves to private address 10.0.0.1"),
        ):
            result = await tool.execute(url="http://10.0.0.1/admin")

        assert result["success"] is False
        assert "private" in result["error"].lower()

    async def test_ssrf_blocks_localhost(self, tool):
        """Test that localhost URLs are blocked via SSRF validation."""
        with patch(
            "taskforce.infrastructure.tools.native.web_tools.validate_url_for_ssrf",
            return_value=(
                False,
                "URL resolves to private/reserved address 127.0.0.1.",
            ),
        ):
            result = await tool.execute(url="http://localhost/secret")

        assert result["success"] is False
        assert "error" in result

    async def test_fetch_timeout(self, tool):
        """Test timeout handling during fetch."""
        with patch(
            "taskforce.infrastructure.tools.native.web_tools.validate_url_for_ssrf",
            return_value=(True, None),
        ):
            with patch(
                "aiohttp.ClientSession",
                side_effect=TimeoutError("Request timed out"),
            ):
                result = await tool.execute(url="https://slow.example.com")

        assert result["success"] is False
        assert "error" in result

    async def test_fetch_network_error(self, tool):
        """Test network error handling."""
        with patch(
            "taskforce.infrastructure.tools.native.web_tools.validate_url_for_ssrf",
            return_value=(True, None),
        ):
            with patch(
                "aiohttp.ClientSession",
                side_effect=ConnectionError("Connection refused"),
            ):
                result = await tool.execute(url="https://down.example.com")

        assert result["success"] is False
        assert "error" in result

    async def test_fetch_strips_style_tags(self, tool):
        """Test that style tags are stripped from HTML."""
        html = "<html><head><style>body{color:red}</style></head><body>Content</body></html>"

        resp_ctx = _mock_aiohttp_response(
            text_data=html, content_type="text/html"
        )
        session_ctx = _mock_session(resp_ctx)

        with patch(
            "taskforce.infrastructure.tools.native.web_tools.validate_url_for_ssrf",
            return_value=(True, None),
        ):
            with patch("aiohttp.ClientSession", return_value=session_ctx):
                result = await tool.execute(url="https://example.com")

        assert result["success"] is True
        assert "color:red" not in result["content"]
        assert "Content" in result["content"]
