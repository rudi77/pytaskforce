"""
Infrastructure Cache Module

Provides caching mechanisms for tool results to eliminate redundant API calls.
"""

from taskforce.infrastructure.cache.tool_cache import CacheEntry, ToolResultCache

__all__ = ["CacheEntry", "ToolResultCache"]

