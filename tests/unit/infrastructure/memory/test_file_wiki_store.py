"""Tests for FileWikiStore CRUD + search."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from taskforce.core.domain.wiki_page import WikiPage
from taskforce.infrastructure.memory.file_wiki_store import FileWikiStore


@pytest.fixture
def store(tmp_path: Path) -> FileWikiStore:
    return FileWikiStore(tmp_path / "wiki")


@pytest.mark.spec("wiki-memory.write_page_creates_file_and_refreshes_index")
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


@pytest.mark.spec("wiki-memory.write_page_creates_file_and_refreshes_index")
async def test_write_refreshes_index(store: FileWikiStore) -> None:
    await store.write_page(WikiPage(name="entities/mueller", title="Mueller", body="x"))
    await store.write_page(
        WikiPage(name="preferences/formats", title="Formats", body="pref")
    )
    index = await store.read_index()
    assert "[Mueller](entities/mueller.md)" in index
    assert "[Formats](preferences/formats.md)" in index


@pytest.mark.spec("wiki-memory.update_section_append_keeps_other_sections")
async def test_update_section_append_keeps_other_sections(store: FileWikiStore) -> None:
    """Appending to one section leaves every other section intact."""
    await store.write_page(
        WikiPage(
            name="entities/mueller",
            title="Mueller",
            body="## Kontakt\n- Tel: 0664-1234567\n\n## Notizen\n- mag PDF-Rechnungen\n",
        )
    )
    updated = await store.update_section(
        "entities/mueller", "Kontakt", "- Fax: 0664-9999", mode="append"
    )
    assert updated is not None
    assert "0664-9999" in updated.body            # appended content
    assert "0664-1234567" in updated.body         # original target content kept
    assert "mag PDF-Rechnungen" in updated.body   # sibling section untouched


@pytest.mark.spec("wiki-memory.update_section_replace_overwrites_only_target")
async def test_update_section_replace_overwrites_only_target(
    store: FileWikiStore,
) -> None:
    """Replace mode overwrites only the target section, not its siblings."""
    await store.write_page(
        WikiPage(
            name="entities/mueller",
            title="Mueller",
            body="## Kontakt\n- Tel: alt\n\n## Notizen\n- bevorzugt E-Mail\n",
        )
    )
    updated = await store.update_section(
        "entities/mueller", "Kontakt", "- Tel: neu", mode="replace"
    )
    assert updated is not None
    assert "alt" not in updated.body              # target section overwritten
    assert "neu" in updated.body
    assert "bevorzugt E-Mail" in updated.body     # sibling section preserved


@pytest.mark.spec("wiki-memory.delete_page_removes_file_and_refreshes_index")
async def test_delete_page_refreshes_index(store: FileWikiStore) -> None:
    """Deleting a page drops it from index.md but leaves other pages listed."""
    await store.write_page(WikiPage(name="entities/keep", title="Keep", body="x"))
    await store.write_page(WikiPage(name="entities/drop", title="Drop", body="y"))

    assert await store.delete_page("entities/drop") is True

    index = await store.read_index()
    assert "entities/keep.md" in index
    assert "entities/drop.md" not in index


@pytest.mark.spec("wiki-memory.update_section_append_keeps_other_sections")
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


@pytest.mark.spec("wiki-memory.update_section_replace_overwrites_only_target")
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


@pytest.mark.spec("wiki-memory.delete_page_removes_file_and_refreshes_index")
async def test_delete_page(store: FileWikiStore) -> None:
    await store.write_page(WikiPage(name="entities/x", title="X", body="body"))
    assert await store.delete_page("entities/x") is True
    assert await store.get_page("entities/x") is None
    assert await store.delete_page("entities/x") is False


@pytest.mark.spec("wiki-memory.search_ranks_title_hits_above_body_hits")
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


@pytest.mark.spec("wiki-memory.empty_query_returns_no_results")
async def test_search_empty_query_returns_empty(store: FileWikiStore) -> None:
    await store.write_page(WikiPage(name="entities/a", title="A", body="body"))
    assert await store.search("") == []


@pytest.mark.spec("wiki-memory.page_name_rejects_reserved_names")
@pytest.mark.spec("wiki-memory.page_name_rejects_path_traversal")
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
@pytest.mark.spec("wiki-memory.page_name_rejects_path_traversal")
async def test_rejects_malicious_names(store: FileWikiStore, bad_name: str) -> None:
    with pytest.raises(ValueError):
        await store.write_page(WikiPage(name=bad_name, title="oops", body=""))


@pytest.mark.spec("wiki-memory.log_is_append_only_and_timestamped")
async def test_append_log(store: FileWikiStore, tmp_path: Path) -> None:
    await store.append_log("first")
    await store.append_log("second")
    log = (tmp_path / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "first" in log
    assert "second" in log
    assert log.count("\n## [") == 2


# ---------------------------------------------------------------------------
# Concurrency (#307) — no lost updates under parallel writers
# ---------------------------------------------------------------------------


async def test_concurrent_update_section_no_lost_update(store: FileWikiStore) -> None:
    """20 parallel appends to one section all survive — no lost update.

    Without a per-page lock each ``update_section`` reads the page,
    appends to its own copy and writes it back; concurrent writers
    clobber each other and only a fraction of the lines survive.
    """
    await store.write_page(
        WikiPage(name="entities/mueller", title="Mueller", body="## Notes\n")
    )

    await asyncio.gather(
        *(
            store.update_section(
                "entities/mueller", "Notes", f"- entry {i}", mode="append"
            )
            for i in range(20)
        )
    )

    final = await store.get_page("entities/mueller")
    assert final is not None
    for i in range(20):
        assert f"- entry {i}" in final.body, f"lost update: entry {i} missing"


async def test_concurrent_append_log_no_lost_entries(
    store: FileWikiStore, tmp_path: Path
) -> None:
    """Parallel append_log calls all land — the log is read-modify-write."""
    await asyncio.gather(*(store.append_log(f"entry-{i}") for i in range(20)))

    log = (tmp_path / "wiki" / "log.md").read_text(encoding="utf-8")
    for i in range(20):
        assert f"entry-{i}" in log, f"lost log entry-{i}"


async def test_concurrent_write_page_distinct_pages_all_indexed(
    store: FileWikiStore,
) -> None:
    """Parallel writes of distinct pages all end up in the refreshed index."""
    await asyncio.gather(
        *(
            store.write_page(
                WikiPage(name=f"entities/p{i}", title=f"P{i}", body="x")
            )
            for i in range(20)
        )
    )

    index = await store.read_index()
    for i in range(20):
        assert f"entities/p{i}.md" in index, f"page p{i} missing from index"


@pytest.mark.spec("wiki-memory.write_page_preserves_created_at_on_overwrite")
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
