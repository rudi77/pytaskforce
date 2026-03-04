"""Lightweight memory consolidation without LLM calls.

Runs the purely algorithmic phases of the sleep-cycle consolidation:
decay, reinforcement, and association building.  This is cheap enough
to run after every session, while the full LLM-powered pipeline
(``ConsolidationEngine``) should be scheduled periodically.

When an embedding provider is supplied, associations are built using
**cosine similarity** between memory embeddings instead of tag overlap.
This produces far more accurate semantic links.

Usage::

    from taskforce.infrastructure.memory.lightweight_consolidation import (
        run_lightweight_consolidation,
    )

    result = await run_lightweight_consolidation(memory_store, session_keywords)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog

from taskforce.core.interfaces.memory_store import MemoryStoreProtocol

logger = structlog.get_logger(__name__)

# Default threshold below which memories are archived.
_ARCHIVE_THRESHOLD: float = 0.10

# Minimum cosine similarity to form an embedding-based association.
_EMBEDDING_SIMILARITY_THRESHOLD: float = 0.55

# Minimum tag overlap for fallback tag-based association.
_MIN_TAG_OVERLAP: int = 1

# Maximum associations per memory.
_MAX_ASSOCIATIONS: int = 10


@dataclass
class LightweightConsolidationResult:
    """Result of a lightweight (no-LLM) consolidation pass."""

    decayed: int = 0
    archived: int = 0
    strengthened: int = 0
    associations_created: int = 0
    duration_ms: int = 0


async def run_lightweight_consolidation(
    store: MemoryStoreProtocol,
    session_keywords: set[str] | None = None,
    archive_threshold: float = _ARCHIVE_THRESHOLD,
    embedding_provider: Any | None = None,
) -> LightweightConsolidationResult:
    """Run a lightweight consolidation pass (no LLM required).

    Four phases:

    1. **Decay sweep** — Apply the forgetting curve.  Archive memories
       whose effective strength falls below *archive_threshold*.
    2. **Reinforce** — Strengthen memories whose content matches any
       of the *session_keywords* (e.g. tool names, mission words).
    3. **Associate (embedding)** — When an embedding provider is available,
       build associations based on cosine similarity between memory contents.
    4. **Associate (tag fallback)** — For memories without embeddings,
       fall back to tag-overlap heuristic.

    Args:
        store: Memory store to operate on.
        session_keywords: Keywords from the just-completed session.
            Used to selectively reinforce related memories.
        archive_threshold: Effective strength below which memories
            are archived.
        embedding_provider: Optional ``EmbeddingProviderProtocol`` for
            semantic association discovery.

    Returns:
        Result summary with counts of each operation.
    """
    start = datetime.now(UTC)
    result = LightweightConsolidationResult()
    all_records = await store.list()
    now = datetime.now(UTC)

    # Phase 1: Decay sweep
    for record in all_records:
        if "archived" in record.tags:
            continue
        eff = record.effective_strength(now)
        if eff < archive_threshold:
            record.tags.append("archived")
            record.strength = eff
            await store.update(record)
            result.archived += 1
        elif eff < record.strength * 0.9:
            record.strength = eff
            await store.update(record)
            result.decayed += 1

    # Phase 2: Reinforce session-related memories
    if session_keywords:
        kw_lower = {kw.lower() for kw in session_keywords if len(kw) > 2}
        for record in all_records:
            if "archived" in record.tags:
                continue
            haystack = f"{record.content} {' '.join(record.tags)}".lower()
            overlap = sum(1 for kw in kw_lower if kw in haystack)
            if overlap >= 2:
                record.reinforce(now)
                await store.update(record)
                result.strengthened += 1

    # Phase 3: Build associations
    active = [r for r in all_records if "archived" not in r.tags]

    if embedding_provider and len(active) >= 2:
        result.associations_created += await _build_embedding_associations(
            active, embedding_provider, store
        )
    else:
        result.associations_created += _build_tag_associations(active)

    # Persist association updates
    for rec in active:
        if rec.associations:
            await store.update(rec)

    elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
    result.duration_ms = int(elapsed)

    logger.info(
        "lightweight_consolidation.complete",
        decayed=result.decayed,
        archived=result.archived,
        strengthened=result.strengthened,
        associations=result.associations_created,
        duration_ms=result.duration_ms,
    )
    return result


async def _build_embedding_associations(
    active: list[Any],
    embedding_provider: Any,
    store: MemoryStoreProtocol,
) -> int:
    """Build associations using cosine similarity between embeddings.

    Falls back to tag-based association for any records where embedding
    fails.
    """
    from taskforce.infrastructure.llm.embedding_service import cosine_similarity

    texts = [r.content for r in active]
    associations_created = 0

    try:
        vectors = await embedding_provider.embed_batch(texts)
    except Exception:
        logger.warning("lightweight_consolidation.embedding_failed_fallback_to_tags")
        return _build_tag_associations(active)

    for i, rec_a in enumerate(active):
        for j in range(i + 1, len(active)):
            rec_b = active[j]
            if (
                rec_b.id in rec_a.associations
                or len(rec_a.associations) >= _MAX_ASSOCIATIONS
                or len(rec_b.associations) >= _MAX_ASSOCIATIONS
            ):
                continue

            sim = cosine_similarity(vectors[i], vectors[j])
            if sim >= _EMBEDDING_SIMILARITY_THRESHOLD:
                rec_a.associate_with(rec_b.id)
                rec_b.associate_with(rec_a.id)
                associations_created += 1

    return associations_created


def _build_tag_associations(active: list[Any]) -> int:
    """Build associations based on shared tags (fallback)."""
    associations_created = 0
    tag_records = [r for r in active if r.tags]
    for i, rec_a in enumerate(tag_records):
        tags_a = set(rec_a.tags)
        for rec_b in tag_records[i + 1 :]:
            shared = tags_a & set(rec_b.tags)
            if len(shared) >= _MIN_TAG_OVERLAP:
                if (
                    rec_b.id not in rec_a.associations
                    and len(rec_a.associations) < _MAX_ASSOCIATIONS
                    and len(rec_b.associations) < _MAX_ASSOCIATIONS
                ):
                    rec_a.associate_with(rec_b.id)
                    rec_b.associate_with(rec_a.id)
                    associations_created += 1
    return associations_created
