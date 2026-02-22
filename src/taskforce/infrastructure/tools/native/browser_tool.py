"""
Browser Tool

Provides browser automation capabilities using Playwright.
Supports navigating pages, clicking elements, filling forms,
taking screenshots, and extracting content from web pages.

Requires the optional 'browser' dependency group:
    uv sync --extra browser
    playwright install chromium
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import structlog

from taskforce.core.domain.errors import ToolError, tool_error_payload
from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol

logger = structlog.get_logger(__name__)

# Module-level browser session – shared across tool calls within a process
_session: _BrowserSession | None = None


class _BrowserSession:
    """Manages a persistent Playwright browser session."""

    def __init__(self) -> None:
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

    async def start(self, headless: bool = True) -> None:
        """Launch the browser and open an initial page."""
        from playwright.async_api import async_playwright  # type: ignore[import]

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=headless)
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self._page = await self._context.new_page()
        logger.info("browser_session.started", headless=headless)

    @property
    def page(self) -> Any:
        """Return the active page."""
        return self._page

    async def close(self) -> None:
        """Close the browser and release all resources."""
        if self._page:
            await self._page.close()
            self._page = None
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("browser_session.closed")


async def _get_session(headless: bool = True) -> _BrowserSession:
    """Return the active session, creating one if necessary."""
    global _session
    if _session is None or _session.page is None:
        _session = _BrowserSession()
        await _session.start(headless=headless)
    return _session


# ---------------------------------------------------------------------------
# Main tool class
# ---------------------------------------------------------------------------


class BrowserTool(ToolProtocol):
    """
    Browser automation tool for interacting with web pages.

    Uses Playwright to control a headless Chromium browser. The session
    persists across multiple tool calls so that navigation state, cookies,
    and form data are maintained between steps.

    Supported actions:
        navigate          – Go to a URL and wait for DOM ready.
        click             – Click an element matching a CSS selector.
        fill              – Type text into an input or textarea.
        screenshot        – Capture the current page as a PNG image.
        get_text          – Extract visible text from an element or the page.
        get_html          – Retrieve the inner HTML of an element or the page.
        evaluate          – Execute a JavaScript expression and return its result.
        wait_for_selector – Wait until an element matching a selector appears.
        wait_for_url      – Wait until the page URL matches a pattern.
        select            – Choose an option in a <select> element.
        hover             – Move the mouse over an element.
        press_key         – Press a keyboard key (optionally on a focused element).
        scroll            – Scroll the page or an element.
        close             – Close the browser session.

    Installation:
        uv sync --extra browser
        playwright install chromium
    """

    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return (
            "Control a web browser to interact with web pages. "
            "Navigate to URLs, click elements, fill forms, take screenshots, and extract text. "
            "Uses CSS selectors for element targeting. Browser session persists across calls."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "navigate",
                        "click",
                        "fill",
                        "screenshot",
                        "get_text",
                        "get_html",
                        "evaluate",
                        "wait_for_selector",
                        "wait_for_url",
                        "select",
                        "hover",
                        "press_key",
                        "scroll",
                        "close",
                    ],
                    "description": (
                        "Browser action to perform: "
                        "navigate (go to URL), click (click element), "
                        "fill (type into field), screenshot (capture page), "
                        "get_text (extract text), get_html (get HTML), "
                        "evaluate (run JavaScript), wait_for_selector (wait for element), "
                        "wait_for_url (wait for URL), select (choose <select> option), "
                        "hover (mouse over element), press_key (keyboard key), "
                        "scroll (scroll page), close (close browser session)."
                    ),
                },
                "url": {
                    "type": "string",
                    "description": "URL to navigate to (required for 'navigate'; pattern for 'wait_for_url').",
                },
                "selector": {
                    "type": "string",
                    "description": (
                        "CSS selector for the target element. "
                        "Required for: click, fill, wait_for_selector, select, hover. "
                        "Optional for: get_text, get_html, press_key, scroll."
                    ),
                },
                "value": {
                    "type": "string",
                    "description": "Text to type (for 'fill') or option value/label to choose (for 'select').",
                },
                "screenshot_path": {
                    "type": "string",
                    "description": (
                        "File path where the PNG screenshot should be saved "
                        "(optional for 'screenshot'). "
                        "The base64-encoded image is always returned regardless."
                    ),
                },
                "script": {
                    "type": "string",
                    "description": "JavaScript expression to evaluate in the browser context (for 'evaluate').",
                },
                "key": {
                    "type": "string",
                    "description": (
                        "Key to press, e.g. 'Enter', 'Tab', 'Escape', 'ArrowDown' (for 'press_key'). "
                        "Follows Playwright key naming conventions."
                    ),
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in milliseconds for the action (default: 30000).",
                },
                "headless": {
                    "type": "boolean",
                    "description": (
                        "Run browser in headless mode (default: true). "
                        "Only applied when a new browser session is started."
                    ),
                },
                "full_page": {
                    "type": "boolean",
                    "description": "Capture the full page instead of just the viewport (default: false).",
                },
                "scroll_direction": {
                    "type": "string",
                    "enum": ["up", "down", "left", "right"],
                    "description": "Direction to scroll (for 'scroll', default: 'down').",
                },
                "scroll_amount": {
                    "type": "integer",
                    "description": "Number of pixels to scroll (for 'scroll', default: 300).",
                },
            },
            "required": ["action"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.MEDIUM

    @property
    def supports_parallelism(self) -> bool:
        # Browser has shared state; parallel calls would corrupt the session.
        return False

    def get_approval_preview(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "")
        lines = [f"Tool: {self.name}", f"Action: {action}"]
        if kwargs.get("url"):
            lines.append(f"URL: {kwargs['url']}")
        if kwargs.get("selector"):
            lines.append(f"Selector: {kwargs['selector']}")
        if kwargs.get("value"):
            lines.append(f"Value: {kwargs['value']}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Main execute dispatcher
    # ------------------------------------------------------------------

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """
        Execute the requested browser action.

        Args:
            action: The action to perform (see parameters_schema for options).
            **kwargs: Action-specific parameters.

        Returns:
            Dictionary with 'success' bool and action-specific fields.
        """
        action = kwargs.get("action", "")
        timeout = int(kwargs.get("timeout", 30_000))
        headless = bool(kwargs.get("headless", True))

        try:
            if action == "close":
                return await self._action_close()

            session = await _get_session(headless=headless)
            page = session.page

            dispatch: dict[str, Any] = {
                "navigate": self._action_navigate,
                "click": self._action_click,
                "fill": self._action_fill,
                "screenshot": self._action_screenshot,
                "get_text": self._action_get_text,
                "get_html": self._action_get_html,
                "evaluate": self._action_evaluate,
                "wait_for_selector": self._action_wait_for_selector,
                "wait_for_url": self._action_wait_for_url,
                "select": self._action_select,
                "hover": self._action_hover,
                "press_key": self._action_press_key,
                "scroll": self._action_scroll,
            }

            handler = dispatch.get(action)
            if handler is None:
                return {"success": False, "error": f"Unknown action: '{action}'"}

            if action == "screenshot":
                return await handler(page, kwargs)
            elif action in ("evaluate", "scroll"):
                return await handler(page, kwargs)
            else:
                return await handler(page, kwargs, timeout)

        except ImportError:
            return {
                "success": False,
                "error": (
                    "Playwright is not installed. "
                    "Install with: uv sync --extra browser && playwright install chromium"
                ),
            }
        except Exception as e:
            safe_kwargs = {k: v for k, v in kwargs.items() if k != "script"}
            tool_error = ToolError(
                f"{self.name} action '{action}' failed: {e}",
                tool_name=self.name,
                details={"action": action, **safe_kwargs},
            )
            logger.error("browser_tool.error", action=action, error=str(e))
            return tool_error_payload(tool_error)

    # ------------------------------------------------------------------
    # Individual action implementations
    # ------------------------------------------------------------------

    async def _action_navigate(
        self, page: Any, kwargs: dict[str, Any], timeout: int
    ) -> dict[str, Any]:
        """Navigate to a URL and wait for the DOM to be ready."""
        url = kwargs.get("url")
        if not url:
            return {"success": False, "error": "Action 'navigate' requires parameter: url"}
        response = await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        return {
            "success": True,
            "url": page.url,
            "status": response.status if response else None,
            "title": await page.title(),
        }

    async def _action_click(
        self, page: Any, kwargs: dict[str, Any], timeout: int
    ) -> dict[str, Any]:
        """Click an element matching the given CSS selector."""
        selector = kwargs.get("selector")
        if not selector:
            return {"success": False, "error": "Action 'click' requires parameter: selector"}
        await page.click(selector, timeout=timeout)
        await page.wait_for_load_state("domcontentloaded")
        return {
            "success": True,
            "action": "click",
            "selector": selector,
            "current_url": page.url,
        }

    async def _action_fill(
        self, page: Any, kwargs: dict[str, Any], timeout: int
    ) -> dict[str, Any]:
        """Clear an input field and type a value into it."""
        selector = kwargs.get("selector")
        value = kwargs.get("value", "")
        if not selector:
            return {"success": False, "error": "Action 'fill' requires parameter: selector"}
        await page.fill(selector, value, timeout=timeout)
        return {
            "success": True,
            "action": "fill",
            "selector": selector,
            "value": value,
        }

    async def _action_screenshot(
        self, page: Any, kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        """Capture the current page as a PNG image."""
        full_page = bool(kwargs.get("full_page", False))
        screenshot_path = kwargs.get("screenshot_path")

        screenshot_bytes: bytes = await page.screenshot(full_page=full_page)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        saved_path: str | None = None
        if screenshot_path:
            path = Path(screenshot_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(screenshot_bytes)
            saved_path = str(path.absolute())
            logger.info("browser_tool.screenshot_saved", path=saved_path)

        return {
            "success": True,
            "action": "screenshot",
            "screenshot_base64": screenshot_b64,
            "saved_path": saved_path,
            "url": page.url,
            "size_bytes": len(screenshot_bytes),
        }

    async def _action_get_text(
        self, page: Any, kwargs: dict[str, Any], timeout: int
    ) -> dict[str, Any]:
        """Extract the visible text from an element or the entire page body."""
        selector = kwargs.get("selector")
        if selector:
            text = await page.inner_text(selector, timeout=timeout)
        else:
            text = await page.inner_text("body")
        return {
            "success": True,
            "text": text,
            "selector": selector or "body",
            "url": page.url,
        }

    async def _action_get_html(
        self, page: Any, kwargs: dict[str, Any], timeout: int
    ) -> dict[str, Any]:
        """Retrieve the HTML of an element or the full page. Truncated at 10 KB."""
        selector = kwargs.get("selector")
        if selector:
            html = await page.inner_html(selector, timeout=timeout)
        else:
            html = await page.content()
        truncated = len(html) > 10_000
        return {
            "success": True,
            "html": html[:10_000],
            "selector": selector or "page",
            "url": page.url,
            "truncated": truncated,
        }

    async def _action_evaluate(
        self, page: Any, kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a JavaScript expression and return its result."""
        script = kwargs.get("script")
        if not script:
            return {"success": False, "error": "Action 'evaluate' requires parameter: script"}
        result = await page.evaluate(script)
        return {
            "success": True,
            "result": result,
            "url": page.url,
        }

    async def _action_wait_for_selector(
        self, page: Any, kwargs: dict[str, Any], timeout: int
    ) -> dict[str, Any]:
        """Wait until an element matching the selector appears in the DOM."""
        selector = kwargs.get("selector")
        if not selector:
            return {
                "success": False,
                "error": "Action 'wait_for_selector' requires parameter: selector",
            }
        await page.wait_for_selector(selector, timeout=timeout)
        return {
            "success": True,
            "selector": selector,
            "found": True,
            "url": page.url,
        }

    async def _action_wait_for_url(
        self, page: Any, kwargs: dict[str, Any], timeout: int
    ) -> dict[str, Any]:
        """Wait until the page URL matches a given URL or glob pattern."""
        url = kwargs.get("url")
        if not url:
            return {"success": False, "error": "Action 'wait_for_url' requires parameter: url"}
        await page.wait_for_url(url, timeout=timeout)
        return {
            "success": True,
            "url": page.url,
        }

    async def _action_select(
        self, page: Any, kwargs: dict[str, Any], timeout: int
    ) -> dict[str, Any]:
        """Choose an option in a <select> element by value or label."""
        selector = kwargs.get("selector")
        value = kwargs.get("value")
        if not selector:
            return {"success": False, "error": "Action 'select' requires parameter: selector"}
        if not value:
            return {"success": False, "error": "Action 'select' requires parameter: value"}
        await page.select_option(selector, value=value, timeout=timeout)
        return {
            "success": True,
            "action": "select",
            "selector": selector,
            "value": value,
        }

    async def _action_hover(
        self, page: Any, kwargs: dict[str, Any], timeout: int
    ) -> dict[str, Any]:
        """Move the mouse pointer over an element."""
        selector = kwargs.get("selector")
        if not selector:
            return {"success": False, "error": "Action 'hover' requires parameter: selector"}
        await page.hover(selector, timeout=timeout)
        return {
            "success": True,
            "action": "hover",
            "selector": selector,
        }

    async def _action_press_key(
        self, page: Any, kwargs: dict[str, Any], timeout: int
    ) -> dict[str, Any]:
        """Press a keyboard key, optionally targeting a specific element."""
        key = kwargs.get("key")
        selector = kwargs.get("selector")
        if not key:
            return {"success": False, "error": "Action 'press_key' requires parameter: key"}
        if selector:
            await page.press(selector, key, timeout=timeout)
        else:
            await page.keyboard.press(key)
        return {
            "success": True,
            "action": "press_key",
            "key": key,
            "selector": selector,
        }

    async def _action_scroll(
        self, page: Any, kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        """Scroll the page window by the given amount in the given direction."""
        direction = kwargs.get("scroll_direction", "down")
        amount = int(kwargs.get("scroll_amount", 300))
        selector = kwargs.get("selector")

        scroll_map: dict[str, tuple[int, int]] = {
            "down": (0, amount),
            "up": (0, -amount),
            "right": (amount, 0),
            "left": (-amount, 0),
        }
        delta_x, delta_y = scroll_map.get(direction, (0, amount))

        if selector:
            element = await page.query_selector(selector)
            if element:
                await element.scroll_into_view_if_needed()

        await page.evaluate(f"window.scrollBy({delta_x}, {delta_y})")
        return {
            "success": True,
            "action": "scroll",
            "direction": direction,
            "amount": amount,
        }

    async def _action_close(self) -> dict[str, Any]:
        """Close the active browser session and free resources."""
        global _session
        if _session:
            await _session.close()
            _session = None
        return {"success": True, "action": "close", "message": "Browser session closed."}

    # ------------------------------------------------------------------
    # Parameter validation
    # ------------------------------------------------------------------

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate that required parameters are present for the given action."""
        action = kwargs.get("action")
        if not action:
            return False, "Missing required parameter: action"

        valid_actions = {
            "navigate",
            "click",
            "fill",
            "screenshot",
            "get_text",
            "get_html",
            "evaluate",
            "wait_for_selector",
            "wait_for_url",
            "select",
            "hover",
            "press_key",
            "scroll",
            "close",
        }
        if action not in valid_actions:
            return False, (
                f"Invalid action '{action}'. Must be one of: {', '.join(sorted(valid_actions))}"
            )

        selector_required = {"click", "fill", "wait_for_selector", "select", "hover"}
        if action in selector_required and not kwargs.get("selector"):
            return False, f"Action '{action}' requires parameter: selector"

        if action == "navigate" and not kwargs.get("url"):
            return False, "Action 'navigate' requires parameter: url"
        if action == "wait_for_url" and not kwargs.get("url"):
            return False, "Action 'wait_for_url' requires parameter: url"
        if action == "fill" and "value" not in kwargs:
            return False, "Action 'fill' requires parameter: value"
        if action == "evaluate" and not kwargs.get("script"):
            return False, "Action 'evaluate' requires parameter: script"
        if action == "press_key" and not kwargs.get("key"):
            return False, "Action 'press_key' requires parameter: key"
        if action == "select" and not kwargs.get("value"):
            return False, "Action 'select' requires parameter: value"

        return True, None
