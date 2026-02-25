"""Unit tests for file-backed memory store."""

import asyncio
from pathlib import Path

import pytest

from taskforce.core.domain.memory import MemoryKind, MemoryRecord, MemoryScope
from taskforce.infrastructure.memory.file_memory_store import FileMemoryStore


def test_file_memory_store_crud(tmp_path: Path) -> None:
    """Verify add/get/update/delete operations."""

    async def _run_test() -> None:
        store = FileMemoryStore(tmp_path)
        record = MemoryRecord(
            scope=MemoryScope.PROFILE,
            kind=MemoryKind.LONG_TERM,
            content="Initial",
            tags=["tag"],
        )

        saved = await store.add(record)
        fetched = await store.get(saved.id)
        assert fetched is not None
        assert fetched.content == "Initial"

        fetched.content = "Updated"
        updated = await store.update(fetched)
        assert updated.content == "Updated"

        deleted = await store.delete(updated.id)
        assert deleted is True

    asyncio.run(_run_test())


def test_file_memory_store_search(tmp_path: Path) -> None:
    """Verify search filters by query."""

    async def _run_test() -> None:
        store = FileMemoryStore(tmp_path)
        await store.add(
            MemoryRecord(
                scope=MemoryScope.PROFILE,
                kind=MemoryKind.LONG_TERM,
                content="Alpha content",
                tags=["alpha"],
            )
        )
        await store.add(
            MemoryRecord(
                scope=MemoryScope.PROFILE,
                kind=MemoryKind.LONG_TERM,
                content="Beta content",
                tags=["beta"],
            )
        )

        matches = await store.search("alpha", scope=MemoryScope.PROFILE)
        assert len(matches) == 1
        assert matches[0].content == "Alpha content"

    asyncio.run(_run_test())


# ------------------------------------------------------------------
# Word-based search tests
# ------------------------------------------------------------------


@pytest.fixture()
def memory_store(tmp_path: Path) -> FileMemoryStore:
    """Create a fresh FileMemoryStore for each test."""
    return FileMemoryStore(tmp_path)


def _make_record(content: str, tags: list[str] | None = None) -> MemoryRecord:
    return MemoryRecord(
        scope=MemoryScope.PROFILE,
        kind=MemoryKind.LONG_TERM,
        content=content,
        tags=tags or [],
    )


async def _seed_accounting_records(store: FileMemoryStore) -> None:
    """Seed records that mimic the accounting agent use-case."""
    await store.add(
        _make_record(
            "Alle Getraenke sollen immer auf das Konto 4900 gebucht werden",
            tags=["Buchungsregel", "Getraenke"],
        )
    )
    await store.add(
        _make_record(
            "Bueromaterial wird auf Konto 6815 gebucht",
            tags=["Buchungsregel", "Bueromaterial"],
        )
    )
    await store.add(
        _make_record(
            "Steuernummer des Mandanten: 12/345/67890",
            tags=["Stammdaten"],
        )
    )


@pytest.mark.asyncio
async def test_search_multi_word_query_all_match(memory_store: FileMemoryStore) -> None:
    """Multi-word query where all words match returns the best result first."""
    await _seed_accounting_records(memory_store)

    matches = await memory_store.search("Buchungsregel Getraenke")
    assert len(matches) >= 1
    # The record with BOTH words matching should be first
    assert "4900" in matches[0].content


@pytest.mark.asyncio
async def test_search_multi_word_partial_match_still_returns(
    memory_store: FileMemoryStore,
) -> None:
    """If only some query words match, the record is still returned (OR logic)."""
    await _seed_accounting_records(memory_store)

    # "Buchungsregel" matches 2 records, "Reisekosten" matches nothing
    matches = await memory_store.search("Buchungsregel Reisekosten")
    assert len(matches) == 2  # Both Buchungsregel records found


@pytest.mark.asyncio
async def test_search_no_words_match_returns_nothing(
    memory_store: FileMemoryStore,
) -> None:
    """If NO query words match any record, nothing is returned."""
    await _seed_accounting_records(memory_store)

    matches = await memory_store.search("Reisekosten Flugtickets")
    assert len(matches) == 0


@pytest.mark.asyncio
async def test_search_results_ranked_by_relevance(
    memory_store: FileMemoryStore,
) -> None:
    """Results are sorted by number of matching words (most relevant first)."""
    await _seed_accounting_records(memory_store)

    # "Buchungsregel" matches 2 records, "Getraenke" matches only the first
    matches = await memory_store.search("Buchungsregel Getraenke")
    assert len(matches) == 2
    # First result should have 2 word hits (Buchungsregel + Getraenke)
    assert "4900" in matches[0].content
    # Second result should have only 1 word hit (Buchungsregel)
    assert "6815" in matches[1].content


@pytest.mark.asyncio
async def test_search_german_plural_prefix_matching(
    memory_store: FileMemoryStore,
) -> None:
    """Plural 'Buchungsregeln' finds singular tag 'Buchungsregel' via prefix."""
    await _seed_accounting_records(memory_store)

    matches = await memory_store.search("Buchungsregeln")
    assert len(matches) == 2  # Both Buchungsregel-tagged records


@pytest.mark.asyncio
async def test_search_single_word_still_works(memory_store: FileMemoryStore) -> None:
    """Single-word queries still work as before."""
    await _seed_accounting_records(memory_store)

    matches = await memory_store.search("Stammdaten")
    assert len(matches) == 1
    assert "Steuernummer" in matches[0].content


@pytest.mark.asyncio
async def test_search_case_insensitive(memory_store: FileMemoryStore) -> None:
    """Search is case-insensitive."""
    await _seed_accounting_records(memory_store)

    matches = await memory_store.search("buchungsregel getraenke")
    # First hit has both words, second has only "buchungsregel"
    assert len(matches) >= 1
    assert "4900" in matches[0].content


@pytest.mark.asyncio
async def test_search_empty_query_returns_nothing(
    memory_store: FileMemoryStore,
) -> None:
    """An empty query returns no results."""
    await _seed_accounting_records(memory_store)

    matches = await memory_store.search("")
    assert len(matches) == 0

    matches = await memory_store.search("   ")
    assert len(matches) == 0


@pytest.mark.asyncio
async def test_search_respects_limit(memory_store: FileMemoryStore) -> None:
    """Search respects the limit parameter."""
    await _seed_accounting_records(memory_store)

    matches = await memory_store.search("Konto", limit=1)
    assert len(matches) == 1


@pytest.mark.asyncio
async def test_search_real_accounting_query(memory_store: FileMemoryStore) -> None:
    """Reproduce the exact failing scenario from the accounting agent.

    The LLM searches for 'Buchungsregeln Kontierung' but the stored
    record has tag 'Buchungsregel' and content about 'Getränke/Konto 4900'.
    'Kontierung' does not appear anywhere in the record, but
    'Buchungsregeln' should still match via prefix on 'Buchungsregel'.
    """
    await memory_store.add(
        _make_record(
            "Alle Getränke sollen immer auf das Konto 4900 gebucht werden",
            tags=["Buchungsregel", "Getränke", "Konto4900"],
        )
    )

    matches = await memory_store.search("Buchungsregeln Kontierung")
    assert len(matches) == 1
    assert "4900" in matches[0].content


@pytest.mark.asyncio
async def test_word_matches_short_word_no_prefix(
    memory_store: FileMemoryStore,
) -> None:
    """Words <= 4 chars do not use prefix matching."""
    assert FileMemoryStore._word_matches("test", "testing ground") is True
    assert FileMemoryStore._word_matches("xyz", "testing ground") is False
    # "test" is exactly 4 chars, no prefix match attempted
    assert FileMemoryStore._word_matches("tess", "testing ground") is False


@pytest.mark.asyncio
async def test_word_matches_long_word_prefix(memory_store: FileMemoryStore) -> None:
    """Words > 4 chars fall back to prefix matching."""
    # "regeln" (6 chars) → prefix "regel" matches "buchungsregel"
    assert FileMemoryStore._word_matches("regeln", "buchungsregel") is True
    # Exact match also works
    assert FileMemoryStore._word_matches("buchungsregel", "buchungsregel") is True
    # No match at all
    assert FileMemoryStore._word_matches("reisekosten", "buchungsregel") is False
