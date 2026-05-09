"""Tests for the trigger-origin ContextVar (issue #177)."""

from __future__ import annotations

import asyncio

from taskforce.core.domain.trigger_context import (
    SCHEDULED_WORKFLOW_ORIGIN,
    get_trigger_origin,
    trigger_origin,
)


def test_default_origin_is_none() -> None:
    assert get_trigger_origin() is None


def test_context_manager_sets_and_restores() -> None:
    assert get_trigger_origin() is None
    with trigger_origin("scheduled_workflow"):
        assert get_trigger_origin() == "scheduled_workflow"
    assert get_trigger_origin() is None


def test_well_known_constant_matches_string() -> None:
    """Plugins coining their own origins compare against a stable value."""
    assert SCHEDULED_WORKFLOW_ORIGIN == "scheduled_workflow"


def test_nested_origins_restore_outer_value() -> None:
    """Nested ``with`` blocks must restore the outer origin, not None."""
    with trigger_origin("outer"):
        assert get_trigger_origin() == "outer"
        with trigger_origin("inner"):
            assert get_trigger_origin() == "inner"
        assert get_trigger_origin() == "outer"
    assert get_trigger_origin() is None


def test_origin_propagates_across_await() -> None:
    """ContextVar carries the origin into nested coroutines without
    threading it through kwargs — that's why we use a ContextVar here
    instead of a plain ``Agent.execute`` parameter."""

    async def _inner() -> str | None:
        # Mimic an arbitrary tool layer reaching for the origin.
        return get_trigger_origin()

    async def _outer() -> str | None:
        with trigger_origin("scheduled_workflow"):
            return await _inner()

    assert asyncio.run(_outer()) == "scheduled_workflow"
