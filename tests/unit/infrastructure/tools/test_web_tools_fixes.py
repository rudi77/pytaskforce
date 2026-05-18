"""Tests for web_tools fixes from issues #380 and #381.

#380 - web_fetch crashes on PDF URLs (UTF-8 decode error)
#381 - web_search cascade-fails on Brave endpoint flakiness
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskforce.infrastructure.tools.native.web_tools import WebFetchTool, WebSearchTool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A minimal 1-page valid PDF that pypdf can parse. Hard-coded bytes so the
# test has no external deps.
MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 100 100]/Contents 4 0 R"
    b"/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 44>>stream\n"
    b"BT /F1 12 Tf 10 50 Td (Hello from PDF) Tj ET\n"
    b"endstream endobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"xref\n0 6\n0000000000 65535 f\n0000000009 00000 n\n0000000054 00000 n\n"
    b"0000000098 00000 n\n0000000189 00000 n\n0000000269 00000 n\n"
    b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n329\n%%EOF\n"
)


def _mock_pdf_response(body: bytes, content_type: str = "application/pdf", status: int = 200):
    """aiohttp response mock that returns bytes via .read()."""
    response = AsyncMock()
    response.status = status
    response.headers = {"Content-Type": content_type}
    response.read = AsyncMock(return_value=body)
    # text() should NOT be called on PDFs; raise if it is.
    response.text = AsyncMock(side_effect=AssertionError(
        "response.text() called on a PDF response - PDF path should use .read()"
    ))
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)
    return response


def _session_returning(response):
    """ClientSession mock whose .get() returns the given response context."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.get = MagicMock(return_value=response)
    return session


# ---------------------------------------------------------------------------
# #380 - web_fetch handles PDFs without crashing
# ---------------------------------------------------------------------------

class TestPdfDetection:
    """Issue #380 helper: _looks_like_pdf works on the cases we care about."""

    @pytest.mark.parametrize("content_type,expected", [
        ("application/pdf", True),
        ("Application/PDF; charset=utf-8", True),
        ("text/html", False),
        ("application/json", False),
        ("", False),
    ])
    def test_by_content_type(self, content_type, expected):
        assert WebFetchTool._looks_like_pdf("https://example.com/x", content_type) is expected

    @pytest.mark.parametrize("url,expected", [
        ("https://example.com/foo.pdf", True),
        ("https://example.com/FOO.PDF", True),
        ("https://example.com/foo.pdf?v=1", True),
        ("https://example.com/foo.pdf#page=2", True),
        ("https://example.com/pdf-info", False),  # not a .pdf ending
        ("https://example.com/foo.html", False),
    ])
    def test_by_url_suffix(self, url, expected):
        assert WebFetchTool._looks_like_pdf(url, "") is expected


@pytest.mark.asyncio
class TestWebFetchPdfIssue380:
    """Issue #380: PDF URLs must not crash with utf-8 decode error."""

    async def test_pdf_url_returns_extracted_text(self):
        """Reproduces the Citroen-preisliste crash scenario from the butler benchmark."""
        tool = WebFetchTool()
        response = _mock_pdf_response(MINIMAL_PDF, content_type="application/pdf")
        session = _session_returning(response)

        with patch("taskforce.infrastructure.tools.native.web_tools.aiohttp.ClientSession",
                   return_value=session):
            result = await tool.execute(url="https://example.com/datasheet.pdf")

        assert result["success"] is True, f"PDF fetch should succeed, got {result}"
        assert result["content_type"] == "application/pdf"
        # pypdf may render the text with spacing artifacts; just check the
        # core word is in there (case-insensitive).
        assert "hello" in result["content"].lower() or "pdf" in result["content"].lower()
        # length = total extracted text length (analogous to len(html) for
        # the HTML path), not the raw PDF byte count.
        assert result["length"] > 0

    async def test_pdf_detected_by_url_suffix_even_without_content_type(self):
        """PDF URLs with empty/wrong Content-Type still get the PDF path."""
        tool = WebFetchTool()
        response = _mock_pdf_response(MINIMAL_PDF, content_type="application/octet-stream")
        session = _session_returning(response)

        with patch("taskforce.infrastructure.tools.native.web_tools.aiohttp.ClientSession",
                   return_value=session):
            result = await tool.execute(url="https://example.com/Preisliste_C3.pdf")

        assert result["success"] is True

    async def test_broken_pdf_returns_note_not_crash(self):
        """If pypdf chokes on garbage bytes, return a marker - never raise."""
        tool = WebFetchTool()
        response = _mock_pdf_response(b"not a real pdf at all", content_type="application/pdf")
        session = _session_returning(response)

        with patch("taskforce.infrastructure.tools.native.web_tools.aiohttp.ClientSession",
                   return_value=session):
            result = await tool.execute(url="https://example.com/broken.pdf")

        # Either success with a note OR failure - both fine, just NOT a raised exception.
        assert "success" in result


# ---------------------------------------------------------------------------
# #381 - web_search cascades through stable backends, retries each once
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestWebSearchRetryIssue381:
    """Issue #381: cascade through reliable backends, one retry per backend.

    Stable backend order is ``WebSearchTool.STABLE_BACKENDS``
    (duckduckgo, mojeek, yahoo). Each backend gets one retry on transient
    errors before moving to the next.
    """

    async def test_first_backend_succeeds_no_cascade(self):
        """duckduckgo returns results — mojeek/yahoo never called."""
        tool = WebSearchTool()
        calls: list[str] = []

        async def first_succeeds(query, num_results, snippet_max_chars, *, backend):
            calls.append(backend)
            return {"success": True, "query": query, "results": [], "count": 0}

        with patch.object(tool, "_search_ddgs", side_effect=first_succeeds):
            result = await tool.execute(query="test query")

        assert result["success"] is True
        assert calls == ["duckduckgo"]

    async def test_first_backend_retry_succeeds(self):
        """duckduckgo transient on attempt 1, OK on attempt 2 — no cascade."""
        tool = WebSearchTool()
        calls: list[str] = []
        n = {"i": 0}

        async def flaky_first(query, num_results, snippet_max_chars, *, backend):
            calls.append(backend)
            n["i"] += 1
            if n["i"] == 1:
                raise ConnectionError("ddg endpoint flake")
            return {"success": True, "query": query, "results": [], "count": 0}

        with patch.object(tool, "_search_ddgs", side_effect=flaky_first):
            with patch("taskforce.infrastructure.tools.native.web_tools.asyncio.sleep",
                       new=AsyncMock()):
                result = await tool.execute(query="test query")

        assert result["success"] is True
        # Two calls, both to first backend (one initial + one retry).
        assert calls == ["duckduckgo", "duckduckgo"]

    async def test_cascades_to_next_backend_on_failure(self):
        """duckduckgo always fails (both attempts) → mojeek succeeds."""
        tool = WebSearchTool()
        calls: list[str] = []

        async def cascade(query, num_results, snippet_max_chars, *, backend):
            calls.append(backend)
            if backend == "duckduckgo":
                raise ConnectionError("ddg down")
            return {"success": True, "query": query, "results": [], "count": 0}

        with patch.object(tool, "_search_ddgs", side_effect=cascade):
            with patch("taskforce.infrastructure.tools.native.web_tools.asyncio.sleep",
                       new=AsyncMock()):
                result = await tool.execute(query="test query")

        assert result["success"] is True
        # ddg called twice (initial + retry), then mojeek succeeds
        assert calls == ["duckduckgo", "duckduckgo", "mojeek"]

    async def test_all_backends_fail_returns_structured_error(self):
        """All STABLE_BACKENDS fail → structured error with attempted list."""
        tool = WebSearchTool()

        async def always_fail(query, num_results, snippet_max_chars, *, backend):
            raise ConnectionError(f"{backend} unreachable")

        with patch.object(tool, "_search_ddgs", side_effect=always_fail):
            with patch("taskforce.infrastructure.tools.native.web_tools.asyncio.sleep",
                       new=AsyncMock()):
                result = await tool.execute(query="test query")

        assert result["success"] is False
        assert result["details"].get("error_type_hint") == "search_backend_unavailable"
        assert result["details"].get("attempted_backends") == list(
            WebSearchTool.STABLE_BACKENDS
        )

    async def test_non_transient_error_moves_to_next_backend(self):
        """ValueError on duckduckgo (e.g. "No results") → try mojeek, not retry."""
        tool = WebSearchTool()
        calls: list[str] = []

        async def first_value_error_then_ok(query, num_results, snippet_max_chars, *, backend):
            calls.append(backend)
            if backend == "duckduckgo":
                raise ValueError("No results found.")
            return {"success": True, "query": query, "results": [], "count": 0}

        with patch.object(tool, "_search_ddgs", side_effect=first_value_error_then_ok):
            result = await tool.execute(query="test query")

        assert result["success"] is True
        # ddg called once (no retry for non-transient), then mojeek
        assert calls == ["duckduckgo", "mojeek"]

