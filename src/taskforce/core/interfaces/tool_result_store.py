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
"""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class ToolResultHandle:
    """
    Lightweight reference to a stored tool result.

    This handle is stored in message history and session state instead of
    the full tool output, keeping token usage under control.

    Attributes:
        id: Unique identifier for this result (e.g., UUID)
        tool: Name of the tool that produced this result
        created_at: ISO 8601 timestamp of result creation
        size_bytes: Size of stored result in bytes
        size_chars: Size of stored result in characters (for text results)
        schema_version: Version of handle format (for future migrations)
        metadata: Additional metadata (e.g., session_id, step, success flag)
    """

    id: str
    tool: str
    created_at: str  # ISO 8601 format
    size_bytes: int
    size_chars: int
    schema_version: str = "1.0"
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert handle to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "tool": self.tool,
            "created_at": self.created_at,
            "size_bytes": self.size_bytes,
            "size_chars": self.size_chars,
            "schema_version": self.schema_version,
            "metadata": self.metadata or {},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolResultHandle":
        """Create handle from dictionary."""
        return cls(
            id=data["id"],
            tool=data["tool"],
            created_at=data["created_at"],
            size_bytes=data["size_bytes"],
            size_chars=data["size_chars"],
            schema_version=data.get("schema_version", "1.0"),
            metadata=data.get("metadata"),
        )


@dataclass
class ToolResultPreview:
    """
    Short preview of a tool result for LLM context.

    Previews are stored in message history alongside handles to give the LLM
    enough context without overwhelming the prompt with full outputs.

    Attributes:
        handle: Reference to the full result
        preview_text: Short excerpt (200-500 chars)
        truncated: Whether the preview is truncated from a larger result
    """

    handle: ToolResultHandle
    preview_text: str
    truncated: bool

    def to_dict(self) -> dict[str, Any]:
        """Convert preview to dictionary for JSON serialization."""
        return {
            "handle": self.handle.to_dict(),
            "preview_text": self.preview_text,
            "truncated": self.truncated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolResultPreview":
        """Create preview from dictionary."""
        return cls(
            handle=ToolResultHandle.from_dict(data["handle"]),
            preview_text=data["preview_text"],
            truncated=data["truncated"],
        )


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

