"""Interfaces for memory stores."""

from __future__ import annotations

import builtins
from typing import Protocol

from taskforce.core.domain.memory import MemoryKind, MemoryRecord, MemoryScope


class MemoryStoreProtocol(Protocol):
    """Protocol for memory persistence implementations."""

    async def add(self, record: MemoryRecord) -> MemoryRecord:
        """Add a new memory record."""
        ...

    async def get(self, record_id: str) -> MemoryRecord | None:
        """Get a memory record by ID."""
        ...

    async def list(
        self,
        scope: MemoryScope | None = None,
        kind: MemoryKind | None = None,
    ) -> list[MemoryRecord]:
        """List memory records by scope and kind."""
        ...

    async def search(
        self,
        query: str,
        scope: MemoryScope | None = None,
        kind: MemoryKind | None = None,
        limit: int = 10,
    ) -> builtins.list[MemoryRecord]:
        """Search memory records by query."""
        ...

    async def update(self, record: MemoryRecord) -> MemoryRecord:
        """Update an existing memory record."""
        ...

    async def delete(self, record_id: str) -> bool:
        """Delete a memory record by ID."""
        ...
