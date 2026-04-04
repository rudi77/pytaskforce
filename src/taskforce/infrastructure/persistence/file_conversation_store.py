"""
File-Based Conversation Store

Implements ``ConversationManagerProtocol`` for the persistent agent (ADR-016).
Stores conversation metadata and messages as JSON files on disk.

Directory layout::

    {work_dir}/conversations/
        index.json              # Conversation metadata index
        {conv_id}/
            messages.json       # Message history
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiofiles
import structlog

from taskforce.core.domain.conversation import Conversation, ConversationStatus
from taskforce.core.interfaces.conversation import (
    ConversationInfo,
    ConversationManagerProtocol,
    ConversationSummary,
)

logger = structlog.get_logger(__name__)


class FileConversationStore:
    """File-based conversation management.

    Metadata for all conversations is kept in a single ``index.json`` file.
    Messages for each conversation are stored in a separate directory.
    """

    def __init__(self, work_dir: str = ".taskforce") -> None:
        self._base_dir = Path(work_dir) / "conversations"
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._index_file = self._base_dir / "index.json"

    # ------------------------------------------------------------------
    # ConversationManagerProtocol implementation
    # ------------------------------------------------------------------

    async def get_or_create(
        self,
        channel: str,
        sender_id: str | None = None,
    ) -> str:
        """Return the active conversation for channel/sender, or create one."""
        index = await self._load_index()
        for conv in index:
            if (
                conv["status"] == ConversationStatus.ACTIVE.value
                and conv["channel"] == channel
                and conv.get("sender_id") == sender_id
            ):
                return conv["conversation_id"]

        return await self.create_new(channel, sender_id)

    async def create_new(self, channel: str, sender_id: str | None = None) -> str:
        """Create a new conversation, archiving any existing active one."""
        index = await self._load_index()

        # Archive the currently active conversation for this channel/sender.
        for conv in index:
            if (
                conv["status"] == ConversationStatus.ACTIVE.value
                and conv["channel"] == channel
                and conv.get("sender_id") == sender_id
            ):
                conv["status"] = ConversationStatus.ARCHIVED.value
                conv["archived_at"] = datetime.now(UTC).isoformat()

        conv_id = uuid4().hex
        now = datetime.now(UTC).isoformat()
        entry: dict[str, Any] = {
            "conversation_id": conv_id,
            "channel": channel,
            "status": ConversationStatus.ACTIVE.value,
            "started_at": now,
            "last_activity": now,
            "message_count": 0,
            "topic": None,
            "summary": None,
            "archived_at": None,
            "sender_id": sender_id,
        }
        index.append(entry)
        await self._save_index(index)

        # Create empty messages file.
        conv_dir = self._base_dir / conv_id
        conv_dir.mkdir(parents=True, exist_ok=True)
        await self._write_json(conv_dir / "messages.json", [])

        logger.info(
            "conversation.created",
            conversation_id=conv_id,
            channel=channel,
        )
        return conv_id

    async def append_message(
        self,
        conversation_id: str,
        message: dict[str, Any],
    ) -> None:
        """Append a message and update conversation metadata."""
        messages = await self._load_messages(conversation_id)
        messages.append(message)
        await self._save_messages(conversation_id, messages)

        # Update index metadata.
        index = await self._load_index()
        for conv in index:
            if conv["conversation_id"] == conversation_id:
                conv["last_activity"] = datetime.now(UTC).isoformat()
                conv["message_count"] = len(messages)
                break
        await self._save_index(index)

    async def get_messages(
        self,
        conversation_id: str,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve messages, optionally limiting to the N most recent."""
        messages = await self._load_messages(conversation_id)
        if limit is not None:
            return messages[-limit:]
        return messages

    async def archive(
        self,
        conversation_id: str,
        summary: str | None = None,
    ) -> None:
        """Archive a conversation."""
        index = await self._load_index()
        for conv in index:
            if conv["conversation_id"] == conversation_id:
                conv["status"] = ConversationStatus.ARCHIVED.value
                conv["archived_at"] = datetime.now(UTC).isoformat()
                if summary is not None:
                    conv["summary"] = summary
                break
        await self._save_index(index)
        logger.info("conversation.archived", conversation_id=conversation_id)

    async def list_active(self) -> list[ConversationInfo]:
        """List active conversations ordered by last activity (newest first)."""
        index = await self._load_index()
        active = [
            c for c in index if c["status"] == ConversationStatus.ACTIVE.value
        ]
        active.sort(key=lambda c: c["last_activity"], reverse=True)
        return [
            ConversationInfo(
                conversation_id=c["conversation_id"],
                channel=c["channel"],
                started_at=datetime.fromisoformat(c["started_at"]),
                last_activity=datetime.fromisoformat(c["last_activity"]),
                message_count=c["message_count"],
                topic=c.get("topic"),
            )
            for c in active
        ]

    async def list_archived(self, limit: int = 20) -> list[ConversationSummary]:
        """List archived conversations ordered by archive date (newest first)."""
        index = await self._load_index()
        archived = [
            c
            for c in index
            if c["status"] == ConversationStatus.ARCHIVED.value and c.get("archived_at")
        ]
        archived.sort(key=lambda c: c["archived_at"], reverse=True)
        return [
            ConversationSummary(
                conversation_id=c["conversation_id"],
                topic=c.get("topic") or "",
                summary=c.get("summary") or "",
                started_at=datetime.fromisoformat(c["started_at"]),
                archived_at=datetime.fromisoformat(c["archived_at"]),
                message_count=c["message_count"],
            )
            for c in archived[:limit]
        ]

    async def get_conversation(self, conversation_id: str) -> Conversation | None:
        """Load a full Conversation domain object.

        This is used by the ConversationManager for topic segmentation.
        Returns ``None`` if the conversation is not found.
        """
        index = await self._load_index()
        for entry in index:
            if entry["conversation_id"] == conversation_id:
                from datetime import datetime as dt

                started = entry.get("started_at", "")
                last = entry.get("last_activity", "")
                conv = Conversation(
                    channel=entry["channel"],
                    conversation_id=entry["conversation_id"],
                    status=ConversationStatus(entry.get("status", "active")),
                    started_at=(
                        dt.fromisoformat(started) if isinstance(started, str) and started
                        else datetime.now(UTC)
                    ),
                    last_activity=(
                        dt.fromisoformat(last) if isinstance(last, str) and last
                        else datetime.now(UTC)
                    ),
                    message_count=entry.get("message_count", 0),
                    topic=entry.get("topic"),
                    summary=entry.get("summary"),
                    sender_id=entry.get("sender_id"),
                    metadata=entry.get("metadata", {}),
                )
                # Load topic segments if stored.
                segments_data = entry.get("topic_segments", [])
                if segments_data:
                    from taskforce.core.domain.conversation import TopicSegment

                    for seg_data in segments_data:
                        seg = TopicSegment(
                            label=seg_data.get("label", ""),
                            topic_id=seg_data.get("topic_id", ""),
                            summary=seg_data.get("summary"),
                            source=seg_data.get("source", "user"),
                            priority=seg_data.get("priority", 0),
                            message_range=tuple(seg_data.get("message_range", [0, 0])),
                        )
                        if seg_data.get("started_at"):
                            seg.started_at = dt.fromisoformat(seg_data["started_at"])
                        if seg_data.get("ended_at"):
                            seg.ended_at = dt.fromisoformat(seg_data["ended_at"])
                        conv.topic_segments.append(seg)
                conv.active_topic_id = entry.get("active_topic_id")
                return conv
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _load_index(self) -> list[dict[str, Any]]:
        """Load the conversation index from disk."""
        if not self._index_file.exists():
            return []
        try:
            async with aiofiles.open(self._index_file, encoding="utf-8") as f:
                content = await f.read()
            return json.loads(content) if content.strip() else []
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("conversation.index_load_failed", error=str(exc))
            return []

    async def _save_index(self, index: list[dict[str, Any]]) -> None:
        """Persist the conversation index to disk."""
        await self._write_json(self._index_file, index)

    async def _load_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        """Load messages for a conversation."""
        msg_file = self._base_dir / conversation_id / "messages.json"
        if not msg_file.exists():
            return []
        try:
            async with aiofiles.open(msg_file, encoding="utf-8") as f:
                content = await f.read()
            return json.loads(content) if content.strip() else []
        except (OSError, json.JSONDecodeError) as exc:
            logger.error(
                "conversation.messages_load_failed",
                conversation_id=conversation_id,
                error=str(exc),
            )
            return []

    async def _save_messages(
        self,
        conversation_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        """Persist messages for a conversation."""
        conv_dir = self._base_dir / conversation_id
        conv_dir.mkdir(parents=True, exist_ok=True)
        await self._write_json(conv_dir / "messages.json", messages)

    async def _write_json(self, path: Path, data: Any) -> None:
        """Write JSON to a file atomically."""
        temp = path.with_suffix(".json.tmp")
        payload = json.dumps(data, indent=2, ensure_ascii=False)
        async with aiofiles.open(temp, "w", encoding="utf-8") as f:
            await f.write(payload)
        if path.exists():
            path.unlink()
        temp.rename(path)
