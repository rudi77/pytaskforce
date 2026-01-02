"""
Unit tests for ToolResultCache.

Tests cache behavior including:
- Cache hits and misses
- Key normalization (deterministic regardless of dict order)
- TTL expiration
- Cache invalidation
- Statistics tracking
"""

from datetime import datetime, timedelta

import pytest

from taskforce.infrastructure.cache.tool_cache import CacheEntry, ToolResultCache


class TestToolResultCache:
    """Test suite for ToolResultCache class."""

    def test_cache_hit(self):
        """Test cache returns stored result on hit."""
        cache = ToolResultCache()

        cache.put(
            "wiki_get_page",
            {"path": "/Home"},
            {"success": True, "content": "Hello World"},
        )
        result = cache.get("wiki_get_page", {"path": "/Home"})

        assert result is not None
        assert result["content"] == "Hello World"
        assert result["success"] is True
        assert cache.stats["hits"] == 1
        assert cache.stats["misses"] == 0

    def test_cache_miss(self):
        """Test cache returns None for unknown key."""
        cache = ToolResultCache()

        result = cache.get("unknown_tool", {"param": "value"})

        assert result is None
        assert cache.stats["misses"] == 1
        assert cache.stats["hits"] == 0

    def test_cache_miss_different_params(self):
        """Test cache returns None when params differ."""
        cache = ToolResultCache()

        cache.put("wiki_get_page", {"path": "/Home"}, {"success": True})
        result = cache.get("wiki_get_page", {"path": "/Other"})

        assert result is None
        assert cache.stats["misses"] == 1

    def test_cache_key_normalization(self):
        """Test cache key is deterministic regardless of dict order."""
        cache = ToolResultCache()

        # Store with one key order
        cache.put("tool", {"b": 2, "a": 1}, {"result": "data"})

        # Retrieve with different key order
        result = cache.get("tool", {"a": 1, "b": 2})

        assert result is not None
        assert result["result"] == "data"
        assert cache.stats["hits"] == 1

    def test_cache_key_with_nested_dicts(self):
        """Test cache key normalization with nested dictionaries."""
        cache = ToolResultCache()

        # Store with nested dict
        cache.put(
            "search",
            {"query": "test", "filters": {"type": "doc", "scope": "all"}},
            {"results": []},
        )

        # Retrieve with same params (different order)
        result = cache.get(
            "search",
            {"filters": {"scope": "all", "type": "doc"}, "query": "test"},
        )

        assert result is not None
        assert cache.stats["hits"] == 1

    def test_cache_ttl_not_expired(self):
        """Test cache entry is returned when TTL not expired."""
        cache = ToolResultCache(default_ttl=3600)  # 1 hour

        cache.put("tool", {"key": "value"}, {"result": "data"})
        result = cache.get("tool", {"key": "value"})

        assert result is not None
        assert result["result"] == "data"

    def test_cache_ttl_expired(self):
        """Test cache entries expire after TTL."""
        cache = ToolResultCache(default_ttl=1)  # 1 second TTL

        cache.put("tool", {"key": "value"}, {"result": "data"})

        # Manually expire by modifying created_at
        key = cache._compute_key("tool", {"key": "value"})
        cache._cache[key].created_at = datetime.utcnow() - timedelta(seconds=2)

        result = cache.get("tool", {"key": "value"})

        assert result is None  # Expired
        assert cache.stats["misses"] == 1
        # Entry should be removed from cache
        assert key not in cache._cache

    def test_cache_ttl_zero_no_expiry(self):
        """Test TTL of 0 means no expiry (session lifetime)."""
        cache = ToolResultCache(default_ttl=0)

        cache.put("tool", {"key": "value"}, {"result": "data"})

        # Even with old created_at, should not expire
        key = cache._compute_key("tool", {"key": "value"})
        cache._cache[key].created_at = datetime.utcnow() - timedelta(days=365)

        result = cache.get("tool", {"key": "value"})

        assert result is not None
        assert cache.stats["hits"] == 1

    def test_cache_custom_ttl_per_entry(self):
        """Test custom TTL can be set per entry."""
        cache = ToolResultCache(default_ttl=3600)

        # Store with custom short TTL
        cache.put("tool", {"key": "value"}, {"result": "data"}, ttl=1)

        # Verify custom TTL was set
        key = cache._compute_key("tool", {"key": "value"})
        assert cache._cache[key].ttl_seconds == 1

    def test_cache_clear(self):
        """Test cache clear removes all entries and resets stats."""
        cache = ToolResultCache()

        cache.put("tool1", {"a": 1}, {"result": "data1"})
        cache.put("tool2", {"b": 2}, {"result": "data2"})
        cache.get("tool1", {"a": 1})  # Hit
        cache.get("tool3", {"c": 3})  # Miss

        cache.clear()

        assert cache.size == 0
        assert cache.stats["hits"] == 0
        assert cache.stats["misses"] == 0

    def test_cache_invalidate_existing(self):
        """Test invalidate removes specific entry."""
        cache = ToolResultCache()

        cache.put("tool", {"key": "value"}, {"result": "data"})
        removed = cache.invalidate("tool", {"key": "value"})

        assert removed is True
        assert cache.get("tool", {"key": "value"}) is None

    def test_cache_invalidate_nonexistent(self):
        """Test invalidate returns False for non-existent entry."""
        cache = ToolResultCache()

        removed = cache.invalidate("tool", {"key": "value"})

        assert removed is False

    def test_cache_size(self):
        """Test cache size property returns correct count."""
        cache = ToolResultCache()

        assert cache.size == 0

        cache.put("tool1", {"a": 1}, {"result": "data1"})
        assert cache.size == 1

        cache.put("tool2", {"b": 2}, {"result": "data2"})
        assert cache.size == 2

        cache.put("tool1", {"a": 1}, {"result": "updated"})  # Overwrite
        assert cache.size == 2

    def test_cache_stats_copy(self):
        """Test stats property returns copy, not reference."""
        cache = ToolResultCache()

        cache.get("tool", {"key": "value"})  # Miss
        stats1 = cache.stats
        stats1["misses"] = 999  # Modify the copy

        stats2 = cache.stats
        assert stats2["misses"] == 1  # Original unchanged

    def test_cache_overwrites_existing(self):
        """Test put overwrites existing entry with same key."""
        cache = ToolResultCache()

        cache.put("tool", {"key": "value"}, {"result": "original"})
        cache.put("tool", {"key": "value"}, {"result": "updated"})

        result = cache.get("tool", {"key": "value"})

        assert result is not None
        assert result["result"] == "updated"
        assert cache.size == 1

    def test_cache_different_tools_same_params(self):
        """Test different tools with same params are cached separately."""
        cache = ToolResultCache()

        cache.put("tool_a", {"path": "/Home"}, {"result": "A"})
        cache.put("tool_b", {"path": "/Home"}, {"result": "B"})

        result_a = cache.get("tool_a", {"path": "/Home"})
        result_b = cache.get("tool_b", {"path": "/Home"})

        assert result_a["result"] == "A"
        assert result_b["result"] == "B"
        assert cache.size == 2


class TestCacheEntry:
    """Test suite for CacheEntry dataclass."""

    def test_cache_entry_defaults(self):
        """Test CacheEntry has correct default values."""
        entry = CacheEntry(
            tool_name="test_tool",
            input_hash="abc123",
            result={"data": "value"},
        )

        assert entry.tool_name == "test_tool"
        assert entry.input_hash == "abc123"
        assert entry.result == {"data": "value"}
        assert entry.ttl_seconds == 3600  # Default 1 hour
        assert isinstance(entry.created_at, datetime)

    def test_cache_entry_custom_ttl(self):
        """Test CacheEntry accepts custom TTL."""
        entry = CacheEntry(
            tool_name="test_tool",
            input_hash="abc123",
            result={"data": "value"},
            ttl_seconds=60,
        )

        assert entry.ttl_seconds == 60

