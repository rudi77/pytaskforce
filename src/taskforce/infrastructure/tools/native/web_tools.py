"""
Web Tools

Provides web search (DuckDuckGo) and URL content fetching capabilities.
Migrated from Agent V2 with full preservation of functionality.
"""

import asyncio
import re
from typing import Any, Dict

import aiohttp

from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol


class WebSearchTool(ToolProtocol):
    """Web search using DuckDuckGo (no API key required)."""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web using DuckDuckGo"

    @property
    def parameters_schema(self) -> Dict[str, Any]:
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

    def get_approval_preview(self, **kwargs: Any) -> str:
        query = kwargs.get("query", "")
        num_results = kwargs.get("num_results", 5)
        return f"Tool: {self.name}\nOperation: Web search\nQuery: {query}\nResults: {num_results}"

    async def execute(
        self, query: str, num_results: int = 5, **kwargs
    ) -> Dict[str, Any]:
        """
        Search the web using DuckDuckGo.

        Args:
            query: Search query string
            num_results: Number of results to return (default: 5)

        Returns:
            Dictionary with:
            - success: bool - True if search succeeded
            - query: str - The search query
            - results: List[Dict] - Search results with title, snippet, url
            - count: int - Number of results returned
            - error: str - Error message (if failed)
        """
        if not aiohttp:
            return {"success": False, "error": "aiohttp not installed"}

        try:
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
                    # DuckDuckGo may return a non-standard JSON Content-Type
                    # Allow json() to parse regardless of Content-Type
                    data = await response.json(content_type=None)

                    results = []

                    # Extract abstract if available
                    if data.get("Abstract"):
                        results.append(
                            {
                                "title": data.get("Heading", ""),
                                "snippet": data["Abstract"],
                                "url": data.get("AbstractURL", ""),
                            }
                        )

                    # Extract related topics
                    for topic in data.get("RelatedTopics", [])[:num_results]:
                        if isinstance(topic, dict) and "Text" in topic:
                            results.append(
                                {
                                    "title": topic.get("Text", "").split(" - ")[0][
                                        :50
                                    ],
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

        except Exception as e:
            return {"success": False, "error": str(e)}

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
    def parameters_schema(self) -> Dict[str, Any]:
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

    def get_approval_preview(self, **kwargs: Any) -> str:
        url = kwargs.get("url", "")
        return f"Tool: {self.name}\nOperation: Fetch URL content\nURL: {url}"

    async def execute(self, url: str, **kwargs) -> Dict[str, Any]:
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

        except asyncio.TimeoutError:
            return {"success": False, "error": "Request timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "url" not in kwargs:
            return False, "Missing required parameter: url"
        if not isinstance(kwargs["url"], str):
            return False, "Parameter 'url' must be a string"
        return True, None

