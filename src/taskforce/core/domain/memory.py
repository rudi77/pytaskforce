"""Memory domain models and enums.

Implements a human-like memory model inspired by cognitive science:

- **Strength & decay**: Ebbinghaus forgetting curve — memories weaken over
  time unless reinforced through recall (spaced repetition effect).
- **Emotional valence**: Emotionally charged memories are encoded more
  strongly and decay slower, mirroring the amygdala's role in memory.
- **Importance**: High-importance memories have a strength floor below
  which they never decay, similar to survival-relevant memories.
- **Associations**: Memories link to related memories forming an
  associative network.  Retrieval uses spreading activation — recalling
  one memory boosts related ones.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class MemoryScope(str, Enum):
    """Scopes for memory records."""

    SESSION = "session"
    PROFILE = "profile"
    USER = "user"
    ORG = "org"


class MemoryKind(str, Enum):
    """Kinds of memory records."""

    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    TOOL_RESULT = "tool_result"
    WORKING = "working"
    PREFERENCE = "preference"
    LEARNED_FACT = "learned_fact"
    CONSOLIDATED = "consolidated"


class EmotionalValence(str, Enum):
    """Emotional charge associated with a memory.

    Mirrors the role of the amygdala in human memory encoding:
    emotionally significant events are remembered more vividly and
    persist longer.
    """

    NEUTRAL = "neutral"
    POSITIVE = "positive"
    NEGATIVE = "negative"
    SURPRISE = "surprise"
    FRUSTRATION = "frustration"


# Default initial strength by kind — episodic/short-term memories start
# weaker and must be reinforced; preferences and facts start stronger.
_DEFAULT_STRENGTH: dict[MemoryKind, float] = {
    MemoryKind.SHORT_TERM: 0.4,
    MemoryKind.LONG_TERM: 0.8,
    MemoryKind.TOOL_RESULT: 0.3,
    MemoryKind.WORKING: 1.0,
    MemoryKind.PREFERENCE: 0.9,
    MemoryKind.LEARNED_FACT: 0.85,
    MemoryKind.CONSOLIDATED: 0.75,
}

# Default decay rates (per hour).  Lower = more persistent.
_DEFAULT_DECAY_RATE: dict[MemoryKind, float] = {
    MemoryKind.SHORT_TERM: 0.05,
    MemoryKind.LONG_TERM: 0.002,
    MemoryKind.TOOL_RESULT: 0.08,
    MemoryKind.WORKING: 0.0,
    MemoryKind.PREFERENCE: 0.001,
    MemoryKind.LEARNED_FACT: 0.003,
    MemoryKind.CONSOLIDATED: 0.002,
}

# Emotional valence multipliers for initial strength encoding.
_EMOTION_STRENGTH_BOOST: dict[EmotionalValence, float] = {
    EmotionalValence.NEUTRAL: 0.0,
    EmotionalValence.POSITIVE: 0.10,
    EmotionalValence.NEGATIVE: 0.15,
    EmotionalValence.SURPRISE: 0.20,
    EmotionalValence.FRUSTRATION: 0.12,
}

# Emotional valence multipliers for decay rate (lower = slower decay).
_EMOTION_DECAY_FACTOR: dict[EmotionalValence, float] = {
    EmotionalValence.NEUTRAL: 1.0,
    EmotionalValence.POSITIVE: 0.8,
    EmotionalValence.NEGATIVE: 0.7,
    EmotionalValence.SURPRISE: 0.6,
    EmotionalValence.FRUSTRATION: 0.75,
}


@dataclass
class MemoryRecord:
    """A single memory record with human-like memory properties.

    Attributes:
        scope: Visibility scope (session, profile, user, org).
        kind: Memory kind (short_term, preference, learned_fact, etc.).
        content: The memory content as Markdown text.
        id: Unique identifier (UUID hex).
        tags: Keywords for filtering and association discovery.
        metadata: Arbitrary context JSON.
        created_at: When the memory was first encoded.
        updated_at: Last modification timestamp.
        strength: Current memory strength (0.0–1.0).  Decays over time
            following the Ebbinghaus forgetting curve.
        access_count: How many times this memory has been retrieved.
            More accesses → stronger trace (spaced repetition).
        last_accessed: Timestamp of the most recent retrieval.
        emotional_valence: Emotional charge — affects encoding strength
            and decay rate.
        importance: Perceived significance (0.0–1.0).  Acts as a floor
            for effective strength — important memories never fully fade.
        associations: IDs of related memories forming an associative
            network.  Retrieval triggers spreading activation.
        decay_rate: Per-hour decay constant.  Lower values mean the
            memory persists longer.
    """

    scope: MemoryScope
    kind: MemoryKind
    content: str
    id: str = field(default_factory=lambda: uuid4().hex)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # --- Human-like memory properties ---
    strength: float = -1.0  # -1 sentinel → resolved to kind default on init
    access_count: int = 0
    last_accessed: datetime | None = None
    emotional_valence: EmotionalValence = EmotionalValence.NEUTRAL
    importance: float = 0.5
    associations: list[str] = field(default_factory=list)
    decay_rate: float = -1.0  # -1 sentinel → resolved to kind default on init

    def __post_init__(self) -> None:
        """Resolve sentinel defaults based on kind and emotion."""
        if self.strength < 0:
            base = _DEFAULT_STRENGTH.get(self.kind, 0.5)
            boost = _EMOTION_STRENGTH_BOOST.get(self.emotional_valence, 0.0)
            self.strength = min(1.0, base + boost)
        if self.decay_rate < 0:
            base_decay = _DEFAULT_DECAY_RATE.get(self.kind, 0.01)
            factor = _EMOTION_DECAY_FACTOR.get(self.emotional_valence, 1.0)
            self.decay_rate = base_decay * factor

    def touch(self) -> None:
        """Update the record's updated_at timestamp."""
        self.updated_at = datetime.now(UTC)

    def effective_strength(self, now: datetime | None = None) -> float:
        """Compute current effective strength using the forgetting curve.

        Combines Ebbinghaus-style exponential decay with boosts from
        access frequency and a floor from importance.

        Formula::

            raw = strength × e^(−decay_rate × hours_since_access)
            freq_boost = min(1.0 + log(access_count + 1) × 0.1, 1.5)
            effective = max(raw × freq_boost, importance)

        Returns:
            Effective strength in [0.0, 1.0].
        """
        if now is None:
            now = datetime.now(UTC)
        reference = self.last_accessed or self.updated_at
        hours = max((now - reference).total_seconds() / 3600.0, 0.0)
        raw = self.strength * math.exp(-self.decay_rate * hours)
        freq_boost = min(1.0 + math.log(self.access_count + 1) * 0.1, 1.5)
        effective = raw * freq_boost
        # Importance acts as a floor — important memories never fully fade.
        return min(max(effective, self.importance), 1.0)

    def reinforce(self, now: datetime | None = None) -> None:
        """Strengthen memory on recall (spaced repetition effect).

        Longer gaps since last access produce a bigger strength boost,
        mirroring the spacing effect in human memory research.
        """
        if now is None:
            now = datetime.now(UTC)
        if self.last_accessed:
            hours = max((now - self.last_accessed).total_seconds() / 3600.0, 0.0)
            boost = min(0.3, hours * 0.01)
        else:
            boost = 0.1
        self.strength = min(1.0, self.strength + boost)
        self.access_count += 1
        self.last_accessed = now
        # Slow down decay on repeated access (memory trace strengthens).
        self.decay_rate = max(self.decay_rate * 0.95, 0.0005)

    def associate_with(self, other_id: str) -> None:
        """Create a bidirectional association link to another memory."""
        if other_id not in self.associations and other_id != self.id:
            self.associations.append(other_id)
