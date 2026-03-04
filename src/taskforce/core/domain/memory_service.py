"""Unified memory service with human-like memory mechanics.

Extends the basic CRUD memory service with cognitive-science–inspired
operations:

- **Recall with reinforcement**: Retrieving a memory strengthens it
  (spaced repetition effect).
- **Forgetting / decay**: Periodic sweep weakens or archives memories
  whose effective strength falls below a configurable threshold.
- **Associative linking**: Automatically discovers and maintains
  bidirectional association links between semantically related memories.
- **Spreading activation**: When a memory is recalled, associated
  memories receive a transient strength boost so they surface more
  easily in subsequent retrievals.
"""

from __future__ import annotations

from datetime import UTC, datetime

from taskforce.core.domain.memory import (
    MemoryKind,
    MemoryRecord,
    MemoryScope,
)
from taskforce.core.interfaces.memory_store import MemoryStoreProtocol

# Memories below this effective strength are candidates for archival.
_FORGET_THRESHOLD: float = 0.10

# Spreading activation: fraction of source strength added to neighbours.
_ACTIVATION_SPREAD_FACTOR: float = 0.15

# Maximum association fan-out per memory.
_MAX_ASSOCIATIONS: int = 10


class MemoryService:
    """Orchestrates human-like memory operations.

    Acts as a facade over ``MemoryStoreProtocol`` adding strength
    management, associative linking, and decay.
    """

    def __init__(self, store: MemoryStoreProtocol) -> None:
        self._store = store

    # ------------------------------------------------------------------
    # Core CRUD (delegated)
    # ------------------------------------------------------------------

    async def remember(
        self,
        record: MemoryRecord,
        *,
        auto_associate: bool = True,
    ) -> MemoryRecord:
        """Encode a new memory, optionally discovering associations.

        Args:
            record: The memory to store.
            auto_associate: When ``True`` (default), searches for
                existing memories that share tags and creates
                bidirectional association links.

        Returns:
            The persisted record.
        """
        saved = await self._store.add(record)
        if auto_associate:
            await self._discover_associations(saved)
        return saved

    async def recall(
        self,
        query: str,
        scope: MemoryScope | None = None,
        kind: MemoryKind | None = None,
        limit: int = 10,
        *,
        reinforce: bool = True,
        spread_activation: bool = True,
    ) -> list[MemoryRecord]:
        """Search memories with optional reinforcement and spreading activation.

        Args:
            query: Search query string.
            scope: Filter by scope.
            kind: Filter by kind.
            limit: Maximum results.
            reinforce: Strengthen retrieved memories (spaced repetition).
            spread_activation: Boost associated memories on retrieval.

        Returns:
            Matching records sorted by combined relevance.
        """
        results = await self._store.search(
            query=query, scope=scope, kind=kind, limit=limit
        )
        now = datetime.now(UTC)
        for record in results:
            if reinforce:
                record.reinforce(now)
                await self._store.update(record)
            if spread_activation:
                await self._spread_activation(record, now)
        return results

    async def list_records(
        self,
        scope: MemoryScope | None = None,
        kind: MemoryKind | None = None,
    ) -> list[MemoryRecord]:
        """List memory records."""
        return await self._store.list(scope=scope, kind=kind)

    async def reinforce_by_id(self, record_id: str) -> MemoryRecord | None:
        """Explicitly reinforce a specific memory by ID.

        Returns:
            The reinforced record, or ``None`` if not found.
        """
        record = await self._store.get(record_id)
        if not record:
            return None
        record.reinforce()
        return await self._store.update(record)

    # ------------------------------------------------------------------
    # Associative memory network
    # ------------------------------------------------------------------

    async def associate(self, id_a: str, id_b: str) -> bool:
        """Create a bidirectional association between two memories.

        Returns:
            ``True`` if the link was created (or already existed).
        """
        rec_a = await self._store.get(id_a)
        rec_b = await self._store.get(id_b)
        if not rec_a or not rec_b:
            return False
        rec_a.associate_with(id_b)
        rec_b.associate_with(id_a)
        await self._store.update(rec_a)
        await self._store.update(rec_b)
        return True

    async def get_associated(
        self,
        record_id: str,
        *,
        depth: int = 1,
    ) -> list[MemoryRecord]:
        """Retrieve memories associated with the given record.

        Args:
            record_id: Source memory ID.
            depth: How many hops to follow (1 = direct neighbours only).

        Returns:
            Associated records (excluding the source).
        """
        visited: set[str] = {record_id}
        frontier: list[str] = [record_id]
        results: list[MemoryRecord] = []
        for _ in range(depth):
            next_frontier: list[str] = []
            for fid in frontier:
                rec = await self._store.get(fid)
                if not rec:
                    continue
                for assoc_id in rec.associations:
                    if assoc_id not in visited:
                        visited.add(assoc_id)
                        assoc = await self._store.get(assoc_id)
                        if assoc:
                            results.append(assoc)
                            next_frontier.append(assoc_id)
            frontier = next_frontier
        return results

    # ------------------------------------------------------------------
    # Forgetting / decay sweep
    # ------------------------------------------------------------------

    async def decay_sweep(
        self,
        threshold: float = _FORGET_THRESHOLD,
        *,
        archive: bool = True,
    ) -> tuple[int, int]:
        """Run a forgetting sweep across all memories.

        Calculates the effective strength of every record.  Records
        below *threshold* are either archived (tagged ``archived``) or
        deleted.

        Args:
            threshold: Effective strength below which memories are
                forgotten.
            archive: If ``True`` (default), weak memories are tagged
                ``archived`` instead of deleted.

        Returns:
            Tuple of (decayed_count, archived_or_deleted_count).
        """
        all_records = await self._store.list()
        now = datetime.now(UTC)
        decayed = 0
        forgotten = 0
        for record in all_records:
            eff = record.effective_strength(now)
            if eff < threshold:
                if archive:
                    if "archived" not in record.tags:
                        record.tags.append("archived")
                        record.strength = eff
                        await self._store.update(record)
                else:
                    await self._store.delete(record.id)
                forgotten += 1
            elif eff < record.strength * 0.9:
                # Persist the natural decay into the stored strength.
                record.strength = eff
                await self._store.update(record)
                decayed += 1
        return decayed, forgotten

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _discover_associations(self, record: MemoryRecord) -> None:
        """Find existing memories that share tags and create links."""
        if not record.tags:
            return
        query = " ".join(record.tags[:5])
        candidates = await self._store.search(query=query, limit=_MAX_ASSOCIATIONS + 1)
        for candidate in candidates:
            if candidate.id == record.id:
                continue
            if len(record.associations) >= _MAX_ASSOCIATIONS:
                break
            shared = set(record.tags) & set(candidate.tags)
            if shared:
                record.associate_with(candidate.id)
                candidate.associate_with(record.id)
                await self._store.update(candidate)
        if record.associations:
            await self._store.update(record)

    async def _spread_activation(
        self,
        source: MemoryRecord,
        now: datetime,
    ) -> None:
        """Boost associated memories when *source* is retrieved.

        Implements a single-hop spreading activation: each direct
        neighbour receives a fraction of the source's effective
        strength as a temporary boost.
        """
        if not source.associations:
            return
        source_eff = source.effective_strength(now)
        boost = source_eff * _ACTIVATION_SPREAD_FACTOR
        for assoc_id in source.associations:
            neighbour = await self._store.get(assoc_id)
            if neighbour:
                neighbour.strength = min(1.0, neighbour.strength + boost)
                neighbour.touch()
                await self._store.update(neighbour)
