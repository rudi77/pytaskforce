"""
Tool Result Cache

Session-scoped caching for tool execution results to prevent redundant API calls.
The cache stores results keyed by tool name + normalized input parameters.

Usage:
    cache = ToolResultCache(default_ttl=3600)
    
    # Check before execution
    cached = cache.get("wiki_get_page", {"path": "/Home"})
    if cached is not None:
        return cached
    
    # Execute and store
    result = await tool.execute(path="/Home")
    cache.put("wiki_get_page", {"path": "/Home"}, result)
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass
class CacheEntry:
    """Single cached tool result with TTL support."""

    tool_name: str
    input_hash: str
    result: dict[str, Any]
    created_at: datetime = field(default_factory=datetime.utcnow)
    ttl_seconds: int = 3600  # Default 1 hour


class ToolResultCache:
    """
    Session-scoped cache for tool execution results.

    Prevents redundant tool calls by storing results keyed by
    tool name + normalized input parameters. Cache entries expire
    after a configurable TTL.

    Attributes:
        _cache: Internal dictionary storing CacheEntry objects
        _default_ttl: Default time-to-live in seconds for cache entries
        _stats: Hit/miss statistics for monitoring

    Example:
        >>> cache = ToolResultCache(default_ttl=3600)
        >>> cache.put("wiki_get_page", {"path": "/Home"}, {"success": True, "content": "Hello"})
        >>> result = cache.get("wiki_get_page", {"path": "/Home"})
        >>> result["content"]
        'Hello'
    """

    def __init__(self, default_ttl: int = 3600):
        """
        Initialize ToolResultCache.

        Args:
            default_ttl: Default time-to-live in seconds for cache entries.
                        Set to 0 for session-lifetime caching (no expiry).
        """
        self._cache: dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl
        self._stats = {"hits": 0, "misses": 0}

    def _compute_key(self, tool_name: str, tool_input: dict) -> str:
        """
        Generate deterministic cache key from tool name and input.

        The key is computed by serializing the input dict with sorted keys
        to ensure deterministic ordering, then hashing with SHA-256.

        Args:
            tool_name: Name of the tool
            tool_input: Input parameters for the tool

        Returns:
            Cache key in format "tool_name:hash_prefix"
        """
        # Normalize input by sorting keys for deterministic hashing
        normalized = json.dumps(tool_input, sort_keys=True, default=str)
        input_hash = hashlib.sha256(normalized.encode()).hexdigest()[:16]
        return f"{tool_name}:{input_hash}"

    def get(self, tool_name: str, tool_input: dict) -> dict[str, Any] | None:
        """
        Retrieve cached result if available and not expired.

        Args:
            tool_name: Name of the tool
            tool_input: Input parameters for the tool

        Returns:
            Cached result dict or None if cache miss or expired
        """
        key = self._compute_key(tool_name, tool_input)
        entry = self._cache.get(key)

        if entry is None:
            self._stats["misses"] += 1
            return None

        # Check TTL (0 means no expiry - session lifetime)
        if entry.ttl_seconds > 0:
            age = (datetime.utcnow() - entry.created_at).total_seconds()
            if age > entry.ttl_seconds:
                del self._cache[key]
                self._stats["misses"] += 1
                return None

        self._stats["hits"] += 1
        return entry.result

    def put(
        self,
        tool_name: str,
        tool_input: dict,
        result: dict[str, Any],
        ttl: int | None = None,
    ) -> None:
        """
        Store tool result in cache.

        Args:
            tool_name: Name of the tool
            tool_input: Input parameters for the tool
            result: Tool execution result to cache
            ttl: Optional TTL override in seconds. If None, uses default_ttl.
        """
        key = self._compute_key(tool_name, tool_input)
        self._cache[key] = CacheEntry(
            tool_name=tool_name,
            input_hash=key.split(":")[1],
            result=result,
            ttl_seconds=ttl if ttl is not None else self._default_ttl,
        )

    def clear(self) -> None:
        """Clear all cached entries and reset statistics."""
        self._cache.clear()
        self._stats = {"hits": 0, "misses": 0}

    def invalidate(self, tool_name: str, tool_input: dict) -> bool:
        """
        Remove a specific entry from the cache.

        Args:
            tool_name: Name of the tool
            tool_input: Input parameters for the tool

        Returns:
            True if entry was found and removed, False otherwise
        """
        key = self._compute_key(tool_name, tool_input)
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    @property
    def stats(self) -> dict[str, int]:
        """
        Return cache hit/miss statistics.

        Returns:
            Dictionary with 'hits' and 'misses' counts
        """
        return self._stats.copy()

    @property
    def size(self) -> int:
        """
        Return number of entries in cache.

        Returns:
            Number of cached entries
        """
        return len(self._cache)

