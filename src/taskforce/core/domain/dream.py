"""Dream domain models and enums.

Implements generative dreaming — a cognitive-inspired process that creates
new knowledge by recombining, varying, and simulating against the existing
memory corpus.  Runs as an optional phase after memory consolidation.

Four dreaming sub-phases:

- **Replay with Variations**: Re-narrate past experiences with deliberate
  perturbations to extract latent lessons.
- **Creative Recombination**: Merge memories from unrelated domains to
  generate novel cross-domain insights.
- **Emotional Processing**: Reappraise emotionally charged memories,
  dampening negative valence over cycles (REM-like regulation).
- **Predictive Simulation**: Run forward-looking "what if" scenarios
  based on detected patterns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from taskforce.core.domain.memory import EmotionalValence


class DreamPhase(str, Enum):
    """Sub-phases of a dream cycle."""

    REPLAY = "replay"
    RECOMBINATION = "recombination"
    EMOTIONAL_PROCESSING = "emotional_processing"
    PREDICTION = "prediction"


class DreamInsightType(str, Enum):
    """Type of insight produced during dreaming."""

    VARIATION = "variation"
    RECOMBINATION = "recombination"
    REAPPRAISAL = "reappraisal"
    PREDICTION = "prediction"


class DreamStatus(str, Enum):
    """Status of a dream cycle."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DreamTrigger(str, Enum):
    """What triggered the dream cycle."""

    SCHEDULED = "scheduled"
    MANUAL = "manual"
    POST_CONSOLIDATION = "post_consolidation"


@dataclass
class DreamInsight:
    """A single insight produced during a dream phase.

    Attributes:
        content: The insight text (Markdown).
        source_memory_ids: IDs of memories that contributed to this insight.
        insight_type: Category of the insight.
        confidence: How confident the insight is (0.0-1.0).
        novelty_score: How different from existing memories (0.0-1.0).
        tags: Keywords for filtering and association.
        emotional_valence: Emotional charge of the insight.
    """

    content: str
    source_memory_ids: list[str]
    insight_type: DreamInsightType
    confidence: float = 0.5
    novelty_score: float = 0.5
    tags: list[str] = field(default_factory=list)
    emotional_valence: EmotionalValence = EmotionalValence.NEUTRAL

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "content": self.content,
            "source_memory_ids": self.source_memory_ids,
            "insight_type": self.insight_type.value,
            "confidence": self.confidence,
            "novelty_score": self.novelty_score,
            "tags": self.tags,
            "emotional_valence": self.emotional_valence.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DreamInsight:
        """Deserialize from dictionary."""
        return cls(
            content=data["content"],
            source_memory_ids=data.get("source_memory_ids", []),
            insight_type=DreamInsightType(data.get("insight_type", "variation")),
            confidence=data.get("confidence", 0.5),
            novelty_score=data.get("novelty_score", 0.5),
            tags=data.get("tags", []),
            emotional_valence=EmotionalValence(
                data.get("emotional_valence", "neutral")
            ),
        )


@dataclass
class DreamCycle:
    """Result of a complete dream cycle.

    Attributes:
        dream_id: Unique identifier for this dream cycle.
        started_at: When dreaming started.
        ended_at: When dreaming completed.
        status: Current status of the cycle.
        insights: Insights produced during dreaming.
        memories_processed: Number of memories fed into the pipeline.
        memories_created: Number of new memories persisted from insights.
        total_tokens: Total LLM tokens consumed.
        trigger: What triggered this dream cycle.
    """

    dream_id: str = field(default_factory=lambda: uuid4().hex)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    status: DreamStatus = DreamStatus.RUNNING
    insights: list[DreamInsight] = field(default_factory=list)
    memories_processed: int = 0
    memories_created: int = 0
    total_tokens: int = 0
    trigger: DreamTrigger = DreamTrigger.MANUAL

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "dream_id": self.dream_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "status": self.status.value,
            "insights": [i.to_dict() for i in self.insights],
            "memories_processed": self.memories_processed,
            "memories_created": self.memories_created,
            "total_tokens": self.total_tokens,
            "trigger": self.trigger.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DreamCycle:
        """Deserialize from dictionary."""
        ended_at = data.get("ended_at")
        return cls(
            dream_id=data.get("dream_id", uuid4().hex),
            started_at=datetime.fromisoformat(data["started_at"]),
            ended_at=datetime.fromisoformat(ended_at) if ended_at else None,
            status=DreamStatus(data.get("status", "completed")),
            insights=[
                DreamInsight.from_dict(i) for i in data.get("insights", [])
            ],
            memories_processed=data.get("memories_processed", 0),
            memories_created=data.get("memories_created", 0),
            total_tokens=data.get("total_tokens", 0),
            trigger=DreamTrigger(data.get("trigger", "manual")),
        )


# Default phases in execution order.
DEFAULT_DREAM_PHASES: list[DreamPhase] = [
    DreamPhase.REPLAY,
    DreamPhase.RECOMBINATION,
    DreamPhase.EMOTIONAL_PROCESSING,
    DreamPhase.PREDICTION,
]


@dataclass
class DreamConfig:
    """Configuration for a dream cycle.

    Attributes:
        enabled: Whether dreaming is active.
        phases: Which dream phases to run, in order.
        max_memories_per_phase: Cap per phase for cost control.
        max_llm_calls: Total LLM call budget across all phases.
        replay_variations: Number of memories to replay with variations.
        recombination_pairs: Number of cross-domain memory pairs.
        emotional_decay_factor: How much to dampen negative valence (0.0-1.0).
        novelty_threshold: Filter out insights below this novelty score.
        model_alias: LLM model alias to use.
        schedule_expression: Cron expression for scheduled dreaming.
        trigger_after_consolidation: Run dreaming after each consolidation.
    """

    enabled: bool = False
    phases: list[DreamPhase] = field(default_factory=lambda: list(DEFAULT_DREAM_PHASES))
    max_memories_per_phase: int = 20
    max_llm_calls: int = 4
    replay_variations: int = 3
    recombination_pairs: int = 4
    emotional_decay_factor: float = 0.15
    novelty_threshold: float = 0.4
    model_alias: str = "fast"
    schedule_expression: str = "0 3 * * *"
    trigger_after_consolidation: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DreamConfig:
        """Create config from a dictionary (e.g. profile YAML section)."""
        phases_raw = data.get("phases")
        phases = (
            [DreamPhase(p) for p in phases_raw]
            if phases_raw
            else list(DEFAULT_DREAM_PHASES)
        )
        return cls(
            enabled=data.get("enabled", False),
            phases=phases,
            max_memories_per_phase=data.get("max_memories_per_phase", 20),
            max_llm_calls=data.get("max_llm_calls", 4),
            replay_variations=data.get("replay_variations", 3),
            recombination_pairs=data.get("recombination_pairs", 4),
            emotional_decay_factor=data.get("emotional_decay_factor", 0.15),
            novelty_threshold=data.get("novelty_threshold", 0.4),
            model_alias=data.get("model_alias", "fast"),
            schedule_expression=data.get("schedule_expression", "0 3 * * *"),
            trigger_after_consolidation=data.get(
                "trigger_after_consolidation", True
            ),
        )
