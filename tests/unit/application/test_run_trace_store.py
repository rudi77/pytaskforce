"""Unit tests for ``RunTraceStore``.

Covers the boundary behaviour the UI relies on:

* Token-level events (``llm_token``) are dropped at the writer so the ring
  buffer keeps the structural events used by the run drilldown.
* Per-session event cap evicts the oldest non-head events.
* Per-store session cap evicts the LRU session.
"""

from __future__ import annotations

import pytest

from taskforce.application.run_trace_store import (
    RunTraceStore,
    is_structural_event,
)


def test_llm_token_events_are_dropped() -> None:
    store = RunTraceStore(max_sessions=10, max_events_per_session=10)
    store.start("sess-a", mission="m", profile="p")
    for _ in range(50):
        store.record("sess-a", event_type="llm_token", message="x")
    store.record("sess-a", event_type="tool_call", details={"tool": "python"})
    store.record("sess-a", event_type="final_answer", details={"content": "ok"})

    trace = store.get("sess-a")
    assert trace is not None
    types = [e["event_type"] for e in trace["events"]]
    assert "llm_token" not in types
    assert "tool_call" in types
    assert "final_answer" in types


def test_event_cap_evicts_oldest_but_keeps_head() -> None:
    """Buffer keeps the first event so the trace has a sensible start."""
    store = RunTraceStore(max_sessions=4, max_events_per_session=4)
    store.start("sess-b")
    # Push more structural events than the cap.
    store.record("sess-b", event_type="started", message="boot")
    for i in range(10):
        store.record("sess-b", event_type="step_start", step=i)

    trace = store.get("sess-b")
    assert trace is not None
    assert len(trace["events"]) == 4
    assert trace["events"][0]["event_type"] == "started"
    # The remaining tail should be the most-recent step_start events.
    tail_steps = [e["step"] for e in trace["events"][1:]]
    assert tail_steps == sorted(tail_steps)
    assert tail_steps[-1] == 9


def test_session_cap_evicts_lru() -> None:
    store = RunTraceStore(max_sessions=2, max_events_per_session=10)
    store.start("a")
    store.record("a", event_type="started")
    store.start("b")
    store.record("b", event_type="started")
    # Touching ``a`` should bump it back to MRU.
    store.record("a", event_type="step_start", step=1)
    # Adding a third session evicts the LRU — which is now ``b``.
    store.start("c")
    assert store.get("c") is not None
    assert store.get("a") is not None
    assert store.get("b") is None


def test_aggregates_token_and_cost_totals() -> None:
    store = RunTraceStore()
    store.start("sess-c")
    store.record(
        "sess-c",
        event_type="token_usage",
        prompt_tokens=200,
        completion_tokens=80,
        cost_usd=0.012,
    )
    store.record(
        "sess-c",
        event_type="token_usage",
        prompt_tokens=100,
        completion_tokens=20,
        cost_usd=0.004,
    )
    trace = store.get("sess-c")
    assert trace is not None
    assert trace["total_prompt_tokens"] == 300
    assert trace["total_completion_tokens"] == 100
    assert trace["total_cost_usd"] == pytest.approx(0.016)


def test_finish_marks_session_done() -> None:
    store = RunTraceStore()
    store.start("sess-d")
    store.finish("sess-d", final_status="completed")
    trace = store.get("sess-d")
    assert trace is not None
    assert trace["finished"] is True
    assert trace["final_status"] == "completed"


def test_list_sessions_returns_mru_first() -> None:
    store = RunTraceStore()
    store.start("first")
    store.start("second")
    store.start("third")
    listed = store.list_sessions()
    assert [s["session_id"] for s in listed] == ["third", "second", "first"]


def test_is_structural_event_helper() -> None:
    assert is_structural_event("tool_call")
    assert is_structural_event("final_answer")
    assert not is_structural_event("llm_token")
    assert not is_structural_event("unknown_event")


def test_list_sessions_filters_by_user_id() -> None:
    """Regression for #169: per-user filtering must hide other users' runs."""
    store = RunTraceStore()
    store.start("alice-run", tenant_id="t1", user_id="alice")
    store.start("bob-run", tenant_id="t1", user_id="bob")
    store.start("legacy-run")  # untagged, pre-fix entry

    # No filter → everything shows (single-tenant, legacy callers).
    assert {s["session_id"] for s in store.list_sessions()} == {
        "alice-run",
        "bob-run",
        "legacy-run",
    }

    # Filter to alice → only alice's stamped run, no untagged leak.
    alice_only = store.list_sessions(tenant_id="t1", user_id="alice")
    assert {s["session_id"] for s in alice_only} == {"alice-run"}

    # Cross-tenant → nothing.
    assert store.list_sessions(tenant_id="t2", user_id="alice") == []


def test_get_filters_by_user_id() -> None:
    """Regression for #169: trace drilldown also enforces the filter."""
    store = RunTraceStore()
    store.start("alice-run", tenant_id="t1", user_id="alice")

    # Same user → visible.
    assert store.get("alice-run", tenant_id="t1", user_id="alice") is not None
    # Different user in same tenant → hidden.
    assert store.get("alice-run", tenant_id="t1", user_id="bob") is None
    # Single-tenant fall-through (no filter) → visible.
    assert store.get("alice-run") is not None


def test_record_accumulates_token_usage() -> None:
    """Regression for #170: per-run totals must accumulate from token_usage."""
    store = RunTraceStore()
    store.start("sess-tok")
    store.record(
        "sess-tok",
        event_type="token_usage",
        prompt_tokens=120,
        completion_tokens=45,
        cost_usd=0.0021,
    )
    store.record(
        "sess-tok",
        event_type="token_usage",
        prompt_tokens=80,
        completion_tokens=20,
        cost_usd=0.0008,
    )
    listed = store.list_sessions()
    assert listed[0]["session_id"] == "sess-tok"
    assert listed[0]["total_prompt_tokens"] == 200
    assert listed[0]["total_completion_tokens"] == 65
    assert listed[0]["total_cost_usd"] == pytest.approx(0.0029)
