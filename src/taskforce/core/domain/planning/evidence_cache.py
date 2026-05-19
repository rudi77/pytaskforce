"""Run-local evidence cache for source reads.

The cache is deliberately small and serializable. It keeps enough context for
the agent to know what it already read without turning long-term memory into a
scratchpad.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

EVIDENCE_CACHE_KEY = "evidence_cache"
_MAX_CACHE_ITEMS = 30
_MAX_PREVIEW_CHARS = 500
_MAX_CACHED_CONTENT_CHARS = 50_000


def normalize_source_path(path: str | None) -> str:
    """Return a stable path key for repeat-read detection."""
    if not path:
        return ""
    normalized = str(Path(str(path)).expanduser())
    return normalized.replace("\\", "/").lower()


def record_file_read_evidence(
    state: dict[str, Any],
    args: dict[str, Any],
    result: dict[str, Any],
    step: int,
) -> dict[str, Any] | None:
    """Record a compact evidence entry after a successful ``file_read``."""
    if not result.get("success"):
        return None

    path = str(result.get("path") or args.get("path") or "").strip()
    normalized_path = normalize_source_path(path)
    if not normalized_path:
        return None

    cache = state.setdefault(EVIDENCE_CACHE_KEY, {})
    if not isinstance(cache, dict):
        cache = {}
        state[EVIDENCE_CACHE_KEY] = cache
    was_seen = normalized_path in cache

    metrics = state.setdefault("file_read_metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
        state["file_read_metrics"] = metrics
    metrics["repeat_count"] = int(metrics.get("repeat_count", 0)) + (
        1 if was_seen else 0
    )

    content = str(result.get("content") or "")
    preview = content[:_MAX_PREVIEW_CHARS]
    entry: dict[str, Any] = {
        "path": path,
        "normalized_path": normalized_path,
        "step": step,
        "size": int(result.get("size") or len(content)),
        "preview": preview,
    }
    if len(content) <= _MAX_CACHED_CONTENT_CHARS:
        entry["content"] = content

    cache[normalized_path] = entry
    metrics["unique_paths"] = len(cache)
    if len(cache) > _MAX_CACHE_ITEMS:
        oldest = sorted(
            cache.items(),
            key=lambda item: int(item[1].get("step", 0))
            if isinstance(item[1], dict)
            else 0,
        )
        for key, _ in oldest[: len(cache) - _MAX_CACHE_ITEMS]:
            cache.pop(key, None)

    return entry


def cached_file_read_result(
    state: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any] | None:
    """Return a synthetic ``file_read`` result for an unchanged cached path."""
    normalized_path = normalize_source_path(str(args.get("path") or ""))
    if not normalized_path:
        return None
    cache = state.get(EVIDENCE_CACHE_KEY)
    if not isinstance(cache, dict):
        return None
    entry = cache.get(normalized_path)
    if not isinstance(entry, dict) or "content" not in entry:
        return None
    content = str(entry.get("content") or "")
    return {
        "success": True,
        "cached": True,
        "path": entry.get("path") or args.get("path"),
        "content": content,
        "size": int(entry.get("size") or len(content)),
    }


def invalidate_file_read_evidence(
    state: dict[str, Any],
    path: str | None,
) -> None:
    """Drop cached evidence for a path that may have changed."""
    normalized_path = normalize_source_path(path)
    if not normalized_path:
        return
    cache = state.get(EVIDENCE_CACHE_KEY)
    if isinstance(cache, dict):
        cache.pop(normalized_path, None)


def build_repeat_read_nudge(path: str) -> str:
    """Create a short system nudge for repeated file reads."""
    return (
        "[System: You already read this file during the current run: "
        f"`{path}`. Do not read it again unless you believe it changed. "
        "Use the `Already read this run` evidence in the context pack and "
        "continue toward the requested deliverables.]"
    )
