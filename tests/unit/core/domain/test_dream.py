"""Tests for Dream domain models."""

from datetime import UTC, datetime

from taskforce.core.domain.dream import (
    DEFAULT_DREAM_PHASES,
    DreamConfig,
    DreamCycle,
    DreamInsight,
    DreamInsightType,
    DreamPhase,
    DreamStatus,
    DreamTrigger,
)
from taskforce.core.domain.memory import EmotionalValence


class TestDreamPhase:
    """Tests for DreamPhase enum."""

    def test_values(self) -> None:
        assert DreamPhase.REPLAY.value == "replay"
        assert DreamPhase.RECOMBINATION.value == "recombination"
        assert DreamPhase.EMOTIONAL_PROCESSING.value == "emotional_processing"
        assert DreamPhase.PREDICTION.value == "prediction"

    def test_all_members(self) -> None:
        assert len(DreamPhase) == 4


class TestDreamInsightType:
    """Tests for DreamInsightType enum."""

    def test_values(self) -> None:
        assert DreamInsightType.VARIATION.value == "variation"
        assert DreamInsightType.RECOMBINATION.value == "recombination"
        assert DreamInsightType.REAPPRAISAL.value == "reappraisal"
        assert DreamInsightType.PREDICTION.value == "prediction"


class TestDreamStatus:
    """Tests for DreamStatus enum."""

    def test_values(self) -> None:
        assert DreamStatus.RUNNING.value == "running"
        assert DreamStatus.COMPLETED.value == "completed"
        assert DreamStatus.FAILED.value == "failed"

    def test_all_members(self) -> None:
        assert len(DreamStatus) == 3


class TestDreamTrigger:
    """Tests for DreamTrigger enum."""

    def test_values(self) -> None:
        assert DreamTrigger.SCHEDULED.value == "scheduled"
        assert DreamTrigger.MANUAL.value == "manual"
        assert DreamTrigger.POST_CONSOLIDATION.value == "post_consolidation"

    def test_all_members(self) -> None:
        assert len(DreamTrigger) == 3


class TestDefaultDreamPhases:
    """Tests for DEFAULT_DREAM_PHASES constant."""

    def test_contains_all_phases_in_order(self) -> None:
        assert DEFAULT_DREAM_PHASES == [
            DreamPhase.REPLAY,
            DreamPhase.RECOMBINATION,
            DreamPhase.EMOTIONAL_PROCESSING,
            DreamPhase.PREDICTION,
        ]

    def test_length(self) -> None:
        assert len(DEFAULT_DREAM_PHASES) == 4


class TestDreamInsight:
    """Tests for DreamInsight dataclass."""

    def test_create_with_defaults(self) -> None:
        insight = DreamInsight(
            content="Test insight",
            source_memory_ids=["mem-1", "mem-2"],
            insight_type=DreamInsightType.VARIATION,
        )
        assert insight.content == "Test insight"
        assert insight.source_memory_ids == ["mem-1", "mem-2"]
        assert insight.insight_type == DreamInsightType.VARIATION
        assert insight.confidence == 0.5
        assert insight.novelty_score == 0.5
        assert insight.tags == []
        assert insight.emotional_valence == EmotionalValence.NEUTRAL

    def test_create_with_custom_values(self) -> None:
        insight = DreamInsight(
            content="Cross-domain pattern",
            source_memory_ids=["mem-a"],
            insight_type=DreamInsightType.RECOMBINATION,
            confidence=0.9,
            novelty_score=0.8,
            tags=["cross-domain", "pattern"],
            emotional_valence=EmotionalValence.POSITIVE,
        )
        assert insight.confidence == 0.9
        assert insight.novelty_score == 0.8
        assert insight.tags == ["cross-domain", "pattern"]
        assert insight.emotional_valence == EmotionalValence.POSITIVE

    def test_to_dict(self) -> None:
        insight = DreamInsight(
            content="Reappraised memory",
            source_memory_ids=["mem-x"],
            insight_type=DreamInsightType.REAPPRAISAL,
            confidence=0.7,
            novelty_score=0.6,
            tags=["emotional"],
            emotional_valence=EmotionalValence.NEGATIVE,
        )
        d = insight.to_dict()
        assert d["content"] == "Reappraised memory"
        assert d["source_memory_ids"] == ["mem-x"]
        assert d["insight_type"] == "reappraisal"
        assert d["confidence"] == 0.7
        assert d["novelty_score"] == 0.6
        assert d["tags"] == ["emotional"]
        assert d["emotional_valence"] == "negative"

    def test_from_dict(self) -> None:
        data = {
            "content": "Predicted outcome",
            "source_memory_ids": ["mem-1", "mem-2"],
            "insight_type": "prediction",
            "confidence": 0.85,
            "novelty_score": 0.9,
            "tags": ["forecast"],
            "emotional_valence": "positive",
        }
        insight = DreamInsight.from_dict(data)
        assert insight.content == "Predicted outcome"
        assert insight.source_memory_ids == ["mem-1", "mem-2"]
        assert insight.insight_type == DreamInsightType.PREDICTION
        assert insight.confidence == 0.85
        assert insight.novelty_score == 0.9
        assert insight.tags == ["forecast"]
        assert insight.emotional_valence == EmotionalValence.POSITIVE

    def test_from_dict_with_defaults(self) -> None:
        data = {"content": "Minimal insight"}
        insight = DreamInsight.from_dict(data)
        assert insight.content == "Minimal insight"
        assert insight.source_memory_ids == []
        assert insight.insight_type == DreamInsightType.VARIATION
        assert insight.confidence == 0.5
        assert insight.novelty_score == 0.5
        assert insight.tags == []
        assert insight.emotional_valence == EmotionalValence.NEUTRAL

    def test_roundtrip_to_dict_from_dict(self) -> None:
        original = DreamInsight(
            content="Roundtrip test",
            source_memory_ids=["m1", "m2", "m3"],
            insight_type=DreamInsightType.RECOMBINATION,
            confidence=0.75,
            novelty_score=0.65,
            tags=["test", "roundtrip"],
            emotional_valence=EmotionalValence.POSITIVE,
        )
        restored = DreamInsight.from_dict(original.to_dict())
        assert restored.content == original.content
        assert restored.source_memory_ids == original.source_memory_ids
        assert restored.insight_type == original.insight_type
        assert restored.confidence == original.confidence
        assert restored.novelty_score == original.novelty_score
        assert restored.tags == original.tags
        assert restored.emotional_valence == original.emotional_valence


class TestDreamCycle:
    """Tests for DreamCycle dataclass."""

    def test_create_with_defaults(self) -> None:
        cycle = DreamCycle()
        assert isinstance(cycle.dream_id, str)
        assert len(cycle.dream_id) > 0
        assert isinstance(cycle.started_at, datetime)
        assert cycle.ended_at is None
        assert cycle.status == DreamStatus.RUNNING
        assert cycle.insights == []
        assert cycle.memories_processed == 0
        assert cycle.memories_created == 0
        assert cycle.total_tokens == 0
        assert cycle.trigger == DreamTrigger.MANUAL

    def test_create_with_custom_values(self) -> None:
        now = datetime.now(UTC)
        insight = DreamInsight(
            content="An insight",
            source_memory_ids=["m1"],
            insight_type=DreamInsightType.VARIATION,
        )
        cycle = DreamCycle(
            dream_id="dream-42",
            started_at=now,
            ended_at=now,
            status=DreamStatus.COMPLETED,
            insights=[insight],
            memories_processed=10,
            memories_created=3,
            total_tokens=500,
            trigger=DreamTrigger.SCHEDULED,
        )
        assert cycle.dream_id == "dream-42"
        assert cycle.started_at == now
        assert cycle.ended_at == now
        assert cycle.status == DreamStatus.COMPLETED
        assert len(cycle.insights) == 1
        assert cycle.memories_processed == 10
        assert cycle.memories_created == 3
        assert cycle.total_tokens == 500
        assert cycle.trigger == DreamTrigger.SCHEDULED

    def test_to_dict(self) -> None:
        now = datetime(2026, 3, 25, 12, 0, 0, tzinfo=UTC)
        insight = DreamInsight(
            content="Test",
            source_memory_ids=["m1"],
            insight_type=DreamInsightType.PREDICTION,
        )
        cycle = DreamCycle(
            dream_id="d-1",
            started_at=now,
            ended_at=now,
            status=DreamStatus.COMPLETED,
            insights=[insight],
            memories_processed=5,
            memories_created=2,
            total_tokens=100,
            trigger=DreamTrigger.POST_CONSOLIDATION,
        )
        d = cycle.to_dict()
        assert d["dream_id"] == "d-1"
        assert d["started_at"] == now.isoformat()
        assert d["ended_at"] == now.isoformat()
        assert d["status"] == "completed"
        assert len(d["insights"]) == 1
        assert d["insights"][0]["content"] == "Test"
        assert d["memories_processed"] == 5
        assert d["memories_created"] == 2
        assert d["total_tokens"] == 100
        assert d["trigger"] == "post_consolidation"

    def test_to_dict_ended_at_none(self) -> None:
        cycle = DreamCycle(dream_id="d-2")
        d = cycle.to_dict()
        assert d["ended_at"] is None

    def test_from_dict(self) -> None:
        now_iso = "2026-03-25T12:00:00+00:00"
        data = {
            "dream_id": "d-abc",
            "started_at": now_iso,
            "ended_at": now_iso,
            "status": "failed",
            "insights": [
                {
                    "content": "Deserialized insight",
                    "source_memory_ids": ["m1"],
                    "insight_type": "variation",
                }
            ],
            "memories_processed": 7,
            "memories_created": 1,
            "total_tokens": 200,
            "trigger": "scheduled",
        }
        cycle = DreamCycle.from_dict(data)
        assert cycle.dream_id == "d-abc"
        assert cycle.started_at.isoformat() == now_iso
        assert cycle.ended_at is not None
        assert cycle.ended_at.isoformat() == now_iso
        assert cycle.status == DreamStatus.FAILED
        assert len(cycle.insights) == 1
        assert cycle.insights[0].content == "Deserialized insight"
        assert cycle.memories_processed == 7
        assert cycle.memories_created == 1
        assert cycle.total_tokens == 200
        assert cycle.trigger == DreamTrigger.SCHEDULED

    def test_from_dict_ended_at_none(self) -> None:
        data = {
            "dream_id": "d-none",
            "started_at": "2026-01-01T00:00:00+00:00",
        }
        cycle = DreamCycle.from_dict(data)
        assert cycle.ended_at is None

    def test_from_dict_empty_insights(self) -> None:
        data = {
            "started_at": "2026-01-01T00:00:00+00:00",
        }
        cycle = DreamCycle.from_dict(data)
        assert cycle.insights == []

    def test_roundtrip_to_dict_from_dict(self) -> None:
        now = datetime(2026, 3, 25, 15, 30, 0, tzinfo=UTC)
        insight = DreamInsight(
            content="Roundtrip cycle insight",
            source_memory_ids=["m1", "m2"],
            insight_type=DreamInsightType.RECOMBINATION,
            confidence=0.8,
            novelty_score=0.7,
            tags=["roundtrip"],
            emotional_valence=EmotionalValence.NEGATIVE,
        )
        original = DreamCycle(
            dream_id="rt-1",
            started_at=now,
            ended_at=now,
            status=DreamStatus.COMPLETED,
            insights=[insight],
            memories_processed=15,
            memories_created=4,
            total_tokens=350,
            trigger=DreamTrigger.POST_CONSOLIDATION,
        )
        restored = DreamCycle.from_dict(original.to_dict())
        assert restored.dream_id == original.dream_id
        assert restored.started_at == original.started_at
        assert restored.ended_at == original.ended_at
        assert restored.status == original.status
        assert len(restored.insights) == 1
        assert restored.insights[0].content == insight.content
        assert restored.insights[0].insight_type == insight.insight_type
        assert restored.memories_processed == original.memories_processed
        assert restored.memories_created == original.memories_created
        assert restored.total_tokens == original.total_tokens
        assert restored.trigger == original.trigger


class TestDreamConfig:
    """Tests for DreamConfig dataclass."""

    def test_defaults(self) -> None:
        config = DreamConfig()
        assert config.enabled is False
        assert config.phases == list(DEFAULT_DREAM_PHASES)
        assert config.max_memories_per_phase == 20
        assert config.max_llm_calls == 4
        assert config.replay_variations == 3
        assert config.recombination_pairs == 4
        assert config.emotional_decay_factor == 0.15
        assert config.novelty_threshold == 0.4
        assert config.model_alias == "fast"
        assert config.schedule_expression == "0 3 * * *"
        assert config.trigger_after_consolidation is True

    def test_from_dict_with_defaults(self) -> None:
        config = DreamConfig.from_dict({})
        assert config.enabled is False
        assert config.phases == list(DEFAULT_DREAM_PHASES)
        assert config.max_memories_per_phase == 20
        assert config.max_llm_calls == 4
        assert config.replay_variations == 3
        assert config.recombination_pairs == 4
        assert config.emotional_decay_factor == 0.15
        assert config.novelty_threshold == 0.4
        assert config.model_alias == "fast"
        assert config.schedule_expression == "0 3 * * *"
        assert config.trigger_after_consolidation is True

    def test_from_dict_with_custom_values(self) -> None:
        data = {
            "enabled": True,
            "max_memories_per_phase": 50,
            "max_llm_calls": 10,
            "replay_variations": 5,
            "recombination_pairs": 8,
            "emotional_decay_factor": 0.3,
            "novelty_threshold": 0.6,
            "model_alias": "powerful",
            "schedule_expression": "0 */6 * * *",
            "trigger_after_consolidation": False,
        }
        config = DreamConfig.from_dict(data)
        assert config.enabled is True
        assert config.max_memories_per_phase == 50
        assert config.max_llm_calls == 10
        assert config.replay_variations == 5
        assert config.recombination_pairs == 8
        assert config.emotional_decay_factor == 0.3
        assert config.novelty_threshold == 0.6
        assert config.model_alias == "powerful"
        assert config.schedule_expression == "0 */6 * * *"
        assert config.trigger_after_consolidation is False

    def test_from_dict_with_custom_phases(self) -> None:
        data = {
            "phases": ["replay", "prediction"],
        }
        config = DreamConfig.from_dict(data)
        assert config.phases == [DreamPhase.REPLAY, DreamPhase.PREDICTION]
        assert len(config.phases) == 2

    def test_from_dict_phases_none_uses_defaults(self) -> None:
        data = {"phases": None}
        config = DreamConfig.from_dict(data)
        assert config.phases == list(DEFAULT_DREAM_PHASES)

    def test_default_phases_are_independent_copies(self) -> None:
        """Ensure each DreamConfig gets its own phases list."""
        config1 = DreamConfig()
        config2 = DreamConfig()
        config1.phases.append(DreamPhase.REPLAY)
        assert len(config1.phases) != len(config2.phases)
