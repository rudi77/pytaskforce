"""File-backed memory store using a single Markdown file."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from taskforce.core.domain.memory import MemoryKind, MemoryRecord, MemoryScope
from taskforce.core.interfaces.memory_store import MemoryStoreProtocol


class FileMemoryStore(MemoryStoreProtocol):
    """Persist memory records in a single Markdown file (``memory.md``).

    All records are stored as YAML documents separated by ``---`` inside a
    single file.  This replaces the previous multi-file/directory layout and
    keeps things simple and human-readable.

    Args:
        base_dir: Path that is either a ``.md`` file or a directory.
            * If it ends with ``.md`` → used as-is (e.g. ``work_dir/memory.md``).
            * Otherwise treated as a directory and ``memory.md`` is appended.
    """

    def __init__(self, base_dir: str | Path) -> None:
        path = Path(base_dir)
        if path.suffix == ".md":
            self._file = path
        else:
            self._file = path / "memory.md"
        self._file.parent.mkdir(parents=True, exist_ok=True)
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
        query_lower = query.lower()
        matches: list[MemoryRecord] = []
        for record in self._load_all():
            if scope and record.scope != scope:
                continue
            if kind and record.kind != kind:
                continue
            haystack = f"{record.content}\n{' '.join(record.tags)}".lower()
            if query_lower in haystack:
                matches.append(record)
            if len(matches) >= limit:
                break
        return matches

    async def update(self, record: MemoryRecord) -> MemoryRecord:
        record.touch()
        records = self._load_all()
        for i, existing in enumerate(records):
            if existing.id == record.id:
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
        self._save_all(new_records)
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_all(self) -> list[MemoryRecord]:
        """Load all records from the single memory file."""
        if not self._file.exists():
            return []
        text = self._file.read_text(encoding="utf-8").strip()
        if not text:
            return []
        records: list[MemoryRecord] = []
        for doc in yaml.safe_load_all(text):
            if doc is None:
                continue
            try:
                records.append(self._dict_to_record(doc))
            except (KeyError, ValueError):
                continue  # skip malformed entries
        return records

    def _save_all(self, records: list[MemoryRecord]) -> None:
        """Write all records to the single memory file."""
        docs = [self._record_to_dict(r) for r in records]
        text = yaml.dump_all(docs, sort_keys=False, allow_unicode=True)
        self._file.write_text(text, encoding="utf-8")

    def _record_to_dict(self, record: MemoryRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "scope": record.scope.value,
            "kind": record.kind.value,
            "content": record.content,
            "tags": record.tags,
            "metadata": record.metadata,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }

    def _dict_to_record(self, data: dict[str, Any]) -> MemoryRecord:
        return MemoryRecord(
            id=data["id"],
            scope=MemoryScope(data["scope"]),
            kind=MemoryKind(data["kind"]),
            content=data["content"],
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
            created_at=self._parse_datetime(data["created_at"]),
            updated_at=self._parse_datetime(data["updated_at"]),
        )

    def _parse_datetime(self, value: str) -> datetime:
        return datetime.fromisoformat(value)

    def _migrate_legacy(self, original_path: Path) -> None:
        """Auto-migrate from old directory-based layout to single file.

        Checks for the old ``scope/kind/uuid.md`` directory layout and
        consolidates all records into the new single file.
        """
        # Determine legacy directory: if original_path is a .md file,
        # check for a directory with the same stem (e.g. memory/ next to memory.md)
        if original_path.suffix == ".md":
            legacy_dir = original_path.with_suffix("")
        elif original_path.is_dir():
            legacy_dir = original_path
        else:
            return
        if not legacy_dir.is_dir():
            return
        # Only migrate if there are .md files deeper inside
        legacy_files = [
            p
            for p in legacy_dir.rglob("*.md")
            if p != self._file and p.parent != legacy_dir
        ]
        if not legacy_files:
            return
        # If the new file already has content, skip migration
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
