"""Unified memory service."""

from __future__ import annotations

from taskforce.core.domain.memory import MemoryKind, MemoryRecord, MemoryScope
from taskforce.core.interfaces.memory_store import MemoryStoreProtocol


class MemoryService:
    """Orchestrates short-term and long-term memory operations."""

    def __init__(self, store: MemoryStoreProtocol) -> None:
        self._store = store

    async def remember(self, record: MemoryRecord) -> MemoryRecord:
        """Store a memory record."""
        return await self._store.add(record)

    async def recall(
        self,
        query: str,
        scope: MemoryScope | None = None,
        kind: MemoryKind | None = None,
        limit: int = 10,
    ) -> list[MemoryRecord]:
        """Search memory records."""
        return await self._store.search(query=query, scope=scope, kind=kind, limit=limit)

    async def list_records(
        self,
        scope: MemoryScope | None = None,
        kind: MemoryKind | None = None,
    ) -> list[MemoryRecord]:
        """List memory records."""
        return await self._store.list(scope=scope, kind=kind)
