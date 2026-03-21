"""
Web Tools

Provides web search (DuckDuckGo) and URL content fetching capabilities.
"""

import asyncio
import re
from typing import Any

import aiohttp

from taskforce.core.domain.errors import ToolError, tool_error_payload
from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol
from taskforce.infrastructure.tools.native.url_validator import validate_url_for_ssrf


class WebSearchTool(ToolProtocol):
    """Web search using DuckDuckGo (no API key required).

    Uses the ``duckduckgo_search`` library for real web search results.
    Falls back to the DuckDuckGo Instant Answer API when the library
    is not installed.
    """

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web using DuckDuckGo"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query string",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (default: 5)",
                },
            },
            "required": ["query"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.LOW

    @property
    def supports_parallelism(self) -> bool:
        return True

    def get_approval_preview(self, **kwargs: Any) -> str:
        query = kwargs.get("query", "")
        num_results = kwargs.get("num_results", 5)
        return f"Tool: {self.name}\nOperation: Web search\nQuery: {query}\nResults: {num_results}"

    async def execute(
        self, query: str, num_results: int = 5, **kwargs: Any
    ) -> dict[str, Any]:
        """Search the web using DuckDuckGo.

        Args:
            query: Search query string.
            num_results: Number of results to return (default: 5).

        Returns:
            Dictionary with success, query, results, count (or error).
        """
        try:
            return await self._search_ddgs(query, num_results)
        except ImportError:
            return await self._search_instant_answer_api(query, num_results)
        except Exception as e:
            tool_error = ToolError(
                f"{self.name} failed: {e}",
                tool_name=self.name,
                details={"query": query, "num_results": num_results},
            )
            return tool_error_payload(tool_error)

    async def _search_ddgs(self, query: str, num_results: int) -> dict[str, Any]:
        """Search using the duckduckgo_search library (real web results)."""
        from ddgs import DDGS  # noqa: WPS433

        # DDGS is synchronous — run in a thread to avoid blocking the event loop.
        def _run() -> list[dict[str, str]]:
            return DDGS().text(query, max_results=num_results)

        raw_results = await asyncio.to_thread(_run)

        results = [
            {
                "title": r.get("title", ""),
                "snippet": r.get("body", ""),
                "url": r.get("href", ""),
            }
            for r in raw_results
        ]

        return {
            "success": True,
            "query": query,
            "results": results,
            "count": len(results),
        }

    async def _search_instant_answer_api(
        self, query: str, num_results: int
    ) -> dict[str, Any]:
        """Fallback: DuckDuckGo Instant Answer API (limited results)."""
        async with aiohttp.ClientSession() as session:
            params = {
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
            }
            async with session.get(
                "https://api.duckduckgo.com/",
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                data = await response.json(content_type=None)

                results: list[dict[str, str]] = []
                if data.get("Abstract"):
                    results.append(
                        {
                            "title": data.get("Heading", ""),
                            "snippet": data["Abstract"],
                            "url": data.get("AbstractURL", ""),
                        }
                    )
                for topic in data.get("RelatedTopics", [])[:num_results]:
                    if isinstance(topic, dict) and "Text" in topic:
                        results.append(
                            {
                                "title": topic.get("Text", "").split(" - ")[0][:50],
                                "snippet": topic.get("Text", ""),
                                "url": topic.get("FirstURL", ""),
                            }
                        )

                return {
                    "success": True,
                    "query": query,
                    "results": results[:num_results],
                    "count": len(results),
                }

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "query" not in kwargs:
            return False, "Missing required parameter: query"
        if not isinstance(kwargs["query"], str):
            return False, "Parameter 'query' must be a string"
        return True, None


class WebFetchTool(ToolProtocol):
    """Fetch and extract content from URLs."""

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return "Fetch and extract content from a URL"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch content from",
                },
            },
            "required": ["url"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.LOW

    @property
    def supports_parallelism(self) -> bool:
        return True

    def get_approval_preview(self, **kwargs: Any) -> str:
        url = kwargs.get("url", "")
        return f"Tool: {self.name}\nOperation: Fetch URL content\nURL: {url}"

    async def execute(self, url: str, **kwargs) -> dict[str, Any]:
        """
        Fetch and extract content from a URL.

        Args:
            url: URL to fetch content from

        Returns:
            Dictionary with:
            - success: bool - True if fetch succeeded
            - url: str - The fetched URL
            - status: int - HTTP status code
            - content: str - Extracted text content (limited to 5000 chars)
            - content_type: str - Content-Type header
            - length: int - Original content length
            - error: str - Error message (if failed)
        """
        if not aiohttp:
            return {"success": False, "error": "aiohttp not installed"}

        # SSRF protection: block requests to private/internal networks
        is_safe, ssrf_error = validate_url_for_ssrf(url)
        if not is_safe:
            return {"success": False, "error": ssrf_error}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    content = await response.text()

                    # Simple HTML extraction
                    if "text/html" in response.headers.get("Content-Type", ""):
                        # Remove HTML tags (basic)
                        text = re.sub(
                            "<script[^>]*>.*?</script>", "", content, flags=re.DOTALL
                        )
                        text = re.sub(
                            "<style[^>]*>.*?</style>", "", text, flags=re.DOTALL
                        )
                        text = re.sub("<[^>]+>", "", text)
                        text = " ".join(text.split())[:5000]  # Limit size
                    else:
                        text = content[:5000]

                    return {
                        "success": True,
                        "url": url,
                        "status": response.status,
                        "content": text,
                        "content_type": response.headers.get("Content-Type", ""),
                        "length": len(content),
                    }

        except TimeoutError:
            tool_error = ToolError(
                f"{self.name} failed: Request timed out",
                tool_name=self.name,
                details={"url": url},
            )
            return tool_error_payload(tool_error)
        except Exception as e:
            tool_error = ToolError(
                f"{self.name} failed: {e}",
                tool_name=self.name,
                details={"url": url},
            )
            return tool_error_payload(tool_error)

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "url" not in kwargs:
            return False, "Missing required parameter: url"
        if not isinstance(kwargs["url"], str):
            return False, "Parameter 'url' must be a string"
        return True, None
