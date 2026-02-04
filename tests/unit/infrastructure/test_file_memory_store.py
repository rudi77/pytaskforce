"""Unit tests for file-backed memory store."""

import asyncio
from pathlib import Path

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
