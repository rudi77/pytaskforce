"""Tests for wiki_lint_service."""

from __future__ import annotations

from pathlib import Path

import pytest

from taskforce.application.wiki_lint_service import lint_wiki
from taskforce.core.domain.wiki_page import WikiPage
from taskforce.infrastructure.memory.file_wiki_store import FileWikiStore


@pytest.fixture
def store(tmp_path: Path) -> FileWikiStore:
    return FileWikiStore(tmp_path / "wiki")


async def test_clean_wiki_has_no_issues(store: FileWikiStore) -> None:
    await store.write_page(
        WikiPage(name="entities/a", title="A", body="See [[entities/b]].")
    )
    await store.write_page(
        WikiPage(name="entities/b", title="B", body="See [[entities/a]].")
    )
    report = await lint_wiki(store)
    assert report.is_clean


async def test_detects_orphans(store: FileWikiStore) -> None:
    await store.write_page(WikiPage(name="entities/a", title="A", body="content"))
    report = await lint_wiki(store)
    assert any(i.kind == "orphan" and "entities/a" in i.message for i in report.issues)


async def test_detects_broken_links(store: FileWikiStore) -> None:
    await store.write_page(
        WikiPage(name="entities/a", title="A", body="See [[entities/ghost]].")
    )
    report = await lint_wiki(store)
    assert any(i.kind == "broken_link" for i in report.issues)


async def test_detects_duplicate_titles(store: FileWikiStore) -> None:
    await store.write_page(WikiPage(name="entities/a", title="Shared", body="[[entities/b]]"))
    await store.write_page(WikiPage(name="entities/b", title="Shared", body="[[entities/a]]"))
    report = await lint_wiki(store)
    assert any(i.kind == "duplicate_title" for i in report.issues)
