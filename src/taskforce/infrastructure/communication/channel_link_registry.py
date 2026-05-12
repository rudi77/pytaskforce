"""Channel-link registry adapters implementing ``ChannelLinkRegistryProtocol``.

Backs the framework's ``/link <code>`` pairing flow (issue #162): a
web-UI / REST client mints a short-lived code bound to the
authenticated ``(tenant, user)``; the user redeems it from the channel
side (``/link 123456`` in Telegram) and from that point inbound
messages from the same sender resolve to the linked tenant/user.

The framework ships two implementations:

- :class:`FileChannelLinkRegistry`: one JSON file per channel under
  ``<work_dir>/channel_links/<channel>.json``. Atomic writes,
  per-channel ``asyncio.Lock`` serialisation, lazy garbage collection
  of expired pending codes.
- :class:`InMemoryChannelLinkRegistry`: dict-backed implementation for
  tests.

Enterprise plugins replace this with a postgres-backed registry via
:func:`taskforce.application.infrastructure_overrides.set_channel_link_registry_override`.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import aiofiles
import structlog

from taskforce.core.domain.gateway import ChannelLink, ChannelLinkCode

_CODE_DIGITS = 6
_CODE_GENERATION_RETRIES = 8
_DEFAULT_TTL_SECONDS = 600


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _generate_code() -> str:
    return f"{secrets.randbelow(10**_CODE_DIGITS):0{_CODE_DIGITS}d}"


class FileChannelLinkRegistry:
    """File-based channel-link registry.

    One JSON document per channel under
    ``<work_dir>/channel_links/<channel>.json``. The on-disk schema is::

        {
          "pending": {
            "<code>": {"tenant_id": "...", "user_id": "...",
                       "expires_at": "<iso8601 utc>"}
          },
          "links": {
            "<sender_id>": {"tenant_id": "...", "user_id": "...",
                            "linked_at": "<iso8601 utc>"}
          }
        }

    Expired pending codes are pruned lazily on every mutation; reads
    do not rewrite the file. The default code length is six digits
    and the default TTL is 600 seconds (10 minutes).
    """

    def __init__(self, work_dir: str = ".taskforce") -> None:
        self._base_dir = Path(work_dir) / "channel_links"
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, asyncio.Lock] = {}
        self._logger = structlog.get_logger()

    async def create_pending_code(
        self,
        *,
        channel: str,
        tenant_id: str,
        user_id: str,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> ChannelLinkCode:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        async with self._lock_for(channel):
            data = await self._read(channel)
            self._prune_expired(data)
            existing_codes = set(data.get("pending", {}).keys())
            code = self._mint_code(existing_codes)
            expires_at = _now_utc() + timedelta(seconds=ttl_seconds)
            data.setdefault("pending", {})[code] = {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "expires_at": expires_at.isoformat(),
            }
            await self._write(channel, data)
            self._logger.info(
                "channel_link_registry.code_created",
                channel=channel,
                tenant_id=tenant_id,
                user_id=user_id,
                ttl_seconds=ttl_seconds,
            )
            return ChannelLinkCode(
                code=code,
                channel=channel,
                tenant_id=tenant_id,
                user_id=user_id,
                expires_at=expires_at,
            )

    async def consume_code(
        self,
        *,
        channel: str,
        code: str,
        sender_id: str,
    ) -> ChannelLink | None:
        async with self._lock_for(channel):
            data = await self._read(channel)
            self._prune_expired(data)
            pending = data.get("pending", {})
            record = pending.pop(code, None)
            if record is None:
                await self._write(channel, data)
                self._logger.info(
                    "channel_link_registry.consume_failed",
                    channel=channel,
                    reason="unknown_or_expired",
                )
                return None
            linked_at = _now_utc()
            data.setdefault("links", {})[sender_id] = {
                "tenant_id": record["tenant_id"],
                "user_id": record["user_id"],
                "linked_at": linked_at.isoformat(),
            }
            await self._write(channel, data)
            self._logger.info(
                "channel_link_registry.link_created",
                channel=channel,
                sender_id=sender_id,
                tenant_id=record["tenant_id"],
                user_id=record["user_id"],
            )
            return ChannelLink(
                channel=channel,
                sender_id=sender_id,
                tenant_id=record["tenant_id"],
                user_id=record["user_id"],
                linked_at=linked_at,
            )

    async def lookup(
        self,
        *,
        channel: str,
        sender_id: str,
    ) -> ChannelLink | None:
        async with self._lock_for(channel):
            data = await self._read(channel)
        record = data.get("links", {}).get(sender_id)
        if record is None:
            return None
        return ChannelLink(
            channel=channel,
            sender_id=sender_id,
            tenant_id=record["tenant_id"],
            user_id=record["user_id"],
            linked_at=_parse_iso(record["linked_at"]),
        )

    async def remove_link(
        self,
        *,
        channel: str,
        sender_id: str,
    ) -> bool:
        async with self._lock_for(channel):
            data = await self._read(channel)
            removed = data.get("links", {}).pop(sender_id, None) is not None
            if removed:
                await self._write(channel, data)
                self._logger.info(
                    "channel_link_registry.link_removed",
                    channel=channel,
                    sender_id=sender_id,
                )
            return removed

    async def list_links(
        self,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> list[ChannelLink]:
        results: list[ChannelLink] = []
        for channel_file in sorted(self._base_dir.glob("*.json")):
            channel = channel_file.stem
            async with self._lock_for(channel):
                data = await self._read(channel)
            for sender_id, record in data.get("links", {}).items():
                if tenant_id is not None and record["tenant_id"] != tenant_id:
                    continue
                if user_id is not None and record["user_id"] != user_id:
                    continue
                results.append(
                    ChannelLink(
                        channel=channel,
                        sender_id=sender_id,
                        tenant_id=record["tenant_id"],
                        user_id=record["user_id"],
                        linked_at=_parse_iso(record["linked_at"]),
                    )
                )
        results.sort(key=lambda link: link.linked_at)
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _lock_for(self, channel: str) -> asyncio.Lock:
        safe = self._safe_channel(channel)
        if safe not in self._locks:
            self._locks[safe] = asyncio.Lock()
        return self._locks[safe]

    def _path_for(self, channel: str) -> Path:
        return self._base_dir / f"{self._safe_channel(channel)}.json"

    @staticmethod
    def _safe_channel(channel: str) -> str:
        return channel.replace("/", "_").replace("\\", "_")

    async def _read(self, channel: str) -> dict[str, Any]:
        """Read the channel's JSON document.

        Returns a fresh empty structure for a *missing* file — that's a
        legitimate "no codes, no links yet" state. Any other error
        (permission denied, JSON corruption, …) is logged and
        re-raised so callers do not silently overwrite a damaged
        file with empty state on the next mutation (Codex P2).
        """
        path = self._path_for(channel)
        if not path.exists():
            return {"pending": {}, "links": {}}
        try:
            async with aiofiles.open(path, encoding="utf-8") as handle:
                payload = json.loads(await handle.read())
        except (OSError, json.JSONDecodeError) as exc:
            self._logger.error(
                "channel_link_registry.read_failed",
                channel=channel,
                error=str(exc),
            )
            raise
        data: dict[str, Any] = payload if isinstance(payload, dict) else {}
        data.setdefault("pending", {})
        data.setdefault("links", {})
        return data

    async def _write(self, channel: str, data: dict[str, Any]) -> None:
        """Atomically rewrite the channel's JSON document.

        A failed write is propagated so callers do *not* return success
        on a mutation that never reached disk (Codex P1). The tmp file
        is best-effort cleaned up before the exception escapes so the
        next attempt does not trip over a stale ``.json.tmp``.
        """
        path = self._path_for(channel)
        temp_path = path.with_suffix(".json.tmp")
        try:
            async with aiofiles.open(temp_path, "w", encoding="utf-8") as handle:
                await handle.write(json.dumps(data, indent=2, ensure_ascii=False))
            temp_path.replace(path)
        except OSError as exc:
            self._logger.error(
                "channel_link_registry.write_failed",
                channel=channel,
                error=str(exc),
            )
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    @staticmethod
    def _prune_expired(data: dict[str, Any]) -> None:
        now = _now_utc()
        pending = data.get("pending", {})
        for code in list(pending.keys()):
            try:
                expires_at = _parse_iso(pending[code]["expires_at"])
            except (KeyError, ValueError):
                pending.pop(code, None)
                continue
            if expires_at <= now:
                pending.pop(code, None)

    @staticmethod
    def _mint_code(existing: set[str]) -> str:
        for _ in range(_CODE_GENERATION_RETRIES):
            candidate = _generate_code()
            if candidate not in existing:
                return candidate
        # Extremely unlikely with 10^6 keyspace and short TTL; fall
        # through to a guaranteed-unique probe.
        for offset in range(10**_CODE_DIGITS):
            candidate = f"{offset:0{_CODE_DIGITS}d}"
            if candidate not in existing:
                return candidate
        raise RuntimeError("channel-link code space exhausted")


class InMemoryChannelLinkRegistry:
    """In-memory channel-link registry for tests.

    Mirrors :class:`FileChannelLinkRegistry` semantics (single-use
    codes, TTL expiry, lazy GC) but keeps state in process-local
    dicts so tests can construct one per case.
    """

    def __init__(self) -> None:
        self._pending: dict[str, dict[str, dict[str, Any]]] = {}
        self._links: dict[str, dict[str, dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    async def create_pending_code(
        self,
        *,
        channel: str,
        tenant_id: str,
        user_id: str,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> ChannelLinkCode:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        async with self._lock:
            channel_pending = self._pending.setdefault(channel, {})
            self._prune(channel_pending)
            code = FileChannelLinkRegistry._mint_code(set(channel_pending.keys()))
            expires_at = _now_utc() + timedelta(seconds=ttl_seconds)
            channel_pending[code] = {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "expires_at": expires_at,
            }
            return ChannelLinkCode(
                code=code,
                channel=channel,
                tenant_id=tenant_id,
                user_id=user_id,
                expires_at=expires_at,
            )

    async def consume_code(
        self,
        *,
        channel: str,
        code: str,
        sender_id: str,
    ) -> ChannelLink | None:
        async with self._lock:
            channel_pending = self._pending.setdefault(channel, {})
            self._prune(channel_pending)
            record = channel_pending.pop(code, None)
            if record is None:
                return None
            linked_at = _now_utc()
            self._links.setdefault(channel, {})[sender_id] = {
                "tenant_id": record["tenant_id"],
                "user_id": record["user_id"],
                "linked_at": linked_at,
            }
            return ChannelLink(
                channel=channel,
                sender_id=sender_id,
                tenant_id=record["tenant_id"],
                user_id=record["user_id"],
                linked_at=linked_at,
            )

    async def lookup(
        self,
        *,
        channel: str,
        sender_id: str,
    ) -> ChannelLink | None:
        record = self._links.get(channel, {}).get(sender_id)
        if record is None:
            return None
        return ChannelLink(
            channel=channel,
            sender_id=sender_id,
            tenant_id=record["tenant_id"],
            user_id=record["user_id"],
            linked_at=record["linked_at"],
        )

    async def remove_link(
        self,
        *,
        channel: str,
        sender_id: str,
    ) -> bool:
        async with self._lock:
            return self._links.get(channel, {}).pop(sender_id, None) is not None

    async def list_links(
        self,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> list[ChannelLink]:
        results: list[ChannelLink] = []
        for channel, channel_links in self._links.items():
            for sender_id, record in channel_links.items():
                if tenant_id is not None and record["tenant_id"] != tenant_id:
                    continue
                if user_id is not None and record["user_id"] != user_id:
                    continue
                results.append(
                    ChannelLink(
                        channel=channel,
                        sender_id=sender_id,
                        tenant_id=record["tenant_id"],
                        user_id=record["user_id"],
                        linked_at=record["linked_at"],
                    )
                )
        results.sort(key=lambda link: link.linked_at)
        return results

    @staticmethod
    def _prune(channel_pending: dict[str, dict[str, Any]]) -> None:
        now = _now_utc()
        for code in list(channel_pending.keys()):
            expires_at = channel_pending[code].get("expires_at")
            if isinstance(expires_at, datetime) and expires_at <= now:
                channel_pending.pop(code, None)
