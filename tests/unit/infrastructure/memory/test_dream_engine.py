"""Tests for DreamEngine."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from taskforce.core.domain.dream import (
    DreamConfig,
    DreamInsightType,
    DreamPhase,
    DreamStatus,
)
from taskforce.core.domain.memory import (
    EmotionalValence,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
)
from taskforce.infrastructure.memory.dream_engine import (
    DreamEngine,
    _dampen_emotional_valence,
    _parse_insights,
    _select_distant_pairs,
    _select_strongest,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


def _make_memory(
    content: str = "test memory",
    *,
    id: str | None = None,
    tags: list[str] | None = None,
    strength: float = 0.8,
    emotional_valence: EmotionalValence = EmotionalValence.NEUTRAL,
    importance: float = 0.5,
    metadata: dict | None = None,
) -> MemoryRecord:
    """Create a MemoryRecord with explicit strength (bypassing sentinel logic)."""
    rec = MemoryRecord(
        scope=MemoryScope.USER,
        kind=MemoryKind.LONG_TERM,
        content=content,
        tags=tags or [],
        strength=strength,
        emotional_valence=emotional_valence,
        importance=importance,
        metadata=metadata or {},
    )
    if id is not None:
        rec.id = id
    return rec


def _llm_response(items: list[dict], tokens: int = 100) -> dict:
    """Build a mock LLM response that call_llm_json will parse."""
    return {
        "content": json.dumps(items),
        "usage": {"total_tokens": tokens},
    }


@pytest.fixture
def mock_llm():
    """Mock LLM provider returning valid JSON insight arrays."""
    llm = AsyncMock()
    default_items = [
        {
            "content": "insight text",
            "source_ids": ["abc"],
            "confidence": 0.8,
            "tags": ["test"],
        }
    ]
    llm.complete = AsyncMock(return_value=_llm_response(default_items))
    return llm


@pytest.fixture
def mock_memory_store():
    """Mock memory store."""
    store = AsyncMock()
    store.update = AsyncMock(side_effect=lambda r: r)
    store.add = AsyncMock(side_effect=lambda r: r)
    store.get = AsyncMock(return_value=None)
    store.list = AsyncMock(return_value=[])
    return store


@pytest.fixture
def engine(mock_llm, mock_memory_store):
    """DreamEngine wired with mock dependencies."""
    return DreamEngine(mock_llm, mock_memory_store)


@pytest.fixture
def default_config() -> DreamConfig:
    """Default dream config with all 4 phases enabled."""
    return DreamConfig(
        enabled=True,
        max_llm_calls=4,
        replay_variations=3,
        recombination_pairs=2,
        novelty_threshold=0.0,  # Accept all insights for easier testing
    )


@pytest.fixture
def sample_memories() -> list[MemoryRecord]:
    """A set of memories suitable for all 4 phases."""
    return [
        _make_memory(
            "Learned to deploy via CI/CD pipeline",
            id="aaaa1111bbbb2222cccc3333dddd4444",
            tags=["deployment", "ci"],
            strength=0.9,
        ),
        _make_memory(
            "Discovered query optimization technique",
            id="eeee5555ffff6666aaaa7777bbbb8888",
            tags=["database", "performance"],
            strength=0.85,
        ),
        _make_memory(
            "Failed deployment caused frustration",
            id="cccc9999dddd0000eeee1111ffff2222",
            tags=["deployment", "error"],
            strength=0.7,
            emotional_valence=EmotionalValence.FRUSTRATION,
        ),
        _make_memory(
            "Pattern: repeated test failures indicate flaky tests",
            id="dddd3333eeee4444ffff5555aaaa6666",
            tags=["testing", "patterns"],
            strength=0.8,
            metadata={"source": "consolidation"},
        ),
    ]


# ------------------------------------------------------------------
# DreamEngine.dream() — full cycle with all 4 phases
# ------------------------------------------------------------------


class TestDreamFullCycle:
    """Test dream() with all 4 phases executing."""

    async def test_dream_all_phases_produces_insights(
        self, engine, mock_llm, sample_memories, default_config
    ):
        """With budget=4 and 4 phases, each phase should use 1 LLM call."""
        replay_items = [
            {
                "content": "replay insight",
                "source_ids": [sample_memories[0].id[:8]],
                "confidence": 0.7,
                "tags": ["replay"],
            }
        ]
        recomb_items = [
            {
                "content": "cross-domain insight",
                "source_ids": [
                    sample_memories[0].id[:8],
                    sample_memories[1].id[:8],
                ],
                "confidence": 0.8,
                "tags": ["cross"],
            }
        ]
        emotional_items = [
            {
                "content": "reframed frustration constructively",
                "source_id": sample_memories[2].id[:8],
                "tags": ["reframe"],
            }
        ]
        prediction_items = [
            {
                "content": "flaky tests may increase next quarter",
                "source_ids": [sample_memories[3].id[:8]],
                "confidence": 0.6,
                "tags": ["prediction"],
            }
        ]

        mock_llm.complete = AsyncMock(
            side_effect=[
                _llm_response(replay_items),
                _llm_response(recomb_items),
                _llm_response(emotional_items),
                _llm_response(prediction_items),
            ]
        )

        cycle = await engine.dream(sample_memories, default_config)

        assert cycle.status == DreamStatus.COMPLETED
        assert cycle.ended_at is not None
        assert cycle.memories_processed == len(sample_memories)
        # 4 LLM calls, one per phase
        assert mock_llm.complete.call_count == 4

        # Verify insight types present
        types = {i.insight_type for i in cycle.insights}
        assert DreamInsightType.VARIATION in types
        assert DreamInsightType.RECOMBINATION in types
        assert DreamInsightType.REAPPRAISAL in types
        assert DreamInsightType.PREDICTION in types

    async def test_dream_tokens_accumulated(
        self, engine, mock_llm, sample_memories, default_config
    ):
        """Total tokens should sum across all phases."""
        mock_llm.complete = AsyncMock(
            side_effect=[
                _llm_response([{"content": "a", "source_ids": [], "confidence": 0.5, "tags": []}], tokens=50),
                _llm_response([{"content": "b", "source_ids": [], "confidence": 0.5, "tags": []}], tokens=60),
                _llm_response([{"content": "c", "source_id": "", "tags": []}], tokens=70),
                _llm_response([{"content": "d", "source_ids": [], "confidence": 0.5, "tags": []}], tokens=80),
            ]
        )

        cycle = await engine.dream(sample_memories, default_config)
        assert cycle.total_tokens == 50 + 60 + 70 + 80

    async def test_dream_novelty_threshold_filters(
        self, engine, mock_llm, sample_memories
    ):
        """Insights below novelty_threshold should be filtered out."""
        config = DreamConfig(
            enabled=True,
            max_llm_calls=4,
            novelty_threshold=0.8,  # High threshold
            replay_variations=3,
            recombination_pairs=2,
        )

        items = [
            {"content": "insight", "source_ids": [], "confidence": 0.5, "tags": []}
        ]
        mock_llm.complete = AsyncMock(return_value=_llm_response(items))

        cycle = await engine.dream(sample_memories, config)

        assert cycle.status == DreamStatus.COMPLETED
        # Default novelty_score=0.5 < threshold 0.8 → all filtered
        assert len(cycle.insights) == 0

    async def test_dream_handles_llm_returning_invalid_json(
        self, engine, mock_llm, sample_memories, default_config
    ):
        """When LLM returns unparseable JSON, phases produce no insights but cycle completes."""
        mock_llm.complete = AsyncMock(
            return_value={"content": "not json at all", "usage": {"total_tokens": 10}}
        )

        cycle = await engine.dream(sample_memories, default_config)

        # call_llm_json handles errors gracefully — cycle still completes
        assert cycle.status == DreamStatus.COMPLETED
        assert cycle.ended_at is not None
        # No insights parsed from garbage output
        assert len(cycle.insights) == 0


# ------------------------------------------------------------------
# Budget enforcement
# ------------------------------------------------------------------


class TestBudgetEnforcement:
    """Test that max_llm_calls limits the number of LLM calls made."""

    async def test_budget_of_two_only_runs_two_llm_phases(
        self, engine, mock_llm, sample_memories
    ):
        """With budget=2, only first 2 LLM-consuming phases should call LLM."""
        config = DreamConfig(
            enabled=True,
            max_llm_calls=2,
            novelty_threshold=0.0,
            replay_variations=3,
            recombination_pairs=2,
        )

        items = [
            {"content": "insight", "source_ids": [], "confidence": 0.5, "tags": []}
        ]
        mock_llm.complete = AsyncMock(return_value=_llm_response(items))

        cycle = await engine.dream(sample_memories, config)

        assert cycle.status == DreamStatus.COMPLETED
        # Replay (1 call) + Recombination (1 call) = 2, then budget exhausted
        # Emotional processing runs algorithmic dampening but no LLM call
        # Prediction is skipped (budget=0)
        assert mock_llm.complete.call_count == 2

    async def test_budget_of_one_only_runs_one_llm_phase(
        self, engine, mock_llm, sample_memories
    ):
        """With budget=1, only replay phase should call LLM."""
        config = DreamConfig(
            enabled=True,
            max_llm_calls=1,
            novelty_threshold=0.0,
            replay_variations=3,
            recombination_pairs=2,
        )

        items = [
            {"content": "insight", "source_ids": [], "confidence": 0.5, "tags": []}
        ]
        mock_llm.complete = AsyncMock(return_value=_llm_response(items))

        cycle = await engine.dream(sample_memories, config)

        assert cycle.status == DreamStatus.COMPLETED
        assert mock_llm.complete.call_count == 1


# ------------------------------------------------------------------
# Phase skipping when budget=0
# ------------------------------------------------------------------


class TestZeroBudget:
    """When budget=0, LLM-dependent phases produce no insights."""

    async def test_zero_budget_no_llm_calls(
        self, engine, mock_llm, sample_memories
    ):
        """With budget=0, no LLM calls should be made at all."""
        config = DreamConfig(
            enabled=True,
            max_llm_calls=0,
            novelty_threshold=0.0,
            replay_variations=3,
            recombination_pairs=2,
        )

        cycle = await engine.dream(sample_memories, config)

        assert cycle.status == DreamStatus.COMPLETED
        mock_llm.complete.assert_not_awaited()
        # No LLM insights, but emotional dampening still runs
        assert all(
            i.insight_type != DreamInsightType.VARIATION for i in cycle.insights
        )
        assert all(
            i.insight_type != DreamInsightType.PREDICTION for i in cycle.insights
        )

    async def test_zero_budget_emotional_dampening_still_runs(
        self, engine, mock_llm, mock_memory_store, sample_memories
    ):
        """Even with zero budget, algorithmic dampening updates memories."""
        config = DreamConfig(
            enabled=True,
            max_llm_calls=0,
            novelty_threshold=0.0,
            emotional_decay_factor=0.15,
        )

        frustration_mem = sample_memories[2]
        assert frustration_mem.emotional_valence == EmotionalValence.FRUSTRATION

        await engine.dream(sample_memories, config)

        # Emotional dampening should have updated the frustration memory
        mock_memory_store.update.assert_awaited()
        # Frustration should have been shifted to NEGATIVE
        assert frustration_mem.emotional_valence == EmotionalValence.NEGATIVE


# ------------------------------------------------------------------
# _select_strongest helper
# ------------------------------------------------------------------


class TestSelectStrongest:
    def test_picks_highest_effective_strength(self):
        """Should return memories sorted by effective_strength descending."""
        weak = _make_memory("weak", strength=0.2, importance=0.1)
        medium = _make_memory("medium", strength=0.5, importance=0.1)
        strong = _make_memory("strong", strength=0.9, importance=0.1)

        result = _select_strongest([weak, medium, strong], count=2)

        assert len(result) == 2
        assert result[0].content == "strong"
        assert result[1].content == "medium"

    def test_excludes_archived(self):
        """Memories tagged 'archived' should be excluded."""
        active = _make_memory("active", strength=0.9)
        archived = _make_memory("archived", strength=0.95, tags=["archived"])

        result = _select_strongest([active, archived], count=5)

        assert len(result) == 1
        assert result[0].content == "active"

    def test_returns_empty_on_empty_input(self):
        assert _select_strongest([], count=3) == []

    def test_count_exceeds_available(self):
        """When count > available memories, return all."""
        m1 = _make_memory("one", strength=0.9)
        m2 = _make_memory("two", strength=0.8)

        result = _select_strongest([m1, m2], count=10)

        assert len(result) == 2


# ------------------------------------------------------------------
# _select_distant_pairs helper
# ------------------------------------------------------------------


class TestSelectDistantPairs:
    def test_picks_least_tag_overlap(self):
        """Pairs with zero shared tags should be preferred."""
        m_deploy = _make_memory("deploy", tags=["deployment", "ci"])
        m_db = _make_memory("database", tags=["database", "sql"])
        m_deploy2 = _make_memory("deploy2", tags=["deployment", "docker"])

        pairs = _select_distant_pairs([m_deploy, m_db, m_deploy2], count=1)

        assert len(pairs) == 1
        pair_contents = {pairs[0][0].content, pairs[0][1].content}
        # deploy+db or deploy2+db have zero overlap → preferred over deploy+deploy2
        assert "database" in pair_contents

    def test_returns_empty_with_fewer_than_two_memories(self):
        single = _make_memory("only one", tags=["tag"])
        assert _select_distant_pairs([single], count=1) == []
        assert _select_distant_pairs([], count=1) == []

    def test_excludes_archived(self):
        m1 = _make_memory("active1", tags=["a"])
        m2 = _make_memory("active2", tags=["b"])
        m3 = _make_memory("archived", tags=["c", "archived"])

        pairs = _select_distant_pairs([m1, m2, m3], count=2)

        all_mems_in_pairs = {m.content for p in pairs for m in p}
        assert "archived" not in all_mems_in_pairs

    def test_excludes_tagless_memories(self):
        """Memories with no tags should be excluded."""
        m_no_tags = _make_memory("no tags", tags=[])
        m_tagged = _make_memory("tagged", tags=["a"])

        pairs = _select_distant_pairs([m_no_tags, m_tagged], count=1)
        assert pairs == []

    def test_no_duplicate_indices_in_pairs(self):
        """Each memory should appear in at most one pair."""
        mems = [
            _make_memory(f"mem{i}", tags=[f"tag{i}"]) for i in range(6)
        ]

        pairs = _select_distant_pairs(mems, count=3)

        used_ids = []
        for a, b in pairs:
            used_ids.append(a.id)
            used_ids.append(b.id)
        assert len(used_ids) == len(set(used_ids))


# ------------------------------------------------------------------
# _parse_insights helper
# ------------------------------------------------------------------


class TestParseInsights:
    def test_converts_raw_items_to_dream_insights(self):
        mem = _make_memory("test", id="aaaa1111bbbb2222cccc3333dddd4444")
        raw = [
            {
                "content": "an insight",
                "source_ids": [mem.id[:8]],
                "confidence": 0.9,
                "tags": ["tag1", "tag2"],
            }
        ]

        insights = _parse_insights(raw, DreamInsightType.VARIATION, [mem])

        assert len(insights) == 1
        assert insights[0].content == "an insight"
        assert insights[0].confidence == 0.9
        assert insights[0].insight_type == DreamInsightType.VARIATION
        assert insights[0].tags == ["tag1", "tag2"]
        # Short ID should be resolved to full ID
        assert mem.id in insights[0].source_memory_ids

    def test_skips_items_without_content(self):
        raw = [
            {"source_ids": [], "confidence": 0.5, "tags": []},
            {"content": "", "source_ids": [], "confidence": 0.5, "tags": []},
            {"content": "valid", "source_ids": [], "confidence": 0.5, "tags": []},
        ]

        insights = _parse_insights(raw, DreamInsightType.PREDICTION, [])

        assert len(insights) == 1
        assert insights[0].content == "valid"

    def test_skips_non_dict_items(self):
        raw = ["not a dict", 42, None, {"content": "ok", "source_ids": []}]

        insights = _parse_insights(raw, DreamInsightType.RECOMBINATION, [])

        assert len(insights) == 1

    def test_default_confidence_when_missing(self):
        raw = [{"content": "no confidence field", "source_ids": []}]

        insights = _parse_insights(raw, DreamInsightType.VARIATION, [])

        assert insights[0].confidence == 0.5

    def test_tags_truncated_to_five(self):
        raw = [
            {
                "content": "many tags",
                "source_ids": [],
                "tags": ["a", "b", "c", "d", "e", "f", "g"],
            }
        ]

        insights = _parse_insights(raw, DreamInsightType.VARIATION, [])

        assert len(insights[0].tags) == 5

    def test_short_id_resolution(self):
        """Short (8-char) IDs from LLM output should map back to full UUIDs."""
        m1 = _make_memory("m1", id="11112222333344445555666677778888")
        m2 = _make_memory("m2", id="aaaabbbbccccddddeeeeffffaaaabbbb")

        raw = [
            {
                "content": "combined insight",
                "source_ids": ["11112222", "aaaabbbb"],
                "confidence": 0.7,
                "tags": [],
            }
        ]

        insights = _parse_insights(raw, DreamInsightType.RECOMBINATION, [m1, m2])

        assert m1.id in insights[0].source_memory_ids
        assert m2.id in insights[0].source_memory_ids


# ------------------------------------------------------------------
# _dampen_emotional_valence helper
# ------------------------------------------------------------------


class TestDampenEmotionalValence:
    def test_frustration_to_negative(self):
        """FRUSTRATION should shift to NEGATIVE after one dampening pass."""
        mem = _make_memory(
            "frustrating event",
            emotional_valence=EmotionalValence.FRUSTRATION,
            strength=0.8,
        )

        _dampen_emotional_valence([mem], factor=0.15)

        assert mem.emotional_valence == EmotionalValence.NEGATIVE

    def test_negative_to_neutral(self):
        """NEGATIVE should shift to NEUTRAL after one dampening pass."""
        mem = _make_memory(
            "bad event",
            emotional_valence=EmotionalValence.NEGATIVE,
            strength=0.8,
        )

        _dampen_emotional_valence([mem], factor=0.15)

        assert mem.emotional_valence == EmotionalValence.NEUTRAL

    def test_frustration_to_neutral_over_two_cycles(self):
        """FRUSTRATION -> NEGATIVE -> NEUTRAL over two dampening passes."""
        mem = _make_memory(
            "really bad event",
            emotional_valence=EmotionalValence.FRUSTRATION,
            strength=0.8,
        )

        _dampen_emotional_valence([mem], factor=0.15)
        assert mem.emotional_valence == EmotionalValence.NEGATIVE

        _dampen_emotional_valence([mem], factor=0.15)
        assert mem.emotional_valence == EmotionalValence.NEUTRAL

    def test_neutral_stays_neutral(self):
        """NEUTRAL should not change — no further dampening."""
        mem = _make_memory(
            "neutral event",
            emotional_valence=EmotionalValence.NEUTRAL,
            strength=0.8,
        )

        _dampen_emotional_valence([mem], factor=0.15)

        assert mem.emotional_valence == EmotionalValence.NEUTRAL

    def test_positive_stays_positive(self):
        """POSITIVE is not in the dampening map and should stay unchanged."""
        mem = _make_memory(
            "good event",
            emotional_valence=EmotionalValence.POSITIVE,
            strength=0.8,
        )

        _dampen_emotional_valence([mem], factor=0.15)

        assert mem.emotional_valence == EmotionalValence.POSITIVE

    def test_strength_reduced_by_factor(self):
        """Strength should be reduced by (1 - factor) with a floor of 0.1."""
        mem = _make_memory(
            "negative",
            emotional_valence=EmotionalValence.NEGATIVE,
            strength=0.8,
        )

        _dampen_emotional_valence([mem], factor=0.2)

        expected = 0.8 * (1.0 - 0.2)
        assert abs(mem.strength - expected) < 1e-9

    def test_strength_floor_at_0_1(self):
        """Strength should not drop below 0.1 even with extreme factor."""
        mem = _make_memory(
            "negative",
            emotional_valence=EmotionalValence.NEGATIVE,
            strength=0.15,
        )

        _dampen_emotional_valence([mem], factor=0.9)

        assert mem.strength == pytest.approx(0.1)

    def test_multiple_memories_dampened(self):
        """All memories in the list should be processed."""
        mems = [
            _make_memory("a", emotional_valence=EmotionalValence.FRUSTRATION, strength=0.8),
            _make_memory("b", emotional_valence=EmotionalValence.NEGATIVE, strength=0.6),
        ]

        _dampen_emotional_valence(mems, factor=0.15)

        assert mems[0].emotional_valence == EmotionalValence.NEGATIVE
        assert mems[1].emotional_valence == EmotionalValence.NEUTRAL
