"""
Web Tools

Provides web search (DuckDuckGo) and URL content fetching capabilities.

Context engineering: both tools deliberately return *compact* inline
results (titles, URLs, short previews) and rely on the ToolResultStore
to hold any larger payload. This keeps freeform snippet text and
fetched HTML out of the LLM message log, which would otherwise
accumulate across recherche turns and trip provider content filters.
"""

import asyncio
import re
from typing import Any

import aiohttp

from taskforce.core.domain.errors import ToolError, tool_error_payload
from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol
from taskforce.infrastructure.tools.native.url_validator import validate_url_for_ssrf

DEFAULT_SNIPPET_PREVIEW_CHARS = 160
DEFAULT_FETCH_CONTENT_CHARS = 5000


class WebSearchTool(ToolProtocol):
    """Web search using DuckDuckGo (no API key required).

    Uses the ``duckduckgo_search`` library for real web search results.
    Falls back to the DuckDuckGo Instant Answer API when the library
    is not installed.

    Output shape: ``results`` is a list of ``{title, url, snippet}``.
    Snippets are truncated to ``snippet_max_chars`` (default
    ``DEFAULT_SNIPPET_PREVIEW_CHARS = 160``) to keep the inline payload
    small. Pass ``snippet_max_chars=0`` to drop snippets entirely.
    """

    # Always store full payloads to the ToolResultStore — even small
    # search responses can carry trigger-prone language (war, weapons,
    # politics) that aggregates badly across many search turns.
    tool_result_store_threshold: int | None = 800

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
                "snippet_max_chars": {
                    "type": "integer",
                    "description": (
                        "Per-result snippet preview length in characters "
                        f"(default: {DEFAULT_SNIPPET_PREVIEW_CHARS}, "
                        "0 = drop snippets entirely)."
                    ),
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
        self,
        query: str,
        num_results: int = 5,
        snippet_max_chars: int = DEFAULT_SNIPPET_PREVIEW_CHARS,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Search the web using DuckDuckGo.

        Args:
            query: Search query string.
            num_results: Number of results to return (default: 5).
            snippet_max_chars: Per-result snippet preview length. ``0``
                drops snippets entirely; the agent receives only
                ``title`` + ``url``.

        Returns:
            Dictionary with success, query, results, count (or error).
        """
        try:
            return await self._search_with_retry(query, num_results, snippet_max_chars)
        except ImportError:
            return await self._search_instant_answer_api(query, num_results, snippet_max_chars)
        except Exception as e:
            tool_error = ToolError(
                f"{self.name} failed: {e}",
                tool_name=self.name,
                details={"query": query, "num_results": num_results},
            )
            return tool_error_payload(tool_error)

    async def _search_with_retry(
        self, query: str, num_results: int, snippet_max_chars: int
    ) -> dict[str, Any]:
        """Issue #381: retry web_search once on transient connection errors.

        The ddgs library tries multiple backends internally (DuckDuckGo HTML,
        Brave, Bing). When the primary backend is flaky, ddgs surfaces a raw
        ConnectError/TimeoutError. Without a retry layer, the agent sees this
        as a definitive failure and tends to spin up query variations, each
        hitting the same broken endpoint. One short retry catches the common
        case (intermittent flakiness) and a clean structured error on the
        second failure lets prompts say "if search_backend_unavailable, don't
        retry-loop".
        """
        # Errors we treat as transient and worth one retry.
        TRANSIENT = (
            ConnectionError,
            TimeoutError,
            OSError,  # covers many low-level network errors
        )
        try:
            return await self._search_ddgs(query, num_results, snippet_max_chars)
        except TRANSIENT as exc:
            # One retry with a small backoff. Tight on purpose - if the
            # backend is truly down, retrying for minutes wastes the agent's
            # step budget.
            await asyncio.sleep(1.5)
            try:
                return await self._search_ddgs(query, num_results, snippet_max_chars)
            except TRANSIENT as exc2:
                tool_error = ToolError(
                    "Search backend temporarily unreachable - try again "
                    "later or use web_fetch directly with a known URL. "
                    f"Last error: {type(exc2).__name__}: {exc2}",
                    tool_name=self.name,
                    details={
                        "query": query,
                        "num_results": num_results,
                        "first_error": f"{type(exc).__name__}: {exc}",
                        "error_type_hint": "search_backend_unavailable",
                    },
                )
                return tool_error_payload(tool_error)
        # Non-transient errors (e.g. ValueError from a malformed response)
        # bubble up to the caller's generic except clause - no retry.

    @staticmethod
    def _shape_result(title: str, url: str, snippet: str, snippet_max_chars: int) -> dict[str, str]:
        """Build a compact result entry with a length-bounded snippet."""
        entry: dict[str, str] = {"title": title, "url": url}
        if snippet_max_chars > 0 and snippet:
            cleaned = " ".join(snippet.split())
            if len(cleaned) > snippet_max_chars:
                cleaned = cleaned[:snippet_max_chars].rstrip() + "…"
            entry["snippet"] = cleaned
        return entry

    async def _search_ddgs(
        self, query: str, num_results: int, snippet_max_chars: int
    ) -> dict[str, Any]:
        """Search using the duckduckgo_search library (real web results)."""
        from ddgs import DDGS  # noqa: WPS433

        # DDGS is synchronous — run in a thread to avoid blocking the event loop.
        def _run() -> list[dict[str, str]]:
            return DDGS().text(query, max_results=num_results)

        raw_results = await asyncio.to_thread(_run)

        results = [
            self._shape_result(
                r.get("title", ""),
                r.get("href", ""),
                r.get("body", ""),
                snippet_max_chars,
            )
            for r in raw_results
        ]

        return {
            "success": True,
            "query": query,
            "results": results,
            "count": len(results),
        }

    async def _search_instant_answer_api(
        self, query: str, num_results: int, snippet_max_chars: int
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
                        self._shape_result(
                            data.get("Heading", ""),
                            data.get("AbstractURL", ""),
                            data["Abstract"],
                            snippet_max_chars,
                        )
                    )
                for topic in data.get("RelatedTopics", [])[:num_results]:
                    if isinstance(topic, dict) and "Text" in topic:
                        results.append(
                            self._shape_result(
                                topic.get("Text", "").split(" - ")[0][:50],
                                topic.get("FirstURL", ""),
                                topic.get("Text", ""),
                                snippet_max_chars,
                            )
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
        if "num_results" in kwargs and not isinstance(kwargs["num_results"], int):
            return False, "Parameter 'num_results' must be an integer"
        if "snippet_max_chars" in kwargs:
            value = kwargs["snippet_max_chars"]
            # ``bool`` is a subclass of ``int``; reject it explicitly.
            if isinstance(value, bool) or not isinstance(value, int):
                return False, "Parameter 'snippet_max_chars' must be an integer"
            if value < 0:
                return False, "Parameter 'snippet_max_chars' must be >= 0"
        return True, None


class WebFetchTool(ToolProtocol):
    """Fetch and extract content from URLs.

    Returns the fetched text inline, but declares a low
    ``tool_result_store_threshold`` so any non-trivial response is
    automatically captured by the ToolResultStore. The agent then
    accesses the full content via ``fetch_result`` / ``file_read``,
    keeping raw HTML and freeform article text out of the message log.
    """

    # Any fetch over ~1.5 KB lands in the ToolResultStore.
    tool_result_store_threshold: int | None = 1500

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

        PDF handling (issue #380): if the response Content-Type is
        application/pdf or the body starts with the ``%PDF-`` magic bytes,
        the text is extracted via pypdf instead of a doomed utf-8 decode.
        """
        if not aiohttp:
            return {"success": False, "error": "aiohttp not installed"}

        # SSRF protection: block requests to private/internal networks
        is_safe, ssrf_error = validate_url_for_ssrf(url)
        if not is_safe:
            return {"success": False, "error": ssrf_error}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    content_type = response.headers.get("Content-Type", "")

                    # Issue #380: PDF detection via Content-Type or .pdf URL
                    # suffix. PDFs are binary - calling response.text() would
                    # crash with utf-8 decode error. Read bytes and run pypdf.
                    if self._looks_like_pdf(url, content_type):
                        raw_bytes = await response.read()
                        text, length = self._extract_pdf_text(raw_bytes)
                        return {
                            "success": True,
                            "url": url,
                            "status": response.status,
                            "content": text,
                            "content_type": content_type or "application/pdf",
                            "length": length,
                        }

                    # Text/HTML path - unchanged from before.
                    content = await response.text()

                    if "text/html" in content_type:
                        # Remove HTML tags (basic)
                        text = re.sub("<script[^>]*>.*?</script>", "", content, flags=re.DOTALL)
                        text = re.sub("<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
                        text = re.sub("<[^>]+>", "", text)
                        text = " ".join(text.split())[:5000]
                    else:
                        text = content[:5000]

                    return {
                        "success": True,
                        "url": url,
                        "status": response.status,
                        "content": text,
                        "content_type": content_type,
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

    @staticmethod
    def _looks_like_pdf(url: str, content_type: str) -> bool:
        """PDF detection via Content-Type header or .pdf URL suffix.

        We detect before reading the body (so existing tests that mock
        only response.text() keep working). The two signals catch the
        vast majority of cases - direct PDF links and PDF-serving CMS URLs
        usually set Content-Type, the rest end in .pdf in the path.
        """
        if "application/pdf" in content_type.lower():
            return True
        # Match path ending in .pdf, optionally followed by ?query or #frag
        path = url.split("?", 1)[0].split("#", 1)[0].lower()
        return path.endswith(".pdf")

    @staticmethod
    def _extract_pdf_text(body: bytes, max_chars: int = 5000) -> tuple[str, int]:
        """Extract text from PDF bytes via pypdf. Returns (text, full_length).

        Falls back to a structured note if pypdf is unavailable or extraction
        fails — never raises.
        """
        try:
            from io import BytesIO

            from pypdf import PdfReader
        except ImportError:
            note = "[PDF detected but pypdf is not installed - install with `uv pip install pypdf`]"
            return note, len(body)
        try:
            reader = PdfReader(BytesIO(body))
            parts = []
            total = 0
            for page in reader.pages:
                try:
                    page_text = page.extract_text() or ""
                except Exception:
                    page_text = ""
                parts.append(page_text)
                total += len(page_text)
                if sum(len(p) for p in parts) > max_chars:
                    break
            text = "\n\n".join(parts)
            return text[:max_chars], total
        except Exception as exc:
            note = f"[PDF detected but extraction failed: {exc}]"
            return note, len(body)

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "url" not in kwargs:
            return False, "Missing required parameter: url"
        if not isinstance(kwargs["url"], str):
            return False, "Parameter 'url' must be a string"
        return True, None
