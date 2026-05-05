"""Checkpoint storage adapters for agent recovery."""

from __future__ import annotations

import json
from pathlib import Path

import aiofiles
import structlog

from taskforce.core.domain.runtime import CheckpointRecord
from taskforce.core.interfaces.runtime import CheckpointStoreProtocol


class FileCheckpointStore(CheckpointStoreProtocol):
    """File-based checkpoint store."""

    def __init__(self, work_dir: str | Path = ".taskforce") -> None:
        self._work_dir = Path(work_dir)
        self._base_dir = self._work_dir / "runtime" / "checkpoints"
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._logger = structlog.get_logger().bind(component="FileCheckpointStore")

    async def save(self, record: CheckpointRecord) -> None:
        session_dir = self._base_dir / record.session_id
        path = session_dir / f"{record.checkpoint_id}.json"
        tmp_path = path.with_suffix(".tmp")
        payload = json.dumps(record.to_dict(), ensure_ascii=False, indent=2)

        # The session/parent directory may have been wiped between checkpoints
        # (e.g. by a manual cleanup or a session rotation). We recreate the
        # tree on every save and retry the atomic replace once if the directory
        # vanishes between the temp-write and the replace — this is what
        # caused the "checkpoint save failed" loop in long-running sub-agents.
        for attempt in range(2):
            try:
                session_dir.mkdir(parents=True, exist_ok=True)
                async with aiofiles.open(tmp_path, "w", encoding="utf-8") as handle:
                    await handle.write(payload)
                tmp_path.replace(path)
                break
            except FileNotFoundError as exc:
                if attempt == 0:
                    self._logger.warning(
                        "checkpoint_save_retry",
                        session_id=record.session_id,
                        error=str(exc),
                    )
                    # Best-effort cleanup of the dangling temp file before retrying.
                    try:
                        tmp_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                    continue
                self._logger.error(
                    "checkpoint_save_failed",
                    session_id=record.session_id,
                    error=str(exc),
                )
                raise
        self._logger.debug("checkpoint_saved", session_id=record.session_id)

    async def latest(self, session_id: str) -> CheckpointRecord | None:
        records = await self.list(session_id)
        if not records:
            return None
        return max(records, key=lambda item: item.timestamp)

    async def list(self, session_id: str) -> list[CheckpointRecord]:
        session_dir = self._base_dir / session_id
        if not session_dir.exists():
            return []
        records: list[CheckpointRecord] = []
        for path in session_dir.glob("*.json"):
            async with aiofiles.open(path, "r", encoding="utf-8") as handle:
                payload = json.loads(await handle.read())
            records.append(CheckpointRecord.from_dict(payload))
        return records


class InMemoryCheckpointStore(CheckpointStoreProtocol):
    """In-memory checkpoint store for testing."""

    def __init__(self) -> None:
        self._records: dict[str, list[CheckpointRecord]] = {}

    async def save(self, record: CheckpointRecord) -> None:
        self._records.setdefault(record.session_id, []).append(record)

    async def latest(self, session_id: str) -> CheckpointRecord | None:
        records = self._records.get(session_id, [])
        if not records:
            return None
        return max(records, key=lambda item: item.timestamp)

    async def list(self, session_id: str) -> list[CheckpointRecord]:
        return list(self._records.get(session_id, []))
