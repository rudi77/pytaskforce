"""
Unit tests for BrowserTool

Tests the BrowserTool implementation using mocked Playwright objects,
so no real browser installation is required to run the test suite.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import taskforce.infrastructure.tools.native.browser_tool as browser_module
from taskforce.infrastructure.tools.native.browser_tool import BrowserTool
from taskforce.core.interfaces.tools import ApprovalRiskLevel


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_page(
    url: str = "https://example.com",
    title: str = "Example",
    status: int = 200,
) -> MagicMock:
    """Return a Playwright Page-like mock with common methods stubbed."""
    page = MagicMock()
    page.url = url

    page.goto = AsyncMock(return_value=MagicMock(status=status))
    page.title = AsyncMock(return_value=title)
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.inner_text = AsyncMock(return_value="Hello World")
    page.inner_html = AsyncMock(return_value="<p>Hello</p>")
    page.content = AsyncMock(return_value="<html><body><p>Hello</p></body></html>")
    page.evaluate = AsyncMock(return_value=42)
    page.wait_for_selector = AsyncMock()
    page.wait_for_url = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.select_option = AsyncMock()
    page.hover = AsyncMock()
    page.press = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.query_selector = AsyncMock(return_value=None)
    page.screenshot = AsyncMock(return_value=b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    page.close = AsyncMock()
    return page


@pytest.fixture(autouse=True)
def reset_browser_session():
    """Ensure module-level browser session is clean before each test."""
    browser_module._session = None
    yield
    browser_module._session = None


@pytest.fixture
def tool() -> BrowserTool:
    """Return a fresh BrowserTool instance."""
    return BrowserTool()


@pytest.fixture
def mock_page() -> MagicMock:
    """Return a pre-built mock page."""
    return _make_page()


@pytest.fixture
def mock_session(mock_page: MagicMock) -> MagicMock:
    """Return a mock _BrowserSession whose .page property returns mock_page."""
    session = MagicMock()
    session.page = mock_page
    session.close = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Tool metadata tests
# ---------------------------------------------------------------------------


class TestBrowserToolMetadata:
    """Verify tool identity, schema, and capability flags."""

    def test_name(self, tool: BrowserTool) -> None:
        assert tool.name == "browser"

    def test_description_mentions_key_concepts(self, tool: BrowserTool) -> None:
        desc = tool.description.lower()
        assert "browser" in desc
        assert "navigate" in desc or "url" in desc
        assert "screenshot" in desc or "click" in desc

    def test_parameters_schema_structure(self, tool: BrowserTool) -> None:
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "action" in schema["properties"]
        assert "action" in schema["required"]
        # Spot-check optional params
        for param in ("url", "selector", "value", "screenshot_path", "script", "key"):
            assert param in schema["properties"]

    def test_requires_approval_is_false(self, tool: BrowserTool) -> None:
        assert tool.requires_approval is False

    def test_approval_risk_level(self, tool: BrowserTool) -> None:
        assert tool.approval_risk_level == ApprovalRiskLevel.MEDIUM

    def test_supports_parallelism_is_false(self, tool: BrowserTool) -> None:
        # Browser session has shared state – parallel calls are unsafe.
        assert tool.supports_parallelism is False

    def test_get_approval_preview(self, tool: BrowserTool) -> None:
        preview = tool.get_approval_preview(
            action="navigate", url="https://example.com"
        )
        assert "browser" in preview
        assert "navigate" in preview
        assert "https://example.com" in preview


# ---------------------------------------------------------------------------
# Parameter validation tests
# ---------------------------------------------------------------------------


class TestValidateParams:
    """Verify validate_params enforces required parameters correctly."""

    def test_missing_action(self, tool: BrowserTool) -> None:
        valid, error = tool.validate_params()
        assert valid is False
        assert error is not None

    def test_invalid_action(self, tool: BrowserTool) -> None:
        valid, error = tool.validate_params(action="fly")
        assert valid is False
        assert "fly" in (error or "")

    def test_navigate_missing_url(self, tool: BrowserTool) -> None:
        valid, error = tool.validate_params(action="navigate")
        assert valid is False
        assert "url" in (error or "").lower()

    def test_navigate_valid(self, tool: BrowserTool) -> None:
        valid, error = tool.validate_params(action="navigate", url="https://example.com")
        assert valid is True
        assert error is None

    def test_click_missing_selector(self, tool: BrowserTool) -> None:
        valid, error = tool.validate_params(action="click")
        assert valid is False
        assert "selector" in (error or "").lower()

    def test_fill_missing_selector(self, tool: BrowserTool) -> None:
        valid, error = tool.validate_params(action="fill", value="hello")
        assert valid is False
        assert "selector" in (error or "").lower()

    def test_fill_missing_value(self, tool: BrowserTool) -> None:
        valid, error = tool.validate_params(action="fill", selector="#q")
        assert valid is False
        assert "value" in (error or "").lower()

    def test_fill_valid(self, tool: BrowserTool) -> None:
        valid, error = tool.validate_params(action="fill", selector="#q", value="test")
        assert valid is True
        assert error is None

    def test_evaluate_missing_script(self, tool: BrowserTool) -> None:
        valid, error = tool.validate_params(action="evaluate")
        assert valid is False
        assert "script" in (error or "").lower()

    def test_press_key_missing_key(self, tool: BrowserTool) -> None:
        valid, error = tool.validate_params(action="press_key")
        assert valid is False
        assert "key" in (error or "").lower()

    def test_select_missing_value(self, tool: BrowserTool) -> None:
        valid, error = tool.validate_params(action="select", selector="select#lang")
        assert valid is False
        assert "value" in (error or "").lower()

    def test_screenshot_valid(self, tool: BrowserTool) -> None:
        valid, error = tool.validate_params(action="screenshot")
        assert valid is True
        assert error is None

    def test_close_valid(self, tool: BrowserTool) -> None:
        valid, error = tool.validate_params(action="close")
        assert valid is True
        assert error is None


# ---------------------------------------------------------------------------
# Execute – action tests (Playwright mocked at session level)
# ---------------------------------------------------------------------------


class TestExecuteActions:
    """Test each action via execute() with a mocked browser session."""

    @pytest.fixture(autouse=True)
    def patch_session(self, mock_session: MagicMock) -> None:
        """Patch _get_session to return the mock session for all tests."""
        with patch(
            "taskforce.infrastructure.tools.native.browser_tool._get_session",
            new=AsyncMock(return_value=mock_session),
        ):
            yield

    # --- navigate ---

    async def test_navigate_success(
        self, tool: BrowserTool, mock_page: MagicMock
    ) -> None:
        result = await tool.execute(action="navigate", url="https://example.com")
        assert result["success"] is True
        assert result["url"] == mock_page.url
        assert result["status"] == 200
        assert result["title"] == "Example"
        mock_page.goto.assert_awaited_once()

    async def test_navigate_missing_url(self, tool: BrowserTool) -> None:
        result = await tool.execute(action="navigate")
        assert result["success"] is False
        assert "url" in result["error"].lower()

    # --- click ---

    async def test_click_success(
        self, tool: BrowserTool, mock_page: MagicMock
    ) -> None:
        result = await tool.execute(action="click", selector="button#submit")
        assert result["success"] is True
        assert result["selector"] == "button#submit"
        mock_page.click.assert_awaited_once_with("button#submit", timeout=30_000)

    async def test_click_missing_selector(self, tool: BrowserTool) -> None:
        result = await tool.execute(action="click")
        assert result["success"] is False

    # --- fill ---

    async def test_fill_success(
        self, tool: BrowserTool, mock_page: MagicMock
    ) -> None:
        result = await tool.execute(action="fill", selector="input#name", value="Alice")
        assert result["success"] is True
        assert result["value"] == "Alice"
        mock_page.fill.assert_awaited_once_with("input#name", "Alice", timeout=30_000)

    # --- screenshot ---

    async def test_screenshot_returns_base64(
        self, tool: BrowserTool, mock_page: MagicMock
    ) -> None:
        result = await tool.execute(action="screenshot")
        assert result["success"] is True
        assert "screenshot_base64" in result
        assert result["saved_path"] is None
        assert result["size_bytes"] > 0

    async def test_screenshot_saves_to_path(
        self, tool: BrowserTool, mock_page: MagicMock, tmp_path: Path
    ) -> None:
        dest = tmp_path / "capture.png"
        result = await tool.execute(action="screenshot", screenshot_path=str(dest))
        assert result["success"] is True
        assert result["saved_path"] is not None
        assert dest.exists()

    # --- get_text ---

    async def test_get_text_full_page(
        self, tool: BrowserTool, mock_page: MagicMock
    ) -> None:
        result = await tool.execute(action="get_text")
        assert result["success"] is True
        assert result["text"] == "Hello World"
        assert result["selector"] == "body"

    async def test_get_text_with_selector(
        self, tool: BrowserTool, mock_page: MagicMock
    ) -> None:
        result = await tool.execute(action="get_text", selector="h1")
        assert result["success"] is True
        assert result["selector"] == "h1"
        mock_page.inner_text.assert_awaited_once_with("h1", timeout=30_000)

    # --- get_html ---

    async def test_get_html_full_page(
        self, tool: BrowserTool, mock_page: MagicMock
    ) -> None:
        result = await tool.execute(action="get_html")
        assert result["success"] is True
        assert "<html>" in result["html"]

    async def test_get_html_with_selector(
        self, tool: BrowserTool, mock_page: MagicMock
    ) -> None:
        result = await tool.execute(action="get_html", selector="article")
        assert result["success"] is True
        assert result["selector"] == "article"

    async def test_get_html_truncates_large_content(
        self, tool: BrowserTool, mock_page: MagicMock
    ) -> None:
        mock_page.content = AsyncMock(return_value="x" * 20_000)
        result = await tool.execute(action="get_html")
        assert result["success"] is True
        assert len(result["html"]) <= 10_000
        assert result["truncated"] is True

    # --- evaluate ---

    async def test_evaluate_success(
        self, tool: BrowserTool, mock_page: MagicMock
    ) -> None:
        result = await tool.execute(action="evaluate", script="1 + 1")
        assert result["success"] is True
        assert result["result"] == 42
        mock_page.evaluate.assert_awaited_once_with("1 + 1")

    async def test_evaluate_missing_script(self, tool: BrowserTool) -> None:
        result = await tool.execute(action="evaluate")
        assert result["success"] is False

    # --- wait_for_selector ---

    async def test_wait_for_selector_success(
        self, tool: BrowserTool, mock_page: MagicMock
    ) -> None:
        result = await tool.execute(action="wait_for_selector", selector=".loaded")
        assert result["success"] is True
        assert result["found"] is True
        mock_page.wait_for_selector.assert_awaited_once()

    # --- wait_for_url ---

    async def test_wait_for_url_success(
        self, tool: BrowserTool, mock_page: MagicMock
    ) -> None:
        result = await tool.execute(action="wait_for_url", url="**/dashboard")
        assert result["success"] is True
        mock_page.wait_for_url.assert_awaited_once()

    # --- select ---

    async def test_select_success(
        self, tool: BrowserTool, mock_page: MagicMock
    ) -> None:
        result = await tool.execute(
            action="select", selector="select#country", value="DE"
        )
        assert result["success"] is True
        assert result["value"] == "DE"
        mock_page.select_option.assert_awaited_once()

    # --- hover ---

    async def test_hover_success(
        self, tool: BrowserTool, mock_page: MagicMock
    ) -> None:
        result = await tool.execute(action="hover", selector="#menu")
        assert result["success"] is True
        mock_page.hover.assert_awaited_once_with("#menu", timeout=30_000)

    # --- press_key ---

    async def test_press_key_global(
        self, tool: BrowserTool, mock_page: MagicMock
    ) -> None:
        result = await tool.execute(action="press_key", key="Enter")
        assert result["success"] is True
        mock_page.keyboard.press.assert_awaited_once_with("Enter")

    async def test_press_key_on_element(
        self, tool: BrowserTool, mock_page: MagicMock
    ) -> None:
        result = await tool.execute(action="press_key", key="Tab", selector="input")
        assert result["success"] is True
        mock_page.press.assert_awaited_once_with("input", "Tab", timeout=30_000)

    # --- scroll ---

    async def test_scroll_down(
        self, tool: BrowserTool, mock_page: MagicMock
    ) -> None:
        result = await tool.execute(action="scroll", scroll_direction="down", scroll_amount=500)
        assert result["success"] is True
        assert result["direction"] == "down"
        assert result["amount"] == 500

    async def test_scroll_default_direction(
        self, tool: BrowserTool, mock_page: MagicMock
    ) -> None:
        result = await tool.execute(action="scroll")
        assert result["success"] is True
        assert result["direction"] == "down"

    # --- close ---

    async def test_close_action(self, tool: BrowserTool) -> None:
        # Place a mock session into the module global
        mock_sess = MagicMock()
        mock_sess.close = AsyncMock()
        browser_module._session = mock_sess  # type: ignore[assignment]

        result = await tool.execute(action="close")
        assert result["success"] is True
        mock_sess.close.assert_awaited_once()
        assert browser_module._session is None

    # --- unknown action ---

    async def test_unknown_action(self, tool: BrowserTool) -> None:
        result = await tool.execute(action="fly")
        assert result["success"] is False
        assert "fly" in result["error"]

    # --- playwright not installed ---

    async def test_playwright_not_installed(self, tool: BrowserTool) -> None:
        with patch(
            "taskforce.infrastructure.tools.native.browser_tool._get_session",
            side_effect=ImportError("No module named 'playwright'"),
        ):
            result = await tool.execute(action="navigate", url="https://example.com")
        assert result["success"] is False
        assert "playwright" in result["error"].lower()


# ---------------------------------------------------------------------------
# Registry integration test
# ---------------------------------------------------------------------------


class TestBrowserToolRegistry:
    """Verify the tool is correctly registered in the tool registry."""

    def test_browser_in_registry(self) -> None:
        from taskforce.infrastructure.tools.registry import get_tool_definition, is_registered

        assert is_registered("browser")
        spec = get_tool_definition("browser")
        assert spec is not None
        assert spec["type"] == "BrowserTool"
        assert "browser_tool" in spec["module"]

    def test_registry_resolves_browser(self) -> None:
        from taskforce.infrastructure.tools.registry import resolve_tool_spec

        spec = resolve_tool_spec("browser")
        assert spec is not None
        assert spec["type"] == "BrowserTool"
