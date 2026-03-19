"""File-backed memory store with in-memory cache.

Supports the enhanced human-like memory model: new fields (strength,
access_count, last_accessed, emotional_valence, importance,
associations, decay_rate) are serialized alongside the original fields.
Legacy records without these fields are loaded with sensible defaults.

The in-memory cache avoids repeated YAML parsing on every operation.
Records are loaded once and kept in memory; writes flush to disk
immediately.  The cache is invalidated when the file's mtime changes
(e.g. another process modified it).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
import yaml

from taskforce.core.domain.memory import (
    EmotionalValence,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
)
from taskforce.core.interfaces.memory_store import MemoryStoreProtocol

logger = structlog.get_logger(__name__)


class FileMemoryStore(MemoryStoreProtocol):
    """Persist memory records in a single Markdown file (``memory.md``).

    All records are stored as YAML documents separated by ``---`` inside a
    single file.  An in-memory cache avoids re-parsing the file on every
    read.  Writes flush to disk immediately and update the cache.

    When an ``EmbeddingProviderProtocol`` is provided, ``search()`` uses
    semantic (cosine-similarity) matching in addition to keyword matching.
    Without it, falls back to pure keyword search.

    Args:
        base_dir: Path that is either a ``.md`` file or a directory.
            * If it ends with ``.md`` → used as-is (e.g. ``work_dir/memory.md``).
            * Otherwise treated as a directory and ``memory.md`` is appended.
        embedding_provider: Optional embedding service for semantic search.
    """

    def __init__(
        self,
        base_dir: str | Path,
        embedding_provider: Any | None = None,
    ) -> None:
        path = Path(base_dir)
        if path.suffix == ".md":
            self._file = path
        else:
            self._file = path / "memory.md"
        self._file.parent.mkdir(parents=True, exist_ok=True)
        # In-memory cache
        self._cache: list[MemoryRecord] | None = None
        self._cache_mtime: float = 0.0
        # Optional embedding provider for semantic search
        self._embedder = embedding_provider
        # Embedding vector cache: record_id → vector
        self._embedding_cache: dict[str, list[float]] = {}
        # Migrate legacy directory layout if present
        self._migrate_legacy(path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def add(self, record: MemoryRecord) -> MemoryRecord:
        record.touch()
        records = self._load_all()
        records.append(record)
        self._save_all(records)
        return record

    async def get(self, record_id: str) -> MemoryRecord | None:
        for record in self._load_all():
            if record.id == record_id:
                return record
        return None

    async def list(
        self,
        scope: MemoryScope | None = None,
        kind: MemoryKind | None = None,
    ) -> list[MemoryRecord]:
        return [
            r
            for r in self._load_all()
            if (scope is None or r.scope == scope)
            and (kind is None or r.kind == kind)
        ]

    async def search(
        self,
        query: str,
        scope: MemoryScope | None = None,
        kind: MemoryKind | None = None,
        limit: int = 10,
    ) -> list[MemoryRecord]:
        """Search memory records using hybrid keyword + semantic matching.

        When an embedding provider is configured, uses a combined score::

            combined = (keyword_score + semantic_similarity) × (1 + effective_strength)

        Without embeddings, falls back to keyword-only::

            combined = keyword_hits × (1 + effective_strength)

        Archived memories are excluded.  Words longer than 4 characters
        also match by prefix for morphological variant handling.
        """
        query_words = query.lower().split()
        if not query_words:
            return []
        all_records = self._load_all()
        logger.debug(
            "memory.search",
            query=query,
            total_records=len(all_records),
            semantic=self._embedder is not None,
        )

        # Pre-filter candidates.
        candidates: list[MemoryRecord] = []
        for record in all_records:
            if scope and record.scope != scope:
                continue
            if kind and record.kind != kind:
                continue
            if "archived" in record.tags:
                continue
            candidates.append(record)

        if not candidates:
            return []

        now = datetime.now(UTC)

        # Compute semantic similarities if embedder available.
        semantic_scores: dict[str, float] = {}
        if self._embedder is not None:
            semantic_scores = await self._compute_semantic_scores(query, candidates)

        scored: list[tuple[float, MemoryRecord]] = []
        for record in candidates:
            haystack = f"{record.content}\n{' '.join(record.tags)}".lower()
            keyword_hits = sum(
                1 for w in query_words if self._word_matches(w, haystack)
            )
            keyword_score = keyword_hits / max(len(query_words), 1)
            sem_score = semantic_scores.get(record.id, 0.0)

            # Require at least some relevance signal.
            if keyword_hits == 0 and sem_score < 0.3:
                continue

            eff = record.effective_strength(now)
            combined = (keyword_score + sem_score) * (1.0 + eff)
            scored.append((combined, record))

        scored.sort(key=lambda item: item[0], reverse=True)
        matches = [record for _, record in scored[:limit]]
        logger.debug("memory.search.results", query=query, matched=len(matches))
        return matches

    async def _compute_semantic_scores(
        self,
        query: str,
        candidates: list[MemoryRecord],
    ) -> dict[str, float]:
        """Compute cosine similarity between query and candidate records.

        Uses cached embeddings when available.  Falls back gracefully
        on any embedding error (returns empty scores).
        """
        from taskforce.infrastructure.llm.embedding_service import cosine_similarity

        try:
            query_vec = await self._embedder.embed_text(query)

            # Collect texts that need embedding.
            to_embed: list[tuple[int, MemoryRecord]] = []
            cached_vecs: dict[str, list[float]] = {}
            for i, rec in enumerate(candidates):
                if rec.id in self._embedding_cache:
                    cached_vecs[rec.id] = self._embedding_cache[rec.id]
                else:
                    to_embed.append((i, rec))

            if to_embed:
                texts = [r.content for _, r in to_embed]
                vecs = await self._embedder.embed_batch(texts)
                for (_, rec), vec in zip(to_embed, vecs, strict=True):
                    self._embedding_cache[rec.id] = vec
                    cached_vecs[rec.id] = vec

            scores: dict[str, float] = {}
            for rec in candidates:
                vec = cached_vecs.get(rec.id)
                if vec:
                    scores[rec.id] = max(0.0, cosine_similarity(query_vec, vec))
            return scores

        except Exception as exc:
            logger.warning("memory.semantic_search_failed", error=str(exc))
            return {}

    @staticmethod
    def _word_matches(word: str, haystack: str) -> bool:
        """Check whether *word* occurs in *haystack*.

        For words longer than 4 characters a prefix match (dropping the
        last character) is also accepted.  This handles common inflection
        differences like singular/plural in German without requiring a
        full stemmer.
        """
        if word in haystack:
            return True
        if len(word) > 4:
            prefix = word[: len(word) - 1]
            return prefix in haystack
        return False

    async def update(self, record: MemoryRecord) -> MemoryRecord:
        record.touch()
        records = self._load_all()
        for i, existing in enumerate(records):
            if existing.id == record.id:
                # Invalidate stale embedding if content changed.
                if existing.content != record.content:
                    self._embedding_cache.pop(record.id, None)
                records[i] = record
                self._save_all(records)
                return record
        # Not found → append as new
        records.append(record)
        self._save_all(records)
        return record

    async def delete(self, record_id: str) -> bool:
        records = self._load_all()
        new_records = [r for r in records if r.id != record_id]
        if len(new_records) == len(records):
            return False
        self._embedding_cache.pop(record_id, None)
        self._save_all(new_records)
        return True

    # ------------------------------------------------------------------
    # In-memory cache
    # ------------------------------------------------------------------

    def _load_all(self) -> list[MemoryRecord]:
        """Load all records, using the in-memory cache when possible.

        The cache is invalidated when the file's mtime changes, so
        external modifications (e.g. another process editing the file)
        are picked up automatically.
        """
        if self._cache is not None and not self._cache_stale():
            return list(self._cache)
        return self._load_from_disk()

    def _cache_stale(self) -> bool:
        """Check whether the on-disk file has changed since last load."""
        try:
            mtime = os.path.getmtime(self._file)
            return mtime != self._cache_mtime
        except OSError:
            # File might not exist.
            return self._cache_mtime != 0.0

    def _load_from_disk(self) -> list[MemoryRecord]:
        """Parse the YAML file and populate the cache."""
        if not self._file.exists():
            self._cache = []
            self._cache_mtime = 0.0
            return []
        text = self._file.read_text(encoding="utf-8").strip()
        if not text:
            self._cache = []
            self._cache_mtime = 0.0
            return []
        records: list[MemoryRecord] = []
        for doc in yaml.safe_load_all(text):
            if doc is None:
                continue
            try:
                records.append(self._dict_to_record(doc))
            except (KeyError, ValueError):
                continue  # skip malformed entries
        self._cache = records
        try:
            self._cache_mtime = os.path.getmtime(self._file)
        except OSError:
            self._cache_mtime = 0.0
        return list(records)

    def _save_all(self, records: list[MemoryRecord]) -> None:
        """Write all records to disk and update the cache.

        Uses atomic write via a temp file with retry to handle Windows
        file-locking issues (``OSError: [Errno 22]``) that occur when
        concurrent reads/writes overlap on the same file.
        """
        import time

        docs = [self._record_to_dict(r) for r in records]
        text = yaml.dump_all(docs, sort_keys=False, allow_unicode=True)
        data = text.encode("utf-8")
        target = self._file.resolve()
        tmp = target.with_suffix(".md.tmp")

        last_error: OSError | None = None
        for attempt in range(3):
            try:
                tmp.write_bytes(data)
                if target.exists():
                    os.replace(str(tmp), str(target))
                else:
                    tmp.rename(target)
                last_error = None
                break
            except OSError as exc:
                last_error = exc
                logger.debug(
                    "memory.save_retry",
                    attempt=attempt + 1,
                    error=str(exc),
                )
                time.sleep(0.1 * (attempt + 1))

        if last_error is not None:
            logger.error("memory.save_failed", error=str(last_error))

        # Update cache to match what we just wrote.
        self._cache = list(records)
        try:
            self._cache_mtime = os.path.getmtime(self._file)
        except OSError:
            self._cache_mtime = 0.0

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def _record_to_dict(self, record: MemoryRecord) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": record.id,
            "scope": record.scope.value,
            "kind": record.kind.value,
            "content": record.content,
            "tags": record.tags,
            "metadata": record.metadata,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            # Human-like memory properties
            "strength": round(record.strength, 4),
            "access_count": record.access_count,
            "emotional_valence": record.emotional_valence.value,
            "importance": round(record.importance, 4),
            "decay_rate": round(record.decay_rate, 6),
        }
        if record.last_accessed:
            result["last_accessed"] = record.last_accessed.isoformat()
        if record.associations:
            result["associations"] = record.associations
        return result

    def _dict_to_record(self, data: dict[str, Any]) -> MemoryRecord:
        last_accessed_raw = data.get("last_accessed")
        valence_raw = data.get("emotional_valence")
        return MemoryRecord(
            id=data["id"],
            scope=MemoryScope(data["scope"]),
            kind=MemoryKind(data["kind"]),
            content=data["content"],
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
            created_at=self._parse_datetime(data["created_at"]),
            updated_at=self._parse_datetime(data["updated_at"]),
            # Human-like memory properties (backward-compatible defaults)
            strength=data.get("strength", -1.0),
            access_count=data.get("access_count", 0),
            last_accessed=(
                self._parse_datetime(last_accessed_raw) if last_accessed_raw else None
            ),
            emotional_valence=(
                EmotionalValence(valence_raw) if valence_raw else EmotionalValence.NEUTRAL
            ),
            importance=data.get("importance", 0.5),
            associations=data.get("associations", []),
            decay_rate=data.get("decay_rate", -1.0),
        )

    def _parse_datetime(self, value: str) -> datetime:
        return datetime.fromisoformat(value)

    # ------------------------------------------------------------------
    # Legacy migration
    # ------------------------------------------------------------------

    def _migrate_legacy(self, original_path: Path) -> None:
        """Auto-migrate from old directory-based layout to single file.

        Checks for the old ``scope/kind/uuid.md`` directory layout and
        consolidates all records into the new single file.
        """
        if original_path.suffix == ".md":
            legacy_dir = original_path.with_suffix("")
        elif original_path.is_dir():
            legacy_dir = original_path
        else:
            return
        if not legacy_dir.is_dir():
            return
        legacy_files = [
            p
            for p in legacy_dir.rglob("*.md")
            if p != self._file and p.parent != legacy_dir
        ]
        if not legacy_files:
            return
        if self._file.exists() and self._file.stat().st_size > 0:
            return
        records: list[MemoryRecord] = []
        for path in legacy_files:
            try:
                record = self._read_legacy_record(path)
                records.append(record)
            except Exception:
                continue
        if records:
            self._save_all(records)

    def _read_legacy_record(self, path: Path) -> MemoryRecord:
        """Read a record from the old per-file format (YAML front matter)."""
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            raise ValueError("Missing front matter in legacy memory record.")
        _, rest = text.split("---", 1)
        header, content = rest.split("---", 1)
        data = yaml.safe_load(header.strip()) or {}
        return MemoryRecord(
            id=data["id"],
            scope=MemoryScope(data["scope"]),
            kind=MemoryKind(data["kind"]),
            content=content.strip(),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
            created_at=self._parse_datetime(data["created_at"]),
            updated_at=self._parse_datetime(data["updated_at"]),
        )
