"""Heartbeat storage adapters for long-running agent sessions."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import aiofiles
import structlog

from taskforce.core.domain.runtime import HeartbeatRecord
from taskforce.core.interfaces.runtime import HeartbeatStoreProtocol


class FileHeartbeatStore(HeartbeatStoreProtocol):
    """File-based heartbeat store."""

    def __init__(
        self,
        work_dir: str | Path = ".taskforce",
    ) -> None:
        self._work_dir = Path(work_dir)
        self._base_dir = self._work_dir / "runtime" / "heartbeats"
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, asyncio.Lock] = {}
        self._logger = structlog.get_logger().bind(component="FileHeartbeatStore")

    async def record(self, record: HeartbeatRecord) -> None:
        path = self._base_dir / f"{record.session_id}.json"
        lock = self._locks.setdefault(record.session_id, asyncio.Lock())
        async with lock:
            payload = json.dumps(record.to_dict(), ensure_ascii=False, indent=2)
            tmp_path = path.with_suffix(".tmp")
            async with aiofiles.open(tmp_path, "w", encoding="utf-8") as handle:
                await handle.write(payload)
            tmp_path.replace(path)
        self._logger.debug("heartbeat_recorded", session_id=record.session_id)

    async def load(self, session_id: str) -> HeartbeatRecord | None:
        path = self._base_dir / f"{session_id}.json"
        if not path.exists():
            return None
        async with aiofiles.open(path, "r", encoding="utf-8") as handle:
            payload = json.loads(await handle.read())
        return HeartbeatRecord.from_dict(payload)

    async def list_records(self) -> list[HeartbeatRecord]:
        records: list[HeartbeatRecord] = []
        for path in self._base_dir.glob("*.json"):
            async with aiofiles.open(path, "r", encoding="utf-8") as handle:
                payload = json.loads(await handle.read())
            records.append(HeartbeatRecord.from_dict(payload))
        return records


class InMemoryHeartbeatStore(HeartbeatStoreProtocol):
    """In-memory heartbeat store for testing."""

    def __init__(self) -> None:
        self._records: dict[str, HeartbeatRecord] = {}

    async def record(self, record: HeartbeatRecord) -> None:
        self._records[record.session_id] = record

    async def load(self, session_id: str) -> HeartbeatRecord | None:
        return self._records.get(session_id)

    async def list_records(self) -> list[HeartbeatRecord]:
        return list(self._records.values())
