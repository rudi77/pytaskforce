"""Tests for human-like memory properties: strength, decay, emotion, associations.

Covers the Ebbinghaus forgetting curve, spaced repetition reinforcement,
emotional valence encoding, importance-based floors, and associative
linking on the ``MemoryRecord`` model.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from taskforce.core.domain.memory import (
    _DEFAULT_STRENGTH,
    _EMOTION_DECAY_FACTOR,
    _EMOTION_STRENGTH_BOOST,
    EmotionalValence,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
)

# ------------------------------------------------------------------
# EmotionalValence enum
# ------------------------------------------------------------------


class TestEmotionalValence:
    """Tests for EmotionalValence enum."""

    def test_values(self) -> None:
        assert EmotionalValence.NEUTRAL.value == "neutral"
        assert EmotionalValence.POSITIVE.value == "positive"
        assert EmotionalValence.NEGATIVE.value == "negative"
        assert EmotionalValence.SURPRISE.value == "surprise"
        assert EmotionalValence.FRUSTRATION.value == "frustration"

    def test_member_count(self) -> None:
        assert len(EmotionalValence) == 5

    def test_is_str_enum(self) -> None:
        assert isinstance(EmotionalValence.POSITIVE, str)

    def test_lookup_by_value(self) -> None:
        assert EmotionalValence("surprise") == EmotionalValence.SURPRISE


# ------------------------------------------------------------------
# Default strength and decay by kind
# ------------------------------------------------------------------


class TestDefaultStrength:
    """New MemoryRecords get kind-appropriate initial strength."""

    def test_short_term_has_low_strength(self) -> None:
        r = MemoryRecord(
            scope=MemoryScope.SESSION,
            kind=MemoryKind.SHORT_TERM,
            content="temp",
        )
        assert abs(r.strength - _DEFAULT_STRENGTH[MemoryKind.SHORT_TERM]) < 0.01

    def test_preference_has_high_strength(self) -> None:
        r = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.PREFERENCE,
            content="likes dark mode",
        )
        assert r.strength >= 0.85

    def test_explicit_strength_overrides_default(self) -> None:
        r = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.PREFERENCE,
            content="test",
            strength=0.3,
        )
        assert r.strength == 0.3


class TestDefaultDecay:
    """New MemoryRecords get kind-appropriate decay rates."""

    def test_short_term_decays_fast(self) -> None:
        r = MemoryRecord(
            scope=MemoryScope.SESSION,
            kind=MemoryKind.SHORT_TERM,
            content="temp",
        )
        pref = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.PREFERENCE,
            content="pref",
        )
        assert r.decay_rate > pref.decay_rate

    def test_explicit_decay_overrides_default(self) -> None:
        r = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.LONG_TERM,
            content="test",
            decay_rate=0.1,
        )
        assert r.decay_rate == 0.1


# ------------------------------------------------------------------
# Emotional encoding
# ------------------------------------------------------------------


class TestEmotionalEncoding:
    """Emotional valence boosts initial strength and slows decay."""

    def test_surprise_boosts_strength(self) -> None:
        neutral = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.LEARNED_FACT,
            content="fact",
            emotional_valence=EmotionalValence.NEUTRAL,
        )
        surprise = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.LEARNED_FACT,
            content="surprise fact",
            emotional_valence=EmotionalValence.SURPRISE,
        )
        assert surprise.strength > neutral.strength

    def test_negative_slows_decay(self) -> None:
        neutral = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.LEARNED_FACT,
            content="fact",
            emotional_valence=EmotionalValence.NEUTRAL,
        )
        negative = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.LEARNED_FACT,
            content="bad fact",
            emotional_valence=EmotionalValence.NEGATIVE,
        )
        assert negative.decay_rate < neutral.decay_rate

    def test_all_valences_have_boost_values(self) -> None:
        for valence in EmotionalValence:
            assert valence in _EMOTION_STRENGTH_BOOST
            assert valence in _EMOTION_DECAY_FACTOR


# ------------------------------------------------------------------
# Forgetting curve (effective_strength)
# ------------------------------------------------------------------


class TestForgettingCurve:
    """Ebbinghaus-inspired forgetting curve tests."""

    def test_strength_at_creation_is_near_base(self) -> None:
        now = datetime.now(UTC)
        r = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.LEARNED_FACT,
            content="fact",
            updated_at=now,
        )
        eff = r.effective_strength(now)
        assert 0.5 < eff <= 1.0

    def test_strength_decays_over_time(self) -> None:
        past = datetime.now(UTC) - timedelta(hours=100)
        r = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.SHORT_TERM,
            content="old",
            updated_at=past,
            importance=0.0,  # No floor — allow full decay
        )
        now = datetime.now(UTC)
        eff = r.effective_strength(now)
        assert eff < r.strength

    def test_importance_acts_as_floor(self) -> None:
        very_old = datetime.now(UTC) - timedelta(days=365)
        r = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.LEARNED_FACT,
            content="critical",
            updated_at=very_old,
            importance=0.8,
        )
        now = datetime.now(UTC)
        eff = r.effective_strength(now)
        assert eff >= 0.8

    def test_effective_never_exceeds_one(self) -> None:
        now = datetime.now(UTC)
        r = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.PREFERENCE,
            content="pref",
            strength=1.0,
            access_count=100,
            updated_at=now,
            last_accessed=now,
        )
        eff = r.effective_strength(now)
        assert eff <= 1.0

    def test_access_count_boosts_effective_strength(self) -> None:
        now = datetime.now(UTC)
        past = now - timedelta(hours=10)
        low_access = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.LEARNED_FACT,
            content="fact",
            updated_at=past,
            access_count=0,
        )
        high_access = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.LEARNED_FACT,
            content="fact",
            updated_at=past,
            access_count=20,
        )
        # Ensure they have the same base strength
        high_access.strength = low_access.strength
        high_access.decay_rate = low_access.decay_rate
        eff_low = low_access.effective_strength(now)
        eff_high = high_access.effective_strength(now)
        assert eff_high > eff_low


# ------------------------------------------------------------------
# Spaced repetition (reinforce)
# ------------------------------------------------------------------


class TestSpacedRepetition:
    """Memory reinforcement on recall."""

    def test_reinforce_increases_strength(self) -> None:
        r = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.LEARNED_FACT,
            content="fact",
            strength=0.5,
        )
        original_strength = r.strength
        r.reinforce()
        assert r.strength > original_strength

    def test_reinforce_increments_access_count(self) -> None:
        r = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.LEARNED_FACT,
            content="fact",
        )
        assert r.access_count == 0
        r.reinforce()
        assert r.access_count == 1
        r.reinforce()
        assert r.access_count == 2

    def test_reinforce_updates_last_accessed(self) -> None:
        r = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.LEARNED_FACT,
            content="fact",
        )
        assert r.last_accessed is None
        r.reinforce()
        assert r.last_accessed is not None

    def test_longer_gap_gives_bigger_boost(self) -> None:
        now = datetime.now(UTC)
        # Recently accessed
        r1 = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.LEARNED_FACT,
            content="fact",
            strength=0.5,
            last_accessed=now - timedelta(minutes=5),
        )
        # Not accessed for a long time
        r2 = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.LEARNED_FACT,
            content="fact",
            strength=0.5,
            last_accessed=now - timedelta(hours=24),
        )
        r1.reinforce(now)
        r2.reinforce(now)
        assert r2.strength > r1.strength

    def test_reinforce_capped_at_one(self) -> None:
        r = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.PREFERENCE,
            content="pref",
            strength=0.99,
        )
        r.reinforce()
        assert r.strength <= 1.0

    def test_reinforce_slows_decay(self) -> None:
        r = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.LEARNED_FACT,
            content="fact",
        )
        original_decay = r.decay_rate
        r.reinforce()
        assert r.decay_rate < original_decay


# ------------------------------------------------------------------
# Associations
# ------------------------------------------------------------------


class TestAssociations:
    """Associative memory linking."""

    def test_associate_with_adds_id(self) -> None:
        r = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.LEARNED_FACT,
            content="fact",
        )
        r.associate_with("other-id")
        assert "other-id" in r.associations

    def test_no_self_association(self) -> None:
        r = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.LEARNED_FACT,
            content="fact",
            id="my-id",
        )
        r.associate_with("my-id")
        assert "my-id" not in r.associations

    def test_no_duplicate_associations(self) -> None:
        r = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.LEARNED_FACT,
            content="fact",
        )
        r.associate_with("other-id")
        r.associate_with("other-id")
        assert r.associations.count("other-id") == 1

    def test_associations_default_empty(self) -> None:
        r = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.LEARNED_FACT,
            content="fact",
        )
        assert r.associations == []

    def test_associations_independent_per_instance(self) -> None:
        r1 = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.LEARNED_FACT,
            content="a",
        )
        r2 = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.LEARNED_FACT,
            content="b",
        )
        r1.associate_with("id-x")
        assert r2.associations == []


# ------------------------------------------------------------------
# Backward compatibility
# ------------------------------------------------------------------


class TestBackwardCompatibility:
    """Existing code that creates MemoryRecords without new fields still works."""

    def test_minimal_creation_still_works(self) -> None:
        r = MemoryRecord(
            scope=MemoryScope.SESSION,
            kind=MemoryKind.SHORT_TERM,
            content="hello",
        )
        assert r.strength > 0
        assert r.decay_rate > 0
        assert r.access_count == 0
        assert r.last_accessed is None
        assert r.emotional_valence == EmotionalValence.NEUTRAL
        assert r.importance == 0.5
        assert r.associations == []

    def test_touch_still_works(self) -> None:
        r = MemoryRecord(
            scope=MemoryScope.SESSION,
            kind=MemoryKind.SHORT_TERM,
            content="hello",
        )
        old_updated = r.updated_at
        import time

        time.sleep(0.01)
        r.touch()
        assert r.updated_at > old_updated
