"""Conversation store adapters implementing ConversationStoreProtocol.

Provides file-based and in-memory implementations for session mapping
and conversation history persistence. Channel-agnostic by design.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import aiofiles
import structlog


@dataclass(frozen=True)
class ConversationRecord:
    """Persisted conversation record."""

    channel: str
    conversation_id: str
    session_id: str
    history: list[dict[str, Any]]
    updated_at: str


class FileConversationStore:
    """File-based conversation store for session mapping and history.

    Stores one JSON file per (channel, conversation_id) pair under
    ``{work_dir}/conversations/{channel}/{conversation_id}.json``.
    Uses per-file async locks and atomic temp-file writes.
    """

    def __init__(
        self,
        work_dir: str = ".taskforce",
        time_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._base_dir = Path(work_dir) / "conversations"
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, asyncio.Lock] = {}
        self._logger = structlog.get_logger()
        self._time_provider = time_provider or datetime.now

    async def get_session_id(self, channel: str, conversation_id: str) -> str | None:
        """Return the mapped session ID for a channel conversation."""
        record = await self._load_record(channel, conversation_id)
        return record.session_id if record else None

    async def set_session_id(self, channel: str, conversation_id: str, session_id: str) -> None:
        """Persist the session ID mapping for a channel conversation."""
        record = await self._load_record(channel, conversation_id)
        history = record.history if record else []
        await self._save_record(channel, conversation_id, session_id, history)

    async def load_history(self, channel: str, conversation_id: str) -> list[dict[str, Any]]:
        """Load stored conversation history."""
        record = await self._load_record(channel, conversation_id)
        return record.history if record else []

    async def save_history(
        self, channel: str, conversation_id: str, history: list[dict[str, Any]]
    ) -> None:
        """Persist conversation history."""
        session_id = await self.get_session_id(channel, conversation_id)
        if session_id is None:
            raise ValueError("session_id must be set before saving history")
        await self._save_record(channel, conversation_id, session_id, history)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def _record_path(self, channel: str, conversation_id: str) -> Path:
        safe_channel = channel.replace("/", "_")
        safe_conversation = conversation_id.replace("/", "_")
        channel_dir = self._base_dir / safe_channel
        channel_dir.mkdir(parents=True, exist_ok=True)
        return channel_dir / f"{safe_conversation}.json"

    def _now_isoformat(self) -> str:
        return self._time_provider().isoformat()

    async def _load_record(self, channel: str, conversation_id: str) -> ConversationRecord | None:
        path = self._record_path(channel, conversation_id)
        if not path.exists():
            return None
        async with self._get_lock(str(path)):
            try:
                async with aiofiles.open(path, encoding="utf-8") as handle:
                    payload = json.loads(await handle.read())
            except (OSError, json.JSONDecodeError) as exc:
                self._logger.error(
                    "conversation_store.load_failed",
                    channel=channel,
                    conversation_id=conversation_id,
                    error=str(exc),
                )
                return None
        return ConversationRecord(
            channel=payload.get("channel", payload.get("provider", "")),
            conversation_id=payload["conversation_id"],
            session_id=payload["session_id"],
            history=payload.get("history", []),
            updated_at=payload.get("updated_at", ""),
        )

    async def _save_record(
        self,
        channel: str,
        conversation_id: str,
        session_id: str,
        history: list[dict[str, Any]],
    ) -> None:
        path = self._record_path(channel, conversation_id)
        payload = {
            "channel": channel,
            "conversation_id": conversation_id,
            "session_id": session_id,
            "history": history,
            "updated_at": self._now_isoformat(),
        }
        temp_path = path.with_suffix(".json.tmp")
        async with self._get_lock(str(path)):
            try:
                async with aiofiles.open(temp_path, "w", encoding="utf-8") as handle:
                    await handle.write(json.dumps(payload, indent=2, ensure_ascii=False))
                if path.exists():
                    path.unlink()
                temp_path.rename(path)
            except OSError as exc:
                self._logger.error(
                    "conversation_store.save_failed",
                    channel=channel,
                    conversation_id=conversation_id,
                    error=str(exc),
                )


class InMemoryConversationStore:
    """In-memory conversation store for tests."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], ConversationRecord] = {}

    async def get_session_id(self, channel: str, conversation_id: str) -> str | None:
        record = self._records.get((channel, conversation_id))
        return record.session_id if record else None

    async def set_session_id(self, channel: str, conversation_id: str, session_id: str) -> None:
        record = self._records.get((channel, conversation_id))
        history = record.history if record else []
        self._records[(channel, conversation_id)] = ConversationRecord(
            channel=channel,
            conversation_id=conversation_id,
            session_id=session_id,
            history=history,
            updated_at=datetime.now().isoformat(),
        )

    async def load_history(self, channel: str, conversation_id: str) -> list[dict[str, Any]]:
        record = self._records.get((channel, conversation_id))
        return list(record.history) if record else []

    async def save_history(
        self, channel: str, conversation_id: str, history: list[dict[str, Any]]
    ) -> None:
        session_id = await self.get_session_id(channel, conversation_id)
        if session_id is None:
            raise ValueError("session_id must be set before saving history")
        self._records[(channel, conversation_id)] = ConversationRecord(
            channel=channel,
            conversation_id=conversation_id,
            session_id=session_id,
            history=list(history),
            updated_at=datetime.now().isoformat(),
        )
