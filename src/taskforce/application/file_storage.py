"""
File Storage Service
====================

Persistent storage for files uploaded by the management UI (chat
attachments, agent inputs). Uses a sharded directory layout on disk
plus a SQLite index for metadata queries.

Layout::

    .taskforce/uploads/{shard}/{file_id}     # raw blob
    .taskforce/uploads.db                     # SQLite index

* ``file_id`` is a 32-character hex UUID (no dashes).
* The first two characters of ``file_id`` form the shard directory so a
  flat upload directory never grows beyond 256 entries.
* MIME type is detected from the filename (``mimetypes``) — good enough
  for Phase 4. Heavyweight ``python-magic`` may be added later.

The service is intentionally process-local: callers acquire a fresh
SQLite connection per operation so it works under FastAPI's threadpool
without further locking.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Iterator

import structlog

logger = structlog.get_logger(__name__)

DEFAULT_MAX_BYTES = 25 * 1024 * 1024  # 25 MB


def _default_root() -> Path:
    override = os.environ.get("TASKFORCE_UPLOADS_DIR")
    if override:
        return Path(override).expanduser()
    return Path(".taskforce") / "uploads"


def _max_upload_bytes() -> int:
    raw = os.environ.get("TASKFORCE_UPLOAD_MAX_MB")
    if not raw:
        return DEFAULT_MAX_BYTES
    try:
        return max(1, int(raw)) * 1024 * 1024
    except ValueError:
        return DEFAULT_MAX_BYTES


@dataclass(frozen=True)
class FileMetadata:
    """Public metadata record for an uploaded file."""

    file_id: str
    name: str
    mime: str
    size: int
    sha256: str
    created_at: str  # ISO8601 UTC


class FileStorageError(RuntimeError):
    """Base error for file storage operations."""


class FileNotFound(FileStorageError):
    pass


class FileTooLarge(FileStorageError):
    pass


class FileStorage:
    """File storage backed by a sharded filesystem + SQLite index."""

    def __init__(
        self,
        root: Path | None = None,
        max_bytes: int | None = None,
    ) -> None:
        self._root = (root or _default_root()).resolve()
        self._db_path = self._root.with_suffix(".db") if self._root.suffix else self._root.parent / "uploads.db"
        # Use {root}/index.db so reset_root_for_tests works cleanly.
        self._db_path = self._root / "index.db"
        self._max_bytes = max_bytes if max_bytes is not None else _max_upload_bytes()
        self._root.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS files (
                    file_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    mime TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def _shard_dir(self, file_id: str) -> Path:
        return self._root / file_id[:2]

    def _blob_path(self, file_id: str) -> Path:
        return self._shard_dir(file_id) / file_id

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    @property
    def root(self) -> Path:
        return self._root

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, name: str, stream: IO[bytes], declared_mime: str | None = None) -> FileMetadata:
        """Persist a stream and return its metadata.

        Streams are read in chunks so large uploads do not load fully
        into memory. The size budget is enforced incrementally; once
        exceeded the partial blob is removed and ``FileTooLarge`` is
        raised.
        """
        if not name:
            raise ValueError("file name is required")
        file_id = uuid.uuid4().hex
        shard = self._shard_dir(file_id)
        shard.mkdir(parents=True, exist_ok=True)
        target = self._blob_path(file_id)

        sha = hashlib.sha256()
        size = 0
        try:
            with target.open("wb") as out:
                while True:
                    chunk = stream.read(1 << 16)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > self._max_bytes:
                        raise FileTooLarge(
                            f"upload exceeds limit of {self._max_bytes} bytes"
                        )
                    sha.update(chunk)
                    out.write(chunk)
        except FileTooLarge:
            target.unlink(missing_ok=True)
            raise
        except Exception:
            target.unlink(missing_ok=True)
            raise

        mime = declared_mime or mimetypes.guess_type(name)[0] or "application/octet-stream"
        created_at = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO files (file_id, name, mime, size, sha256, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (file_id, name, mime, size, sha.hexdigest(), created_at),
            )

        meta = FileMetadata(
            file_id=file_id,
            name=name,
            mime=mime,
            size=size,
            sha256=sha.hexdigest(),
            created_at=created_at,
        )
        logger.info("file_uploaded", file_id=file_id, size=size, mime=mime)
        return meta

    def get_metadata(self, file_id: str) -> FileMetadata:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM files WHERE file_id = ?", (file_id,)
            ).fetchone()
        if row is None:
            raise FileNotFound(f"file '{file_id}' not found")
        return _row_to_metadata(row)

    def open_stream(self, file_id: str) -> tuple[IO[bytes], FileMetadata]:
        meta = self.get_metadata(file_id)
        path = self._blob_path(file_id)
        if not path.is_file():
            raise FileNotFound(f"file '{file_id}' missing on disk")
        return path.open("rb"), meta

    def delete(self, file_id: str) -> None:
        meta = self.get_metadata(file_id)
        path = self._blob_path(file_id)
        if path.exists():
            path.unlink()
        # Best-effort: remove empty shard dir so the tree stays tidy.
        shard = self._shard_dir(file_id)
        try:
            shard.rmdir()
        except OSError:
            pass
        with self._connect() as conn:
            conn.execute("DELETE FROM files WHERE file_id = ?", (file_id,))
        logger.info("file_deleted", file_id=file_id)
        # ``meta`` is unused after delete; touch via replace to avoid linter
        del meta

    def attachments_for_prompt(self, file_ids: list[str]) -> list[dict]:
        """Build a serialisable list of attachment metadata for prompt injection."""
        if not file_ids:
            return []
        result: list[dict] = []
        with self._connect() as conn:
            placeholders = ",".join("?" * len(file_ids))
            rows = conn.execute(
                f"SELECT * FROM files WHERE file_id IN ({placeholders})",
                file_ids,
            ).fetchall()
        for row in rows:
            meta = _row_to_metadata(row)
            result.append(
                {
                    "file_id": meta.file_id,
                    "name": meta.name,
                    "mime": meta.mime,
                    "size": meta.size,
                    "path": str(self._blob_path(meta.file_id)),
                }
            )
        return result


def _row_to_metadata(row: sqlite3.Row) -> FileMetadata:
    return FileMetadata(
        file_id=row["file_id"],
        name=row["name"],
        mime=row["mime"],
        size=row["size"],
        sha256=row["sha256"],
        created_at=row["created_at"],
    )


# ------------------------------------------------------------------
# Singleton accessor
# ------------------------------------------------------------------

_storage: FileStorage | None = None


def get_file_storage() -> FileStorage:
    global _storage
    if _storage is None:
        _storage = FileStorage()
    return _storage


def reset_file_storage() -> None:
    """Reset the cached storage (test helper)."""
    global _storage
    _storage = None


def reset_root_for_tests(root: Path) -> FileStorage:
    """Replace the global storage with one rooted at ``root`` (test helper)."""
    global _storage
    _storage = FileStorage(root=root)
    return _storage


__all__ = [
    "FileMetadata",
    "FileNotFound",
    "FileStorage",
    "FileStorageError",
    "FileTooLarge",
    "get_file_storage",
    "reset_file_storage",
    "reset_root_for_tests",
]
