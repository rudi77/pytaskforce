"""
File-based Tool Result Store Implementation

This module provides a simple file-based implementation of the ToolResultStore
protocol. Tool results are stored as JSON files in a configurable directory,
with one file per result.

Design:
- Each result stored as {handle_id}.json in store_dir
- Handles stored separately for quick metadata access
- Session-scoped cleanup via metadata tracking
- Simple, debuggable file structure

Directory Structure:
    store_dir/
        results/
            abc-123.json        # Full tool result
            def-456.json
        handles/
            abc-123.json        # Handle metadata
            def-456.json
"""

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import aiofiles
import structlog

from taskforce.core.interfaces.tool_result_store import ToolResultHandle


class FileToolResultStore:
    """
    File-based implementation of ToolResultStore protocol.

    Stores tool results as JSON files in a directory structure.
    Simple, debuggable, suitable for development and single-machine
    deployments.

    Thread Safety:
        Uses asyncio locks per handle ID to prevent concurrent write
        conflicts. Read operations are lock-free (write-once).
    """

    def __init__(self, store_dir: str | Path = "./tool_results"):
        """
        Initialize file-based tool result store.

        Args:
            store_dir: Directory for storing results
                      (default: ./tool_results).
        """
        self.store_dir = Path(store_dir)
        self.results_dir = self.store_dir / "results"
        self.handles_dir = self.store_dir / "handles"
        self.logger = structlog.get_logger().bind(
            component="tool_result_store"
        )

        # Locks for concurrent access (per handle ID)
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_lock = asyncio.Lock()

    async def _ensure_dirs(self) -> None:
        """Create store directories if they don't exist."""
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.handles_dir.mkdir(parents=True, exist_ok=True)

    async def _get_lock(self, handle_id: str) -> asyncio.Lock:
        """Get or create lock for a handle ID."""
        async with self._locks_lock:
            if handle_id not in self._locks:
                self._locks[handle_id] = asyncio.Lock()
            return self._locks[handle_id]

    def _result_path(self, handle_id: str) -> Path:
        """Get file path for a result."""
        return self.results_dir / f"{handle_id}.json"

    def _handle_path(self, handle_id: str) -> Path:
        """Get file path for a handle."""
        return self.handles_dir / f"{handle_id}.json"

    async def put(
        self,
        tool_name: str,
        result: dict[str, Any],
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolResultHandle:
        """
        Store a tool result and return a handle.

        Implementation:
        1. Generate unique ID (UUID)
        2. Serialize result to JSON and calculate size
        3. Write result file atomically
        4. Create and write handle metadata
        5. Return handle

        Args:
            tool_name: Name of the tool that produced this result
            result: Full tool result dictionary
            session_id: Optional session ID for scoping/cleanup
            metadata: Optional metadata (e.g., step number, success flag)

        Returns:
            ToolResultHandle with unique ID and size information
        """
        await self._ensure_dirs()

        # Generate unique ID
        handle_id = str(uuid.uuid4())
        lock = await self._get_lock(handle_id)

        async with lock:
            # Serialize result
            result_json = json.dumps(
                result, ensure_ascii=False, indent=2, default=str
            )
            size_bytes = len(result_json.encode("utf-8"))
            size_chars = len(result_json)

            # Build metadata
            full_metadata = metadata or {}
            if session_id:
                full_metadata["session_id"] = session_id
            # noqa: E501
            full_metadata["success"] = result.get("success", False)

            # Create handle
            handle = ToolResultHandle(
                id=handle_id,
                tool=tool_name,
                created_at=datetime.utcnow().isoformat() + "Z",
                size_bytes=size_bytes,
                size_chars=size_chars,
                schema_version="1.0",
                metadata=full_metadata,
            )

            # Write result file
            result_path = self._result_path(handle_id)
            async with aiofiles.open(result_path, "w", encoding="utf-8") as f:
                await f.write(result_json)

            # Write handle file
            handle_path = self._handle_path(handle_id)
            handle_json = json.dumps(handle.to_dict(), indent=2)
            async with aiofiles.open(handle_path, "w", encoding="utf-8") as f:
                await f.write(handle_json)

            self.logger.info(
                "tool_result_stored",
                handle_id=handle_id,
                tool=tool_name,
                size_bytes=size_bytes,
                size_chars=size_chars,
                session_id=session_id,
            )

            return handle

    async def fetch(
        self,
        handle: ToolResultHandle,
        selector: str | None = None,
        max_chars: int | None = None,
    ) -> dict[str, Any] | None:
        """
        Retrieve a stored tool result by handle.

        Implementation:
        1. Check if result file exists
        2. Read and parse JSON
        3. Apply selector if provided (future feature)
        4. Apply max_chars limit if provided
        5. Return result

        Args:
            handle: Handle returned from put()
            selector: Optional selector for partial retrieval
                     (not yet implemented)
            max_chars: Optional limit on returned data size

        Returns:
            Full tool result dictionary, or None if not found
        """
        result_path = self._result_path(handle.id)

        if not result_path.exists():
            self.logger.warning("tool_result_not_found", handle_id=handle.id)
            return None

        try:
            async with aiofiles.open(result_path, "r", encoding="utf-8") as f:
                content = await f.read()

            result = json.loads(content)

            # Apply max_chars limit if specified
            if max_chars and len(content) > max_chars:
                # Truncate large fields
                result = self._truncate_result(result, max_chars)

            self.logger.debug("tool_result_fetched", handle_id=handle.id)
            return result

        except Exception as e:
            self.logger.error(
                "tool_result_fetch_failed",
                handle_id=handle.id,
                error=str(e),
            )
            return None

    def _truncate_result(
        self,
        result: dict[str, Any],
        max_chars: int,
    ) -> dict[str, Any]:
        """
        Truncate large fields in result to meet max_chars limit.

        Args:
            result: Original result dictionary
            max_chars: Maximum total characters

        Returns:
            Truncated result dictionary
        """
        truncated = result.copy()
        large_fields = [
            "output",
            "result",
            "content",
            "stdout",
            "stderr",
            "data",
        ]

        for field in large_fields:
            if field in truncated and isinstance(truncated[field], str):
                field_limit = max_chars // len(large_fields)
                if len(truncated[field]) > field_limit:
                    truncated[field] = (
                        truncated[field][:field_limit] + "... [TRUNCATED]"
                    )

        return truncated

    async def delete(self, handle: ToolResultHandle) -> bool:
        """
        Delete a stored tool result.

        Implementation:
        1. Acquire lock for handle ID
        2. Delete result file
        3. Delete handle file
        4. Return success status

        Args:
            handle: Handle of result to delete

        Returns:
            True if deleted, False if not found
        """
        lock = await self._get_lock(handle.id)

        async with lock:
            result_path = self._result_path(handle.id)
            handle_path = self._handle_path(handle.id)

            deleted = False

            if result_path.exists():
                result_path.unlink()
                deleted = True

            if handle_path.exists():
                handle_path.unlink()
                deleted = True

            if deleted:
                self.logger.info("tool_result_deleted", handle_id=handle.id)
            else:
                self.logger.warning(
                    "tool_result_not_found_for_delete",
                    handle_id=handle.id,
                )

            return deleted

    async def cleanup_session(self, session_id: str) -> int:
        """
        Delete all tool results for a session.

        Implementation:
        1. Scan all handle files
        2. Load handles with matching session_id
        3. Delete each result and handle
        4. Return count

        Args:
            session_id: Session ID to clean up

        Returns:
            Number of results deleted
        """
        await self._ensure_dirs()

        count = 0
        handle_files = list(self.handles_dir.glob("*.json"))

        for handle_path in handle_files:
            try:
                async with aiofiles.open(
                    handle_path, "r", encoding="utf-8"
                ) as f:
                    handle_data = json.loads(await f.read())

                # Check if this handle belongs to the session
                metadata = handle_data.get("metadata", {})
                if metadata.get("session_id") == session_id:
                    handle = ToolResultHandle.from_dict(handle_data)
                    if await self.delete(handle):
                        count += 1

            except Exception as e:
                self.logger.warning(
                    "cleanup_handle_failed",
                    handle_path=str(handle_path),
                    error=str(e),
                )

        self.logger.info(
            "session_cleanup_complete", session_id=session_id, count=count
        )
        return count

    async def get_stats(self) -> dict[str, Any]:
        """
        Get storage statistics.

        Implementation:
        1. Scan all result files
        2. Calculate total size and count
        3. Find oldest/newest timestamps
        4. Return stats dictionary

        Returns:
            Dictionary with storage statistics
        """
        await self._ensure_dirs()

        result_files = list(self.results_dir.glob("*.json"))
        handle_files = list(self.handles_dir.glob("*.json"))

        total_bytes = sum(
            f.stat().st_size for f in result_files if f.exists()
        )
        total_results = len(result_files)

        # Find oldest and newest
        timestamps = []
        for handle_path in handle_files:
            try:
                async with aiofiles.open(
                    handle_path, "r", encoding="utf-8"
                ) as f:
                    handle_data = json.loads(await f.read())
                    timestamps.append(handle_data.get("created_at", ""))
            except Exception:
                pass

        timestamps.sort()

        return {
            "total_results": total_results,
            "total_bytes": total_bytes,
            "total_mb": round(total_bytes / 1024 / 1024, 2),
            "oldest_result": timestamps[0] if timestamps else None,
            "newest_result": timestamps[-1] if timestamps else None,
            "store_dir": str(self.store_dir),
        }
