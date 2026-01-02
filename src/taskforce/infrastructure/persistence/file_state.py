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

    def __init__(self, work_dir: str = ".taskforce"):
        """
        Initialize the file-based state manager.

        Args:
            work_dir: Root directory for state storage. Defaults to ".taskforce"
                     in the current working directory.
        """
        self.work_dir = Path(work_dir)
        self.states_dir = self.work_dir / "states"
        self.states_dir.mkdir(parents=True, exist_ok=True)
        self.locks: dict[str, asyncio.Lock] = {}
        self.logger = structlog.get_logger()

    def _get_lock(self, session_id: str) -> asyncio.Lock:
        """
        Get or create a lock for a session.

        Args:
            session_id: Session identifier

        Returns:
            asyncio.Lock instance for the session
        """
        if session_id not in self.locks:
            self.locks[session_id] = asyncio.Lock()
        return self.locks[session_id]

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
            state_data: Dictionary containing session state. Will be modified
                       to include _version and _updated_at fields.

        Returns:
            True if state was saved successfully, False otherwise
        """
        async with self._get_lock(session_id):
            try:
                state_file = self.states_dir / f"{session_id}.json"
                temp_file = self.states_dir / f"{session_id}.json.tmp"

                # Increment version
                current_version = state_data.get("_version", 0)
                state_data["_version"] = current_version + 1
                state_data["_updated_at"] = datetime.now().isoformat()

                # Wrap state data with metadata
                state_to_save = {
                    "session_id": session_id,
                    "timestamp": datetime.now().isoformat(),
                    "state_data": state_data
                }

                # Atomic write: write to temp file, then rename
                async with aiofiles.open(temp_file, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(state_to_save, indent=2, ensure_ascii=False))

                # Atomic rename (Windows requires removing target first)
                if state_file.exists():
                    state_file.unlink()
                temp_file.rename(state_file)

                self.logger.info(
                    "state_saved",
                    session_id=session_id,
                    version=state_data["_version"]
                )
                return True

            except Exception as e:
                self.logger.error(
                    "state_save_failed",
                    session_id=session_id,
                    error=str(e)
                )
                return False

    async def load_state(self, session_id: str) -> dict[str, Any] | None:
        """
        Load session state from JSON file.

        Args:
            session_id: Unique identifier for the session

        Returns:
            Dictionary containing session state if found, empty dict if session
            file exists but is empty, None if session doesn't exist or on error
        """
        try:
            state_file = self.states_dir / f"{session_id}.json"

            if not state_file.exists():
                return {}

            async with aiofiles.open(state_file, encoding="utf-8") as f:
                content = await f.read()
                state = json.loads(content)

            self.logger.info("state_loaded", session_id=session_id)
            return state["state_data"]

        except Exception as e:
            self.logger.error(
                "state_load_failed",
                session_id=session_id,
                error=str(e)
            )
            return None

    async def delete_state(self, session_id: str) -> None:
        """
        Delete session state file.

        Idempotent operation - does not raise exception if file doesn't exist.
        Also cleans up the session lock.

        Args:
            session_id: Unique identifier for the session
        """
        try:
            state_file = self.states_dir / f"{session_id}.json"

            if state_file.exists():
                state_file.unlink()
                self.logger.info("state_deleted", session_id=session_id)

            # Clean up lock
            if session_id in self.locks:
                del self.locks[session_id]

        except Exception as e:
            self.logger.error(
                "state_delete_failed",
                session_id=session_id,
                error=str(e)
            )

    async def list_sessions(self) -> list[str]:
        """
        List all session IDs.

        Scans the states directory for all .json files and extracts session IDs.

        Returns:
            List of session IDs (strings), sorted alphabetically.
            Returns empty list if no sessions or on error.
        """
        try:
            sessions = []
            for state_file in self.states_dir.glob("*.json"):
                # Extract session_id from filename (remove .json extension)
                if not state_file.name.endswith(".tmp"):
                    session_id = state_file.stem
                    sessions.append(session_id)

            return sorted(sessions)

        except Exception as e:
            self.logger.error("list_sessions_failed", error=str(e))
            return []

