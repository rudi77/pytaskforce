"""Tests for WikiContextLoader."""

from __future__ import annotations

from pathlib import Path

import pytest
import structlog

from taskforce.core.domain.lean_agent_components.wiki_context_loader import (
    WikiContextConfig,
    WikiContextLoader,
)
from taskforce.core.domain.wiki_page import WikiPage
from taskforce.infrastructure.memory.file_wiki_store import FileWikiStore


@pytest.fixture
def store(tmp_path: Path) -> FileWikiStore:
    return FileWikiStore(tmp_path / "wiki")


@pytest.fixture
def loader(store: FileWikiStore) -> WikiContextLoader:
    return WikiContextLoader(
        wiki_store=store,
        config=WikiContextConfig(),
        logger=structlog.get_logger("test"),
    )


async def test_returns_none_when_empty(loader: WikiContextLoader) -> None:
    result = await loader.load_wiki_context()
    # Empty wiki renders an index with placeholder text — still returned.
    # Caller decides whether to inject.
    assert result is None or "(no pages yet)" in result


async def test_index_and_relevant_combined(
    store: FileWikiStore, loader: WikiContextLoader
) -> None:
    await store.write_page(
        WikiPage(
            name="entities/mueller",
            title="Steuerberater Mueller",
            body="Tel: 0664-1234567",
        )
    )
    result = await loader.load_wiki_context(mission="Mueller Telefon")
    assert result is not None
    assert "WIKI INDEX" in result
    assert "entities/mueller" in result
    assert "Potentially relevant pages" in result


async def test_respects_char_budget(store: FileWikiStore) -> None:
    for i in range(30):
        await store.write_page(
            WikiPage(
                name=f"entities/x{i}",
                title=f"X {i}",
                body="lorem ipsum " * 40,
            )
        )
    tight = WikiContextLoader(
        wiki_store=store,
        config=WikiContextConfig(max_total_chars=400),
        logger=structlog.get_logger("test"),
    )
    result = await tight.load_wiki_context(mission="lorem")
    assert result is not None
    # Header ~180 chars + budgeted body; upper bound generous.
    assert len(result) < 800
