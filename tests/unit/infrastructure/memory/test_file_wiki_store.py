"""Tests for FileWikiStore CRUD + search."""

from __future__ import annotations

from pathlib import Path

import pytest

from taskforce.core.domain.wiki_page import WikiPage
from taskforce.infrastructure.memory.file_wiki_store import FileWikiStore


@pytest.fixture
def store(tmp_path: Path) -> FileWikiStore:
    return FileWikiStore(tmp_path / "wiki")


async def test_write_and_read_page(store: FileWikiStore) -> None:
    page = WikiPage(
        name="entities/steuerberater-mueller",
        title="Steuerberater Mueller",
        body="## Kontakt\n- Tel: 0664-1234567\n",
        tags=["kontakt", "steuer"],
    )
    await store.write_page(page)

    loaded = await store.get_page("entities/steuerberater-mueller")
    assert loaded is not None
    assert loaded.title == "Steuerberater Mueller"
    assert loaded.kind == "entities"
    assert "0664-1234567" in loaded.body
    assert loaded.tags == ["kontakt", "steuer"]


async def test_list_pages_skips_index_and_log(
    store: FileWikiStore, tmp_path: Path
) -> None:
    await store.write_page(WikiPage(name="entities/a", title="A", body="body"))
    await store.append_log("first entry")

    pages = await store.list_pages()
    assert {p.name for p in pages} == {"entities/a"}
    assert (tmp_path / "wiki" / "index.md").exists()
    assert (tmp_path / "wiki" / "log.md").exists()


async def test_write_refreshes_index(store: FileWikiStore) -> None:
    await store.write_page(WikiPage(name="entities/mueller", title="Mueller", body="x"))
    await store.write_page(
        WikiPage(name="preferences/formats", title="Formats", body="pref")
    )
    index = await store.read_index()
    assert "[Mueller](entities/mueller.md)" in index
    assert "[Formats](preferences/formats.md)" in index


async def test_update_section_append(store: FileWikiStore) -> None:
    await store.write_page(
        WikiPage(
            name="entities/mueller",
            title="Mueller",
            body="## Kontakt\n- Tel: 0664-1234567\n",
        )
    )
    updated = await store.update_section(
        "entities/mueller", "Kontakt", "- Fax: 0664-9999", mode="append"
    )
    assert updated is not None
    assert "0664-1234567" in updated.body
    assert "0664-9999" in updated.body


async def test_update_section_replace(store: FileWikiStore) -> None:
    await store.write_page(
        WikiPage(
            name="entities/mueller",
            title="Mueller",
            body="## Kontakt\n- Tel: alt\n",
        )
    )
    updated = await store.update_section(
        "entities/mueller", "Kontakt", "- Tel: neu", mode="replace"
    )
    assert updated is not None
    assert "alt" not in updated.body
    assert "neu" in updated.body


async def test_update_section_on_missing_page_returns_none(store: FileWikiStore) -> None:
    result = await store.update_section("entities/ghost", "X", "foo")
    assert result is None


async def test_delete_page(store: FileWikiStore) -> None:
    await store.write_page(WikiPage(name="entities/x", title="X", body="body"))
    assert await store.delete_page("entities/x") is True
    assert await store.get_page("entities/x") is None
    assert await store.delete_page("entities/x") is False


async def test_search_ranks_title_matches_higher(store: FileWikiStore) -> None:
    await store.write_page(
        WikiPage(name="entities/mueller", title="Steuerberater Mueller", body="x")
    )
    await store.write_page(
        WikiPage(name="concepts/tax", title="Tax Workflow", body="Mueller mentioned")
    )
    results = await store.search("Mueller", limit=5)
    assert results
    assert results[0].name == "entities/mueller"


async def test_search_empty_query_returns_empty(store: FileWikiStore) -> None:
    await store.write_page(WikiPage(name="entities/a", title="A", body="body"))
    assert await store.search("") == []


async def test_rejects_reserved_names(store: FileWikiStore) -> None:
    with pytest.raises(ValueError):
        await store.write_page(WikiPage(name="index", title="oops", body=""))
    with pytest.raises(ValueError):
        await store.write_page(WikiPage(name="../escape", title="oops", body=""))


@pytest.mark.parametrize(
    "bad_name",
    [
        r"..\escape",                 # Windows backslash traversal
        r"entities\..\..\escape",     # mixed backslash traversal
        "C:/evil",                    # drive letter
        "C:\\evil",                   # drive letter (backslash)
        "/absolute/path",             # leading Unix slash
        "entities/../../etc/passwd",  # classic traversal
        "",                           # empty
    ],
)
async def test_rejects_malicious_names(store: FileWikiStore, bad_name: str) -> None:
    with pytest.raises(ValueError):
        await store.write_page(WikiPage(name=bad_name, title="oops", body=""))


async def test_append_log(store: FileWikiStore, tmp_path: Path) -> None:
    await store.append_log("first")
    await store.append_log("second")
    log = (tmp_path / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "first" in log
    assert "second" in log
    assert log.count("\n## [") == 2


async def test_write_preserves_created_at_on_rewrite(store: FileWikiStore) -> None:
    page = WikiPage(name="entities/x", title="X", body="first")
    await store.write_page(page)
    loaded = await store.get_page("entities/x")
    assert loaded is not None
    original_created = loaded.created_at

    rewritten = WikiPage(name="entities/x", title="X", body="second")
    await store.write_page(rewritten)
    reloaded = await store.get_page("entities/x")
    assert reloaded is not None
    assert reloaded.created_at == original_created
