"""Unit tests for the StandingGoal domain model."""

from __future__ import annotations

from datetime import UTC, datetime

from taskforce.core.domain.standing_goal import StandingGoal


def test_defaults_set_uuid_and_priority() -> None:
    goal = StandingGoal(
        description="Weekly summary",
        evaluation_prompt="Should we send a weekly summary now?",
        frequency="0 9 * * 1",
    )
    assert len(goal.goal_id) == 32  # uuid hex
    assert goal.priority == 5
    assert goal.enabled is True
    assert goal.last_evaluated_at is None
    assert goal.last_action_taken == ""
    assert goal.metadata == {}


def test_round_trip_preserves_fields() -> None:
    goal = StandingGoal(
        description="Daily standup",
        evaluation_prompt="Generate today's standup notes.",
        frequency="0 9 * * 1-5",
        priority=3,
        enabled=False,
        last_evaluated_at=datetime(2026, 5, 1, 9, 0, tzinfo=UTC),
        last_action_taken="sent",
        metadata={"team": "platform"},
    )
    encoded = goal.to_dict()
    decoded = StandingGoal.from_dict(encoded)
    assert decoded == goal


def test_from_dict_tolerates_missing_optional_fields() -> None:
    goal = StandingGoal.from_dict(
        {
            "description": "x",
            "evaluation_prompt": "y",
            "frequency": "* * * * *",
        }
    )
    assert goal.priority == 5
    assert goal.enabled is True
    assert goal.metadata == {}
