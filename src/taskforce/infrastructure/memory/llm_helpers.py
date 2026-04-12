"""Shared LLM helper utilities for memory consolidation and dreaming.

Provides common functions for calling an LLM with JSON output,
parsing responses, and resolving domain enums from strings.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from taskforce.core.domain.experience import ConsolidatedMemoryKind
from taskforce.core.domain.memory import EmotionalValence
from taskforce.core.interfaces.llm import LLMProviderProtocol

logger = structlog.get_logger(__name__)


async def call_llm_json(
    llm: LLMProviderProtocol,
    prompt: str,
    model: str,
) -> dict[str, Any]:
    """Call the LLM and parse the response as JSON.

    Args:
        llm: LLM provider implementing ``complete()``.
        prompt: The prompt to send.
        model: Model alias to use.

    Returns:
        Parsed dict on success.  On parse failure returns a dict
        with ``"_raw"`` containing the raw content.  On error
        returns ``{"_error": ..., "_tokens": 0}``.
    """
    try:
        response = await llm.complete(
            messages=[{"role": "user", "content": prompt}],
            model=model,
        )
        content = response.get("content", "")
        tokens = response.get("usage", {}).get("total_tokens", 0)

        parsed = parse_json(content)
        if isinstance(parsed, dict):
            parsed["_tokens"] = tokens
        elif isinstance(parsed, list):
            return {"items": parsed, "_tokens": tokens}
        else:
            return {"_raw": content, "_tokens": tokens}
        return parsed

    except Exception as exc:
        logger.warning("llm_helpers.call_failed", error=str(exc))
        return {"_error": str(exc), "_tokens": 0}


def parse_json(content: str) -> Any:
    """Extract JSON from LLM response, handling common formatting.

    Tries ``[`` before ``{`` when the content starts with an array
    bracket, so that ``[{"key": "value"}]`` is correctly parsed as
    a list rather than extracting the inner dict.

    Args:
        content: Raw LLM response text.

    Returns:
        Parsed JSON value (dict or list), or empty dict on failure.
    """
    content = content.strip()
    pairs: list[tuple[str, str]] = [("{", "}"), ("[", "]")]
    if content.startswith("["):
        pairs = [("[", "]"), ("{", "}")]
    for start_char, end_char in pairs:
        start = content.find(start_char)
        end = content.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(content[start : end + 1])
            except json.JSONDecodeError:
                continue
    return {}


def resolve_valence(valence_str: str) -> EmotionalValence:
    """Resolve a string to an ``EmotionalValence`` enum value.

    Args:
        valence_str: Raw string from LLM output.

    Returns:
        Matching enum value, or ``NEUTRAL`` as fallback.
    """
    try:
        return EmotionalValence(valence_str)
    except ValueError:
        return EmotionalValence.NEUTRAL


def resolve_memory_kind(kind_str: str) -> ConsolidatedMemoryKind:
    """Resolve a string to a ``ConsolidatedMemoryKind`` enum value.

    Args:
        kind_str: Raw string from LLM output.

    Returns:
        Matching enum value, or ``SEMANTIC`` as fallback.
    """
    try:
        return ConsolidatedMemoryKind(kind_str)
    except ValueError:
        return ConsolidatedMemoryKind.SEMANTIC
