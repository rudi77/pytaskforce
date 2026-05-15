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


# Opt-in injection config used by the legacy auto-injection tests. The
# loader's default config (issue #275) is no-injection; tests that
# exercise the injection rendering path need to flip the flags
# explicitly, mirroring what a profile would do via
# ``wiki.context_injection`` in YAML.
_INJECT_ON: dict[str, int | bool] = {"top_k_relevant": 5, "include_index": True}


@pytest.fixture
def loader(store: FileWikiStore) -> WikiContextLoader:
    return WikiContextLoader(
        wiki_store=store,
        config=WikiContextConfig(**_INJECT_ON),
        logger=structlog.get_logger("test"),
    )


async def test_default_config_disables_auto_injection(
    store: FileWikiStore,
) -> None:
    """Issue #275: ``WikiContextConfig()`` must not inject by default.

    Previously the defaults pushed the wiki index plus top-K body hooks
    into every system prompt, which leaked customer / invoice data into
    every LLM call and tripped Azure's content filter. The safe default
    is now off — profiles opt in explicitly.
    """
    await store.write_page(
        WikiPage(
            name="entities/mueller",
            title="Steuerberater Mueller",
            body="Tel: 0664-1234567",
        )
    )
    default_loader = WikiContextLoader(
        wiki_store=store,
        config=WikiContextConfig(),
        logger=structlog.get_logger("test"),
    )
    result = await default_loader.load_wiki_context(mission="Mueller Telefon")
    assert result is None


async def test_from_dict_defaults_disable_injection() -> None:
    """``WikiContextConfig.from_dict`` with an empty dict gives the
    same no-injection defaults as ``WikiContextConfig()``.
    """
    config = WikiContextConfig.from_dict({})
    assert config.top_k_relevant == 0
    assert config.include_index is False


async def test_returns_none_when_empty(loader: WikiContextLoader) -> None:
    result = await loader.load_wiki_context()
    # Empty wiki renders an index with placeholder text — still returned.
    # Caller decides whether to inject.
    assert result is None or "(no pages yet)" in result


async def test_index_and_relevant_combined(store: FileWikiStore, loader: WikiContextLoader) -> None:
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
        config=WikiContextConfig(max_total_chars=400, **_INJECT_ON),
        logger=structlog.get_logger("test"),
    )
    result = await tight.load_wiki_context(mission="lorem")
    assert result is not None
    # Header ~180 chars + budgeted body; upper bound generous.
    assert len(result) < 800
