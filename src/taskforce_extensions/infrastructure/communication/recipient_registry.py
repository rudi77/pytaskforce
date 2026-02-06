"""Recipient registry adapters implementing RecipientRegistryProtocol.

Stores channel-specific recipient references so agents can send
proactive push notifications to users they have previously interacted with.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import aiofiles
import structlog


class FileRecipientRegistry:
    """File-based recipient registry.

    Stores one JSON file per (channel, user_id) pair under
    ``{work_dir}/recipients/{channel}/{user_id}.json``.
    """

    def __init__(self, work_dir: str = ".taskforce") -> None:
        self._base_dir = Path(work_dir) / "recipients"
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, asyncio.Lock] = {}
        self._logger = structlog.get_logger()

    async def register(self, *, channel: str, user_id: str, reference: dict[str, Any]) -> None:
        """Store or update a recipient reference."""
        path = self._record_path(channel, user_id)
        payload = {
            "channel": channel,
            "user_id": user_id,
            "reference": reference,
            "registered_at": datetime.now().isoformat(),
        }
        temp_path = path.with_suffix(".json.tmp")
        async with self._get_lock(str(path)):
            try:
                async with aiofiles.open(temp_path, "w", encoding="utf-8") as handle:
                    await handle.write(json.dumps(payload, indent=2, ensure_ascii=False))
                temp_path.replace(path)
            except OSError as exc:
                self._logger.error(
                    "recipient_registry.register_failed",
                    channel=channel,
                    user_id=user_id,
                    error=str(exc),
                )

    async def resolve(self, *, channel: str, user_id: str) -> dict[str, Any] | None:
        """Look up a stored recipient reference."""
        path = self._record_path(channel, user_id)
        if not path.exists():
            return None
        async with self._get_lock(str(path)):
            try:
                async with aiofiles.open(path, encoding="utf-8") as handle:
                    payload = json.loads(await handle.read())
                return payload.get("reference")
            except (OSError, json.JSONDecodeError) as exc:
                self._logger.error(
                    "recipient_registry.resolve_failed",
                    channel=channel,
                    user_id=user_id,
                    error=str(exc),
                )
                return None

    async def list_recipients(self, channel: str) -> list[str]:
        """List all registered user IDs for a channel."""
        channel_dir = self._base_dir / channel.replace("/", "_")
        if not channel_dir.exists():
            return []
        return [p.stem for p in sorted(channel_dir.glob("*.json"))]

    async def remove(self, *, channel: str, user_id: str) -> bool:
        """Remove a recipient. Returns True if it existed."""
        path = self._record_path(channel, user_id)
        async with self._get_lock(str(path)):
            if path.exists():
                path.unlink()
                return True
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def _record_path(self, channel: str, user_id: str) -> Path:
        safe_channel = channel.replace("/", "_")
        safe_user = user_id.replace("/", "_")
        channel_dir = self._base_dir / safe_channel
        channel_dir.mkdir(parents=True, exist_ok=True)
        return channel_dir / f"{safe_user}.json"


class InMemoryRecipientRegistry:
    """In-memory recipient registry for tests."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], dict[str, Any]] = {}

    async def register(self, *, channel: str, user_id: str, reference: dict[str, Any]) -> None:
        self._records[(channel, user_id)] = reference

    async def resolve(self, *, channel: str, user_id: str) -> dict[str, Any] | None:
        return self._records.get((channel, user_id))

    async def list_recipients(self, channel: str) -> list[str]:
        return [uid for (ch, uid) in self._records if ch == channel]

    async def remove(self, *, channel: str, user_id: str) -> bool:
        key = (channel, user_id)
        if key in self._records:
            del self._records[key]
            return True
        return False
