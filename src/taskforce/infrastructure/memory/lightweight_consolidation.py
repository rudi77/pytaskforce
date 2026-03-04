"""Lightweight memory consolidation without LLM calls.

Runs the purely algorithmic phases of the sleep-cycle consolidation:
decay, reinforcement, and association building.  This is cheap enough
to run after every session, while the full LLM-powered pipeline
(``ConsolidationEngine``) should be scheduled periodically.

Usage::

    from taskforce.infrastructure.memory.lightweight_consolidation import (
        run_lightweight_consolidation,
    )

    result = await run_lightweight_consolidation(memory_store, session_keywords)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import structlog

from taskforce.core.interfaces.memory_store import MemoryStoreProtocol

logger = structlog.get_logger(__name__)

# Default threshold below which memories are archived.
_ARCHIVE_THRESHOLD: float = 0.10

# Minimum tag overlap for automatic association.
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
) -> LightweightConsolidationResult:
    """Run a lightweight consolidation pass (no LLM required).

    Three phases:

    1. **Decay sweep** — Apply the forgetting curve.  Archive memories
       whose effective strength falls below *archive_threshold*.
    2. **Reinforce** — Strengthen memories whose content matches any
       of the *session_keywords* (e.g. tool names, mission words).
    3. **Associate** — Build bidirectional links between non-archived
       memories that share tags.

    Args:
        store: Memory store to operate on.
        session_keywords: Keywords from the just-completed session.
            Used to selectively reinforce related memories.
        archive_threshold: Effective strength below which memories
            are archived.

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
    active = [r for r in all_records if "archived" not in r.tags and r.tags]
    for i, rec_a in enumerate(active):
        tags_a = set(rec_a.tags)
        for rec_b in active[i + 1 :]:
            shared = tags_a & set(rec_b.tags)
            if len(shared) >= _MIN_TAG_OVERLAP:
                if (
                    rec_b.id not in rec_a.associations
                    and len(rec_a.associations) < _MAX_ASSOCIATIONS
                    and len(rec_b.associations) < _MAX_ASSOCIATIONS
                ):
                    rec_a.associate_with(rec_b.id)
                    rec_b.associate_with(rec_a.id)
                    result.associations_created += 1

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
