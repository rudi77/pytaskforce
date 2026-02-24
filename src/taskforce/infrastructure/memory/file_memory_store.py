"""File-backed memory store using Markdown records."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import yaml

from taskforce.core.domain.memory import MemoryKind, MemoryRecord, MemoryScope
from taskforce.core.interfaces.memory_store import MemoryStoreProtocol


class FileMemoryStore(MemoryStoreProtocol):
    """Persist memory records to Markdown files with YAML front matter."""

    def __init__(self, base_dir: str | Path) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    async def add(self, record: MemoryRecord) -> MemoryRecord:
        record.touch()
        self._write_record(record)
        return record

    async def get(self, record_id: str) -> MemoryRecord | None:
        for path in self._base_dir.rglob(f"{record_id}.md"):
            return self._read_record(path)
        return None

    async def list(  # type: ignore[valid-type]
        self,
        scope: MemoryScope | None = None,
        kind: MemoryKind | None = None,
    ) -> list[MemoryRecord]:
        paths: list[Path] = self._iter_paths(scope=scope, kind=kind)
        return [self._read_record(path) for path in paths]

    async def search(
        self,
        query: str,
        scope: MemoryScope | None = None,
        kind: MemoryKind | None = None,
        limit: int = 10,
    ) -> list[MemoryRecord]:
        query_lower = query.lower()
        matches: list[MemoryRecord] = []
        for path in self._iter_paths(scope=scope, kind=kind):  # type: ignore[attr-defined]
            record = self._read_record(path)
            haystack = f"{record.content}\n{' '.join(record.tags)}".lower()
            if query_lower in haystack:
                matches.append(record)
            if len(matches) >= limit:
                break
        return matches

    async def update(self, record: MemoryRecord) -> MemoryRecord:
        record.touch()
        self._write_record(record)
        return record

    async def delete(self, record_id: str) -> bool:
        for path in self._base_dir.rglob(f"{record_id}.md"):
            path.unlink()
            return True
        return False

    def _iter_paths(  # type: ignore[valid-type]
        self,
        scope: MemoryScope | None,
        kind: MemoryKind | None,
    ) -> list[Path]:
        base = self._base_dir
        if scope:
            base = base / scope.value
        if kind:
            base = base / kind.value
        if not base.exists():
            return []
        return sorted(base.glob("**/*.md"))

    def _write_record(self, record: MemoryRecord) -> None:
        path = self._record_path(record)
        path.parent.mkdir(parents=True, exist_ok=True)
        front_matter = self._serialize_front_matter(record)
        path.write_text(f"---\n{front_matter}---\n\n{record.content}\n", encoding="utf-8")

    def _read_record(self, path: Path) -> MemoryRecord:
        text = path.read_text(encoding="utf-8")
        header, content = self._split_front_matter(text)
        data = yaml.safe_load(header) or {}
        return MemoryRecord(
            id=data["id"],
            scope=MemoryScope(data["scope"]),
            kind=MemoryKind(data["kind"]),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
            created_at=self._parse_datetime(data["created_at"]),
            updated_at=self._parse_datetime(data["updated_at"]),
            content=content.strip(),
        )

    def _record_path(self, record: MemoryRecord) -> Path:
        return (
            self._base_dir
            / record.scope.value
            / record.kind.value
            / f"{record.id}.md"
        )

    def _serialize_front_matter(self, record: MemoryRecord) -> str:
        payload = asdict(record)
        payload["scope"] = record.scope.value
        payload["kind"] = record.kind.value
        payload["created_at"] = record.created_at.isoformat()
        payload["updated_at"] = record.updated_at.isoformat()
        return yaml.safe_dump(payload, sort_keys=False)

    def _split_front_matter(self, text: str) -> tuple[str, str]:
        if not text.startswith("---"):
            raise ValueError("Missing front matter in memory record.")
        _, rest = text.split("---", 1)
        header, content = rest.split("---", 1)
        return header.strip(), content

    def _parse_datetime(self, value: str) -> datetime:
        return datetime.fromisoformat(value)
