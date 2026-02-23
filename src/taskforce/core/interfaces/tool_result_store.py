"""
Tool Result Store Protocol

This module defines the protocol interface for storing and retrieving large
tool execution results. The store enables agents to keep message history small
by storing full tool outputs externally and only keeping lightweight handles
and previews in the message history.

Key Concepts:
- ToolResultHandle: Lightweight reference to a stored tool result
- ToolResultStore: Storage abstraction for tool results
- Preview: Short excerpt of result for LLM context (200-500 chars)
- Selector: Query mechanism for retrieving specific parts of results (future)

Data model classes (ToolResultHandle, ToolResultPreview, LineageNode, LineageGraph)
are defined in ``taskforce.core.domain.tool_result`` and re-exported here for
backward compatibility.
"""

from typing import Any, Protocol

# Re-export data model classes from their canonical location in the domain layer.
# Existing imports such as
#     from taskforce.core.interfaces.tool_result_store import ToolResultHandle
# will continue to work.
from taskforce.core.domain.tool_result import (  # noqa: F401
    LineageGraph,
    LineageNode,
    ToolResultHandle,
    ToolResultPreview,
    _utcnow_str,
)

__all__ = [
    "LineageGraph",
    "LineageNode",
    "ToolResultHandle",
    "ToolResultPreview",
    "ToolResultStoreProtocol",
    "_utcnow_str",
]


class ToolResultStoreProtocol(Protocol):
    """
    Protocol defining the contract for tool result storage.

    Implementations provide persistent storage for large tool outputs,
    enabling agents to keep message history small while maintaining
    debuggability and context retrieval capabilities.

    Design Goals:
    - Stop message history from exploding with large tool outputs
    - Maintain debuggability (full results available on demand)
    - Support future enhancements (selectors, compression, TTL)
    - Simple MVP implementation path (file-based or in-memory)

    Thread Safety:
        Implementations should handle concurrent access safely, though
        in practice tool results are write-once and session-scoped.
    """

    async def put(
        self,
        tool_name: str,
        result: dict[str, Any],
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolResultHandle:
        """
        Store a tool result and return a handle.

        Args:
            tool_name: Name of the tool that produced this result
            result: Full tool result dictionary (from tool.execute())
            session_id: Optional session ID for scoping/cleanup
            metadata: Optional metadata (e.g., step number, success flag)

        Returns:
            ToolResultHandle with unique ID and size information

        Example:
            >>> result = {"success": True, "output": "..." * 10000}
            >>> handle = await store.put("file_read", result, "session_1")
            >>> print(f"Stored {handle.size_chars} chars with ID {handle.id}")
        """
        ...

    async def fetch(
        self,
        handle: ToolResultHandle,
        selector: str | None = None,
        max_chars: int | None = None,
    ) -> dict[str, Any] | None:
        """
        Retrieve a stored tool result by handle.

        Args:
            handle: Handle returned from put()
            selector: Optional selector for partial retrieval (future feature)
                     Examples: "output", "output[:1000]", "result.data"
            max_chars: Optional limit on returned data size

        Returns:
            Full tool result dictionary, or None if not found

        Example:
            >>> result = await store.fetch(handle)
            >>> if result:
            ...     print(f"Success: {result['success']}")
            ...     print(f"Output length: {len(result['output'])}")
        """
        ...

    async def delete(self, handle: ToolResultHandle) -> bool:
        """
        Delete a stored tool result.

        Args:
            handle: Handle of result to delete

        Returns:
            True if deleted, False if not found

        Example:
            >>> deleted = await store.delete(handle)
            >>> assert deleted is True
        """
        ...

    async def cleanup_session(self, session_id: str) -> int:
        """
        Delete all tool results for a session.

        Args:
            session_id: Session ID to clean up

        Returns:
            Number of results deleted

        Example:
            >>> count = await store.cleanup_session("session_1")
            >>> print(f"Deleted {count} tool results")
        """
        ...

    async def get_stats(self) -> dict[str, Any]:
        """
        Get storage statistics.

        Returns:
            Dictionary with stats like:
            - total_results: Number of stored results
            - total_bytes: Total storage used
            - oldest_result: Timestamp of oldest result
            - newest_result: Timestamp of newest result

        Example:
            >>> stats = await store.get_stats()
            >>> print(f"Storing {stats['total_results']} results")
            >>> print(f"Using {stats['total_bytes'] / 1024 / 1024:.2f} MB")
        """
        ...
