"""Phase 1 (ADR-019) — interrupt propagation through sub-agent registry.

Verifies that ``request_interrupt_for_parent`` reaches every running
child registered for a parent session, and that future children spawned
*after* the interrupt was raised still get the signal.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from taskforce.application.sub_agent_spawner import (
    _ACTIVE_CHILDREN,
    _INTERRUPTED_PARENTS,
    _deregister_child,
    _register_child,
    request_interrupt_for_parent,
)


def _make_child() -> MagicMock:
    """Return a stub agent exposing only the interrupt-flag surface."""
    child = MagicMock()
    child.request_interrupt = MagicMock()
    return child


def setup_function() -> None:
    """Each test gets a clean registry (process-wide module state)."""
    _ACTIVE_CHILDREN.clear()
    _INTERRUPTED_PARENTS.clear()


@pytest.mark.spec("interruption.interrupt_propagates_to_sub_agents")
@pytest.mark.spec("sub-agents.parent_interrupt_propagates_to_children")
def test_interrupt_signals_every_active_child() -> None:
    parent = "session-A"
    child_a = _make_child()
    child_b = _make_child()
    _register_child(parent, child_a)
    _register_child(parent, child_b)

    signalled = request_interrupt_for_parent(parent)

    assert signalled == 2
    child_a.request_interrupt.assert_called_once()
    child_b.request_interrupt.assert_called_once()


@pytest.mark.spec("interruption.interrupt_propagates_to_sub_agents")
def test_interrupt_isolated_per_parent() -> None:
    a_child = _make_child()
    b_child = _make_child()
    _register_child("session-A", a_child)
    _register_child("session-B", b_child)

    request_interrupt_for_parent("session-A")

    a_child.request_interrupt.assert_called_once()
    b_child.request_interrupt.assert_not_called()


@pytest.mark.spec("sub-agents.late_child_spawn_after_interrupt_is_signalled")
def test_late_child_inherits_interrupt() -> None:
    """A child registered *after* request_interrupt_for_parent must be flagged."""
    parent = "session-A"
    request_interrupt_for_parent(parent)  # No children yet — flag only.

    late = _make_child()
    parent_already_interrupted = _register_child(parent, late)

    assert parent_already_interrupted is True
    # The spawner is responsible for translating that signal into an
    # actual ``request_interrupt`` on the new child; we assert the
    # contract here so spawner logic stays honest.


def test_deregister_clears_interrupted_flag_when_last_child_exits() -> None:
    parent = "session-A"
    child = _make_child()
    _register_child(parent, child)
    request_interrupt_for_parent(parent)

    _deregister_child(parent, child)

    assert parent not in _ACTIVE_CHILDREN
    assert parent not in _INTERRUPTED_PARENTS


def test_request_interrupt_for_unknown_parent_is_noop() -> None:
    signalled = request_interrupt_for_parent("does-not-exist")
    assert signalled == 0
