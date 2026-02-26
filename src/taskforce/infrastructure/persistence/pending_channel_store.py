"""File-based pending channel question store.

Tracks questions sent to external communication channels (Telegram, Teams, …)
and their responses.  Uses a simple JSON-file-per-session approach under the
configured work directory.

Directory layout::

    <work_dir>/pending_channel_questions/
        <session_id>.json   – one file per pending question
        _index.json         – reverse index: channel:recipient_id → session_id
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class FilePendingChannelQuestionStore:
    """File-backed implementation of PendingChannelQuestionStoreProtocol."""

    def __init__(self, work_dir: str = ".taskforce") -> None:
        self._base_dir = Path(work_dir) / "pending_channel_questions"
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._base_dir / "_index.json"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _session_path(self, session_id: str) -> Path:
        safe_id = session_id.replace("/", "_").replace("\\", "_")
        return self._base_dir / f"{safe_id}.json"

    def _load_index(self) -> dict[str, str]:
        """Load the reverse index: key → session_id."""
        if self._index_path.exists():
            try:
                return json.loads(self._index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_index(self, index: dict[str, str]) -> None:
        self._index_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    @staticmethod
    def _key(channel: str, recipient_id: str) -> str:
        return f"{channel}:{recipient_id}"

    # ------------------------------------------------------------------
    # Protocol methods
    # ------------------------------------------------------------------

    async def register(
        self,
        *,
        session_id: str,
        channel: str,
        recipient_id: str,
        question: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a pending question for a channel recipient."""
        entry = {
            "session_id": session_id,
            "channel": channel,
            "recipient_id": recipient_id,
            "question": question,
            "metadata": metadata or {},
            "response": None,
        }
        self._session_path(session_id).write_text(
            json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # Update reverse index
        index = self._load_index()
        index[self._key(channel, recipient_id)] = session_id
        self._save_index(index)

        logger.info(
            "pending_channel_question.registered",
            session_id=session_id,
            channel=channel,
            recipient_id=recipient_id,
        )

    async def resolve(
        self,
        *,
        channel: str,
        sender_id: str,
        response: str,
    ) -> str | None:
        """Resolve a pending question with an inbound response."""
        index = self._load_index()
        key = self._key(channel, sender_id)
        session_id = index.get(key)

        if not session_id:
            return None

        path = self._session_path(session_id)
        if not path.exists():
            # Stale index entry – clean up
            index.pop(key, None)
            self._save_index(index)
            return None

        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        # Already resolved?
        if entry.get("response") is not None:
            return None

        # Store the response
        entry["response"] = response
        path.write_text(
            json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # Remove from reverse index (question is answered)
        index.pop(key, None)
        self._save_index(index)

        logger.info(
            "pending_channel_question.resolved",
            session_id=session_id,
            channel=channel,
            sender_id=sender_id,
        )
        return session_id

    async def get_response(self, *, session_id: str) -> str | None:
        """Get the response for a pending question, if available."""
        path = self._session_path(session_id)
        if not path.exists():
            return None

        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        return entry.get("response")

    async def remove(self, *, session_id: str) -> None:
        """Remove a pending question entry."""
        path = self._session_path(session_id)
        if path.exists():
            # Clean up index first
            try:
                entry = json.loads(path.read_text(encoding="utf-8"))
                index = self._load_index()
                key = self._key(entry["channel"], entry["recipient_id"])
                index.pop(key, None)
                self._save_index(index)
            except (json.JSONDecodeError, OSError, KeyError):
                pass
            path.unlink(missing_ok=True)

        logger.info("pending_channel_question.removed", session_id=session_id)
