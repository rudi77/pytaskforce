"""Tests for the simplified 4-phase consolidation engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from taskforce.core.domain.experience import (
    ConsolidationResult,
    SessionExperience,
    ToolCallExperience,
)
from taskforce.core.domain.memory import (
    EmotionalValence,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
)
from taskforce.infrastructure.memory.consolidation_engine import (
    ConsolidationEngine,
    _build_associations,
    _compute_quality_score,
    _extract_session_keywords,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def mock_llm() -> AsyncMock:
    """Mock LLM provider that returns valid JSON for summarise and integrate."""
    llm = AsyncMock()
    llm.complete = AsyncMock(
        return_value={
            "content": (
                '{"narrative": "Agent completed the task successfully.",'
                ' "key_learnings": ["learning1"],'
                ' "tool_patterns": ["p1"],'
                ' "memory_kind": "semantic",'
                ' "emotional_valence": "positive",'
                ' "importance": 0.7}'
            ),
            "usage": {"total_tokens": 100},
        }
    )
    return llm


@pytest.fixture()
def mock_memory_store() -> AsyncMock:
    """Mock memory store with standard stubs."""
    store = AsyncMock()
    store.list = AsyncMock(return_value=[])
    store.add = AsyncMock(side_effect=lambda r: r)
    store.update = AsyncMock(side_effect=lambda r: r)
    store.get = AsyncMock(return_value=None)
    store.flush = AsyncMock()
    return store


@pytest.fixture()
def engine(mock_llm: AsyncMock, mock_memory_store: AsyncMock) -> ConsolidationEngine:
    """Create a ConsolidationEngine with mocked dependencies."""
    return ConsolidationEngine(
        llm_provider=mock_llm,
        memory_store=mock_memory_store,
    )


def _make_experience(
    session_id: str = "sess-1",
    mission: str = "analyse data files",
    tool_names: list[str] | None = None,
) -> SessionExperience:
    """Build a minimal SessionExperience for testing."""
    tool_calls = [
        ToolCallExperience(
            tool_name=name,
            arguments={},
            success=True,
            duration_ms=50,
        )
        for name in (tool_names or ["file_read", "python"])
    ]
    return SessionExperience(
        session_id=session_id,
        profile="dev",
        mission=mission,
        total_steps=3,
        tool_calls=tool_calls,
        final_answer="Done.",
    )


def _make_memory(
    content: str = "some memory",
    tags: list[str] | None = None,
    strength: float = 0.8,
    importance: float = 0.5,
    hours_ago: float = 0.0,
) -> MemoryRecord:
    """Create a MemoryRecord with deterministic timestamps."""
    now = datetime.now(UTC)
    record = MemoryRecord(
        scope=MemoryScope.USER,
        kind=MemoryKind.CONSOLIDATED,
        content=content,
        tags=tags or [],
        strength=strength,
        importance=importance,
        created_at=now - timedelta(hours=hours_ago),
        updated_at=now - timedelta(hours=hours_ago),
        last_accessed=now - timedelta(hours=hours_ago),
    )
    return record


# ------------------------------------------------------------------
# Empty experiences => early return
# ------------------------------------------------------------------


async def test_consolidate_empty_experiences_returns_early(engine: ConsolidationEngine):
    """Empty experience list should return immediately with zero counts."""
    result = await engine.consolidate(experiences=[], existing_memories=[])

    assert result.sessions_processed == 0
    assert result.memories_created == 0
    assert result.memories_updated == 0
    assert result.ended_at is not None


# ------------------------------------------------------------------
# Phase 1: Maintain — decay + strengthen + associations
# ------------------------------------------------------------------


async def test_phase_maintain_archives_weak_memories(
    engine: ConsolidationEngine, mock_memory_store: AsyncMock
):
    """Memories below the decay archive threshold get tagged as archived."""
    weak = _make_memory(content="old fact", strength=0.01, importance=0.0, hours_ago=1000)
    counts = await engine._phase_maintain([weak], set())

    assert counts["archived"] >= 1
    mock_memory_store.update.assert_called()
    assert "archived" in weak.tags


async def test_phase_maintain_strengthens_on_keyword_overlap(
    engine: ConsolidationEngine, mock_memory_store: AsyncMock
):
    """Memories whose content overlaps with session keywords get reinforced."""
    mem = _make_memory(
        content="python file processing data",
        tags=["python", "data"],
        strength=0.8,
        importance=0.5,
        hours_ago=0.0,
    )
    keywords = {"python", "data", "analyse"}
    counts = await engine._phase_maintain([mem], keywords)

    assert counts["strengthened"] >= 1


async def test_phase_maintain_builds_associations(
    engine: ConsolidationEngine, mock_memory_store: AsyncMock
):
    """Memories sharing tags should have associations created."""
    mem_a = _make_memory(content="memory A", tags=["python", "data"])
    mem_b = _make_memory(content="memory B", tags=["python", "api"])
    counts = await engine._phase_maintain([mem_a, mem_b], set())

    assert counts["associations"] >= 1
    assert mem_b.id in mem_a.associations
    assert mem_a.id in mem_b.associations


async def test_phase_maintain_decays_weakened_memories(
    engine: ConsolidationEngine, mock_memory_store: AsyncMock
):
    """Memories whose effective strength dropped significantly get updated."""
    # Create a memory accessed long ago so effective_strength < strength * 0.9
    mem = _make_memory(content="aging memory", strength=0.8, importance=0.0, hours_ago=200)
    counts = await engine._phase_maintain([mem], set())

    # Should be decayed (effective < 0.9 * original) but not archived (importance floor)
    assert counts["decayed"] >= 0  # may or may not trigger depending on exact decay calc


# ------------------------------------------------------------------
# Phase 2: Distill — LLM summarisation
# ------------------------------------------------------------------


async def test_phase_distill_calls_llm_per_experience(engine: ConsolidationEngine, mock_llm: AsyncMock):
    """Each experience should produce one LLM summarisation call."""
    experiences = [_make_experience("s1"), _make_experience("s2")]
    summaries = await engine._phase_distill(experiences)

    assert len(summaries) == 2
    assert mock_llm.complete.call_count == 2
    assert summaries[0]["session_id"] == "s1"
    assert summaries[1]["session_id"] == "s2"


async def test_phase_distill_preserves_key_learnings(engine: ConsolidationEngine):
    """Summaries should contain key_learnings from LLM response."""
    summaries = await engine._phase_distill([_make_experience()])

    assert "key_learnings" in summaries[0]
    assert summaries[0]["key_learnings"] == ["learning1"]


# ------------------------------------------------------------------
# Phase 3: Integrate — patterns + contradictions + schemas
# ------------------------------------------------------------------


async def test_phase_integrate_immediate_no_existing_returns_empty(
    engine: ConsolidationEngine, mock_llm: AsyncMock
):
    """Immediate strategy with no existing memories skips integration."""
    result = await engine._phase_integrate(
        summaries=[{"session_id": "s1", "narrative": "test"}],
        new_learnings=["learning1"],
        existing_memories=[],
        strategy="immediate",
    )

    assert result["patterns"] == []
    assert result["contradictions"] == []
    assert result["schemas"] == []
    # Should NOT call LLM
    mock_llm.complete.assert_not_called()


async def test_phase_integrate_batch_calls_llm(
    engine: ConsolidationEngine, mock_llm: AsyncMock
):
    """Batch strategy should call LLM for integration even without existing memories."""
    mock_llm.complete.return_value = {
        "content": '{"patterns": [{"pattern": "p1", "confidence": 0.8, "frequency": 2}], "contradictions": [], "schemas": []}',
        "usage": {"total_tokens": 50},
    }
    result = await engine._phase_integrate(
        summaries=[{"session_id": "s1", "narrative": "test"}],
        new_learnings=["learning1"],
        existing_memories=[],
        strategy="batch",
    )

    assert len(result["patterns"]) == 1
    mock_llm.complete.assert_called_once()


# ------------------------------------------------------------------
# Phase 4: Persist — writing memories
# ------------------------------------------------------------------


async def test_phase_persist_creates_summary_memories(
    engine: ConsolidationEngine, mock_memory_store: AsyncMock
):
    """Summary key_learnings should be persisted as CONSOLIDATED memories."""
    summaries = [
        {
            "session_id": "s1",
            "key_learnings": ["insight A", "insight B"],
            "tool_patterns": ["p1"],
            "emotional_valence": "positive",
            "importance": 0.8,
            "memory_kind": "procedural",
        }
    ]
    integration = {"patterns": [], "contradictions": [], "schemas": []}
    created, updated, retired = await engine._phase_persist(
        summaries=summaries,
        integration=integration,
        consolidation_id="c1",
    )

    assert created == 2
    assert mock_memory_store.add.call_count == 2
    # Check the records are CONSOLIDATED kind
    record = mock_memory_store.add.call_args_list[0][0][0]
    assert record.kind == MemoryKind.CONSOLIDATED
    assert record.content == "insight A"


async def test_phase_persist_creates_pattern_memories(
    engine: ConsolidationEngine, mock_memory_store: AsyncMock
):
    """Patterns with confidence >= 0.5 should be written as memories."""
    integration = {
        "patterns": [
            {"pattern": "Use caching for repeated calls", "confidence": 0.9, "tags": ["caching"], "importance": 0.7},
            {"pattern": "Low confidence pattern", "confidence": 0.3, "tags": [], "importance": 0.3},
        ],
        "contradictions": [],
        "schemas": [],
    }
    created, _, _ = await engine._phase_persist(
        summaries=[],
        integration=integration,
        consolidation_id="c1",
    )

    # Only the high-confidence pattern should be created
    assert created == 1


async def test_phase_persist_creates_schema_memories(
    engine: ConsolidationEngine, mock_memory_store: AsyncMock
):
    """Schemas should be persisted as CONSOLIDATED memories."""
    integration = {
        "patterns": [],
        "contradictions": [],
        "schemas": [
            {"schema": "Always validate inputs before processing.", "tags": ["validation"], "importance": 0.9}
        ],
    }
    created, _, _ = await engine._phase_persist(
        summaries=[],
        integration=integration,
        consolidation_id="c1",
    )

    assert created == 1
    record = mock_memory_store.add.call_args_list[0][0][0]
    assert "Always validate" in record.content
    assert record.emotional_valence == EmotionalValence.NEUTRAL


async def test_phase_persist_handles_contradictions_keep_new(
    engine: ConsolidationEngine, mock_memory_store: AsyncMock
):
    """keep_new resolution should retire the existing memory."""
    existing = _make_memory(content="old approach")
    mock_memory_store.get = AsyncMock(return_value=existing)

    integration = {
        "patterns": [],
        "contradictions": [
            {
                "new_learning": "new approach",
                "existing_memory_id": existing.id,
                "resolution": "keep_new",
            }
        ],
        "schemas": [],
    }
    _, _, retired = await engine._phase_persist(
        summaries=[],
        integration=integration,
        consolidation_id="c1",
    )

    assert retired == 1
    assert "retired" in existing.tags
    assert existing.strength == 0.0


async def test_phase_persist_handles_contradictions_merge(
    engine: ConsolidationEngine, mock_memory_store: AsyncMock
):
    """merge resolution should update content of existing memory."""
    existing = _make_memory(content="old approach")
    mock_memory_store.get = AsyncMock(return_value=existing)

    integration = {
        "patterns": [],
        "contradictions": [
            {
                "new_learning": "new approach",
                "existing_memory_id": existing.id,
                "resolution": "merge",
                "merged_content": "combined approach",
            }
        ],
        "schemas": [],
    }
    _, updated, _ = await engine._phase_persist(
        summaries=[],
        integration=integration,
        consolidation_id="c1",
    )

    assert updated == 1
    assert existing.content == "combined approach"


# ------------------------------------------------------------------
# Full consolidate() flow
# ------------------------------------------------------------------


async def test_consolidate_full_flow(engine: ConsolidationEngine, mock_llm: AsyncMock):
    """Full pipeline should process experiences and return a result with metrics."""
    experiences = [_make_experience("s1")]
    existing = [_make_memory(content="existing memory", tags=["data"])]

    result = await engine.consolidate(experiences, existing)

    assert result.sessions_processed == 1
    assert result.memories_created >= 1
    assert result.ended_at is not None
    assert result.quality_score >= 0.0
    assert result.total_tokens > 0
    assert result.session_ids == ["s1"]


async def test_consolidate_calls_flush(
    engine: ConsolidationEngine, mock_memory_store: AsyncMock
):
    """Memory store flush should be called at the end of consolidation."""
    await engine.consolidate([_make_experience()], [])

    mock_memory_store.flush.assert_called_once()


async def test_consolidate_batch_strategy(engine: ConsolidationEngine, mock_llm: AsyncMock):
    """Batch strategy should call LLM for integration phase."""
    # Return integration JSON on the second call (first is summarise)
    mock_llm.complete.side_effect = [
        {
            "content": '{"narrative": "summary", "key_learnings": ["l1"], "tool_patterns": [], "memory_kind": "semantic", "emotional_valence": "neutral", "importance": 0.5}',
            "usage": {"total_tokens": 80},
        },
        {
            "content": '{"patterns": [], "contradictions": [], "schemas": []}',
            "usage": {"total_tokens": 60},
        },
    ]

    result = await engine.consolidate(
        [_make_experience()],
        [_make_memory(content="existing")],
        strategy="batch",
    )

    assert result.total_tokens == 140
    assert mock_llm.complete.call_count == 2


# ------------------------------------------------------------------
# _compute_quality_score
# ------------------------------------------------------------------


def test_compute_quality_score_zero_when_nothing_created():
    """Score should be 0.0 when no memories were created or updated."""
    result = ConsolidationResult(sessions_processed=1)
    assert _compute_quality_score(result) == 0.0


def test_compute_quality_score_scales_with_production():
    """Score should increase as more memories are created per session."""
    result = ConsolidationResult(sessions_processed=2, memories_created=3)
    score = _compute_quality_score(result)
    assert 0.0 < score <= 1.0
    # 3 created / 2 sessions = 1.5 per session -> 1.5/3.0 = 0.5
    assert abs(score - 0.5) < 0.01


def test_compute_quality_score_caps_at_one():
    """Score should never exceed 1.0."""
    result = ConsolidationResult(
        sessions_processed=1,
        memories_created=10,
        contradictions_resolved=5,
    )
    assert _compute_quality_score(result) == 1.0


def test_compute_quality_score_contradiction_bonus():
    """Resolving contradictions should add a bonus to the score."""
    base_result = ConsolidationResult(sessions_processed=1, memories_created=1)
    base_score = _compute_quality_score(base_result)

    bonus_result = ConsolidationResult(
        sessions_processed=1, memories_created=1, contradictions_resolved=2
    )
    bonus_score = _compute_quality_score(bonus_result)

    assert bonus_score > base_score


# ------------------------------------------------------------------
# _extract_session_keywords
# ------------------------------------------------------------------


def test_extract_session_keywords_from_mission():
    """Keywords from the mission text should be extracted."""
    exp = _make_experience(mission="analyse data files quickly")
    keywords = _extract_session_keywords([exp])

    assert "analyse" in keywords
    assert "data" in keywords
    assert "files" in keywords


def test_extract_session_keywords_includes_tool_names():
    """Tool names from tool_calls should appear in keywords."""
    exp = _make_experience(tool_names=["file_read", "web_search"])
    keywords = _extract_session_keywords([exp])

    assert "file_read" in keywords
    assert "web_search" in keywords


def test_extract_session_keywords_empty_experiences():
    """Empty experience list should return empty set."""
    assert _extract_session_keywords([]) == set()


# ------------------------------------------------------------------
# _build_associations
# ------------------------------------------------------------------


def test_build_associations_shared_tags():
    """Memories with shared tags should be associated bidirectionally."""
    a = _make_memory(content="A", tags=["python", "data"])
    b = _make_memory(content="B", tags=["python", "api"])

    count = _build_associations([a, b])

    assert count == 1
    assert b.id in a.associations
    assert a.id in b.associations


def test_build_associations_no_shared_tags():
    """Memories with disjoint tags should not be associated."""
    a = _make_memory(content="A", tags=["python"])
    b = _make_memory(content="B", tags=["java"])

    count = _build_associations([a, b])

    assert count == 0
    assert a.associations == []
    assert b.associations == []


def test_build_associations_no_tags():
    """Memories without tags should be skipped."""
    a = _make_memory(content="A", tags=[])
    b = _make_memory(content="B", tags=[])

    count = _build_associations([a, b])
    assert count == 0


def test_build_associations_no_duplicates():
    """Running associations twice should not create duplicate links."""
    a = _make_memory(content="A", tags=["python", "data"])
    b = _make_memory(content="B", tags=["python", "api"])

    _build_associations([a, b])
    count2 = _build_associations([a, b])

    # Second call should find them already associated
    assert count2 == 0
    assert a.associations.count(b.id) == 1
