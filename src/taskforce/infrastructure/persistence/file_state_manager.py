"""
File-Based State Manager

This module provides a file-based implementation of the StateManagerProtocol,
using JSON files for state persistence. It's designed for development environments
where database setup is not required.

The implementation is compatible with Agent V2 state files and provides:
- Async file I/O using aiofiles
- State versioning for optimistic locking
- Atomic writes (write to temp file, then rename)
- Session-based file organization
- Concurrent access safety via asyncio locks
"""

import asyncio
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import aiofiles
import structlog

from taskforce.core.interfaces.state import StateManagerProtocol


class FileStateManager(StateManagerProtocol):
    """
    File-based state persistence implementing StateManagerProtocol.

    State files are stored as JSON in the directory structure:
    {work_dir}/states/{session_id}.json

    Each state file contains:
    - session_id: Unique identifier
    - timestamp: Last save time
    - state_data: The actual session state (with _version and _updated_at)

    Thread Safety:
        Uses asyncio locks per session_id to prevent concurrent writes.

    Atomic Writes:
        Writes to a temporary file first, then renames to ensure atomicity.

    Example:
        >>> manager = FileStateManager(work_dir=".taskforce")
        >>> state_data = {"todolist_id": "abc-123", "answers": {}}
        >>> await manager.save_state("session_1", state_data)
        >>> loaded = await manager.load_state("session_1")
        >>> assert loaded["todolist_id"] == "abc-123"
    """

    def __init__(
        self,
        work_dir: str = ".taskforce",
        time_provider: Callable[[], datetime] | None = None,
    ):
        """
        Initialize the file-based state manager.

        Args:
            work_dir: Root directory for state storage. Defaults to ".taskforce"
                     in the current working directory.
        """
        self.work_dir = Path(work_dir)
        self.states_dir = self.work_dir / "states"
        self.states_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_lock = asyncio.Lock()
        self.logger = structlog.get_logger()
        self._time_provider = time_provider or datetime.now

    def _now_isoformat(self) -> str:
        """
        Return current timestamp in ISO format.

        Returns:
            ISO-formatted timestamp string
        """
        return self._time_provider().isoformat()

    def _build_state_payload(
        self,
        session_id: str,
        state_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build a new state payload with versioning metadata.

        Args:
            session_id: Unique identifier for the session
            state_data: Dictionary containing session state

        Returns:
            State payload ready for JSON serialization
        """
        state_copy = dict(state_data)
        current_version = int(state_copy.get("_version", 0))
        state_copy["_version"] = current_version + 1
        state_copy["_updated_at"] = self._now_isoformat()
        return {
            "session_id": session_id,
            "timestamp": self._now_isoformat(),
            "state_data": state_copy,
        }

    def _serialize_state_payload(
        self,
        session_id: str,
        state_data: dict[str, Any],
    ) -> tuple[str, int]:
        """
        Serialize state payload to JSON.

        Args:
            session_id: Unique identifier for the session
            state_data: Dictionary containing session state

        Returns:
            Tuple of JSON payload string and version number
        """
        payload = self._build_state_payload(session_id, state_data)
        payload_json = json.dumps(payload, indent=2, ensure_ascii=False)
        return payload_json, int(payload["state_data"]["_version"])

    async def _write_state_file(
        self,
        temp_file: Path,
        state_file: Path,
        payload_json: str,
    ) -> None:
        """
        Write the state payload to disk atomically.

        Args:
            temp_file: Temporary file path
            state_file: Final file path
            payload_json: JSON payload string
        """
        async with aiofiles.open(temp_file, "w", encoding="utf-8") as f:
            await f.write(payload_json)
        if state_file.exists():
            state_file.unlink()
        temp_file.rename(state_file)

    async def _get_lock(self, session_id: str) -> asyncio.Lock:
        """Get or create a lock for a session.

        Thread-safe: uses a master lock to protect the lock dict.

        Args:
            session_id: Session identifier

        Returns:
            asyncio.Lock instance for the session
        """
        async with self._locks_lock:
            if session_id not in self._locks:
                self._locks[session_id] = asyncio.Lock()
            return self._locks[session_id]

    async def save_state(self, session_id: str, state_data: dict[str, Any]) -> bool:
        """
        Save session state to JSON file with versioning.

        Implements atomic write pattern:
        1. Acquire session lock
        2. Increment version
        3. Write to temporary file
        4. Rename to final location

        Args:
            session_id: Unique identifier for the session
            state_data: Dictionary containing session state.

        Returns:
            True if state was saved successfully, False otherwise
        """
        async with await self._get_lock(session_id):
            state_file = self.states_dir / f"{session_id}.json"
            temp_file = self.states_dir / f"{session_id}.json.tmp"

            try:
                payload_json, version = self._serialize_state_payload(session_id, state_data)
            except (TypeError, ValueError) as exc:
                self.logger.error(
                    "state_save_serialization_failed",
                    session_id=session_id,
                    error=str(exc),
                )
                return False

            try:
                await self._write_state_file(temp_file, state_file, payload_json)
            except OSError as exc:
                self.logger.error(
                    "state_save_failed",
                    session_id=session_id,
                    error=str(exc),
                )
                return False

            self.logger.info(
                "state_saved",
                session_id=session_id,
                version=version,
            )
            return True

    async def load_state(self, session_id: str) -> dict[str, Any] | None:
        """
        Load session state from JSON file.

        Args:
            session_id: Unique identifier for the session

        Returns:
            Dictionary containing session state if found, empty dict if session
            doesn't exist, None on error
        """
        state_file = self.states_dir / f"{session_id}.json"

        if not state_file.exists():
            return {}

        try:
            async with aiofiles.open(state_file, encoding="utf-8") as f:
                content = await f.read()
            state = json.loads(content)
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            self.logger.error(
                "state_load_failed",
                session_id=session_id,
                error=str(exc),
            )
            return None

        self.logger.info("state_loaded", session_id=session_id)
        return state.get("state_data", {})  # type: ignore[no-any-return]

    async def delete_state(self, session_id: str) -> None:
        """
        Delete session state file.

        Idempotent operation - does not raise exception if file doesn't exist.
        Also cleans up the session lock.

        Args:
            session_id: Unique identifier for the session
        """
        state_file = self.states_dir / f"{session_id}.json"

        try:
            if state_file.exists():
                state_file.unlink()
                self.logger.info("state_deleted", session_id=session_id)
        except OSError as exc:
            self.logger.error(
                "state_delete_failed",
                session_id=session_id,
                error=str(exc),
            )
            return

        if session_id in self._locks:
            del self._locks[session_id]

    async def list_sessions(self) -> list[str]:
        """
        List all session IDs.

        Scans the states directory for all .json files and extracts session IDs.

        Returns:
            List of session IDs (strings), sorted alphabetically.
            Returns empty list if no sessions or on error.
        """
        sessions = []
        try:
            for state_file in self.states_dir.glob("*.json"):
                if not state_file.name.endswith(".tmp"):
                    sessions.append(state_file.stem)
        except OSError as exc:
            self.logger.error("list_sessions_failed", error=str(exc))
            return []

        return sorted(sessions)
