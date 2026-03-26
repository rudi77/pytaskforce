"""Unit tests for the SLM context enricher."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from taskforce.core.domain.context_enricher import (
    EnricherConfig,
    EnrichmentCategory,
)
from taskforce.core.domain.memory import MemoryKind, MemoryRecord, MemoryScope
from taskforce.infrastructure.memory.slm_context_enricher import SLMContextEnricher


def _make_memory(content: str, tags: list[str] | None = None) -> MemoryRecord:
    """Create a simple memory record for testing."""
    return MemoryRecord(
        scope=MemoryScope.USER,
        kind=MemoryKind.LONG_TERM,
        content=content,
        tags=tags or [],
    )


def _make_llm_mock(response_content: str = "") -> AsyncMock:
    """Create a mock LLM provider that returns the given content."""
    mock = AsyncMock()
    mock.complete = AsyncMock(return_value={"content": response_content})
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_enricher_returns_none_when_disabled() -> None:
    """Disabled enricher returns None without calling LLM."""
    llm = _make_llm_mock()
    config = EnricherConfig(enabled=False)
    enricher = SLMContextEnricher(llm_provider=llm, config=config)

    result = await enricher.enrich("Fix the bug", [_make_memory("some fact")])

    assert result is None
    llm.complete.assert_not_awaited()


async def test_enricher_returns_none_when_no_memories() -> None:
    """Enricher returns None when there are no memories to process."""
    llm = _make_llm_mock()
    config = EnricherConfig(enabled=True)
    enricher = SLMContextEnricher(llm_provider=llm, config=config)

    result = await enricher.enrich("Fix the bug", [])

    assert result is None
    llm.complete.assert_not_awaited()


async def test_enricher_generates_intuition() -> None:
    """Enricher produces formatted intuition block from SLM response."""
    slm_output = (
        "[Factual]\n"
        "- We discussed this bug in December.\n\n"
        "[Behavioral]\n"
        "- User prefers concise tracebacks.\n"
    )
    llm = _make_llm_mock(slm_output)
    config = EnricherConfig(enabled=True, model_alias="slm")
    enricher = SLMContextEnricher(llm_provider=llm, config=config)

    memories = [
        _make_memory("Bug discussion in December", tags=["bug"]),
        _make_memory("User prefers short output", tags=["preference"]),
    ]
    result = await enricher.enrich("Fix the database bug", memories)

    assert result is not None
    assert "## Internal Intuition" in result
    assert "We discussed this bug in December" in result
    llm.complete.assert_awaited_once()

    # Verify model alias was passed
    call_kwargs = llm.complete.call_args
    assert call_kwargs.kwargs.get("model") == "slm" or call_kwargs[1].get("model") == "slm"


async def test_enricher_graceful_on_llm_error() -> None:
    """Enricher returns None when LLM call fails."""
    llm = AsyncMock()
    llm.complete = AsyncMock(side_effect=RuntimeError("connection refused"))
    config = EnricherConfig(enabled=True, timeout_seconds=2.0)
    enricher = SLMContextEnricher(llm_provider=llm, config=config)

    result = await enricher.enrich("Fix the bug", [_make_memory("some fact")])

    assert result is None


async def test_enricher_graceful_on_timeout() -> None:
    """Enricher returns None when SLM call exceeds timeout."""
    import asyncio

    async def slow_complete(**kwargs: Any) -> dict[str, Any]:
        await asyncio.sleep(10)
        return {"content": "too late"}

    llm = AsyncMock()
    llm.complete = slow_complete
    config = EnricherConfig(enabled=True, timeout_seconds=0.1)
    enricher = SLMContextEnricher(llm_provider=llm, config=config)

    result = await enricher.enrich("Fix the bug", [_make_memory("fact")])

    assert result is None


async def test_enricher_returns_none_on_empty_response() -> None:
    """Enricher returns None when SLM returns empty string."""
    llm = _make_llm_mock("   ")
    config = EnricherConfig(enabled=True)
    enricher = SLMContextEnricher(llm_provider=llm, config=config)

    result = await enricher.enrich("Fix the bug", [_make_memory("fact")])

    assert result is None


async def test_enricher_respects_category_selection() -> None:
    """Prompt categories section only includes requested categories."""
    llm = _make_llm_mock("[Factual]\n- A fact.")
    config = EnricherConfig(
        enabled=True,
        categories=[EnrichmentCategory.FACTUAL],
    )
    enricher = SLMContextEnricher(llm_provider=llm, config=config)

    await enricher.enrich("test", [_make_memory("fact")])

    call_kwargs = llm.complete.call_args
    prompt = call_kwargs.kwargs.get("messages", call_kwargs[1].get("messages", []))[0]["content"]
    # The categories instruction section should only list Factual
    categories_section = prompt.split("### Requested categories")[1].split("### Current mission")[0]
    assert "Factual" in categories_section
    assert "Behavioral" not in categories_section
    assert "Dreamed" not in categories_section
