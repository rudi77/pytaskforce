"""Unit tests for the eval runner store and ``run_eval`` orchestration."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from taskforce.application.eval_runner import (
    EvalRunStore,
    get_eval_run_store,
    reset_eval_run_store,
    run_eval,
)


@pytest.fixture(autouse=True)
def _reset_store():
    reset_eval_run_store()
    yield
    reset_eval_run_store()


def test_store_lru_evicts_oldest_runs() -> None:
    store = EvalRunStore(max_runs=2)
    a = store.create(["m"], ["p"])
    b = store.create(["m"], ["p"])
    c = store.create(["m"], ["p"])
    assert store.get(a.run_id) is None  # evicted
    assert store.get(b.run_id) is not None
    assert store.get(c.run_id) is not None


def test_singleton_accessor_is_idempotent() -> None:
    first = get_eval_run_store()
    second = get_eval_run_store()
    assert first is second


class _RecordingExecutor:
    """Records calls + simulates pluggable per-cell behaviour."""

    def __init__(self, behaviours: dict[tuple[str, str], Any] | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self._behaviours = behaviours or {}

    async def execute_mission(self, *, mission: str, profile: str):
        self.calls.append((mission, profile))
        behaviour = self._behaviours.get((mission, profile), "ok")
        if behaviour == "ok":
            return _Result(session_id=f"sess::{profile}::{mission}")
        if behaviour == "raise":
            raise RuntimeError("boom")
        if behaviour == "hang":
            await asyncio.sleep(60)
            return _Result(session_id=None)
        if behaviour == "cancel":
            await asyncio.sleep(60)  # cancellation triggered externally
        return _Result(session_id=None)


class _Result:
    def __init__(self, session_id: str | None, status: str = "completed") -> None:
        self.session_id = session_id
        self.status = status
        self.status_value = status
        self.final_message = "done"


@pytest.mark.asyncio
async def test_run_eval_executes_every_cell() -> None:
    store = get_eval_run_store()
    run = store.create(missions=["m1", "m2"], profiles=["p1", "p2"])
    executor = _RecordingExecutor()

    await run_eval(run, executor=executor, parallelism=2, cell_timeout_s=2.0)

    assert run.finished is True
    assert {(c.mission, c.profile) for c in run.cells} == set(executor.calls)
    assert all(c.status == "completed" for c in run.cells)


@pytest.mark.asyncio
async def test_run_eval_marks_cell_failed_on_exception() -> None:
    store = get_eval_run_store()
    run = store.create(missions=["m1"], profiles=["good", "bad"])
    executor = _RecordingExecutor(
        behaviours={("m1", "bad"): "raise"}
    )

    await run_eval(run, executor=executor, cell_timeout_s=2.0)

    by_profile = {c.profile: c for c in run.cells}
    assert by_profile["good"].status == "completed"
    assert by_profile["bad"].status == "failed"
    assert "boom" in (by_profile["bad"].error or "")


@pytest.mark.asyncio
async def test_run_eval_times_out_long_running_cell() -> None:
    store = get_eval_run_store()
    run = store.create(missions=["hang"], profiles=["p1"])
    executor = _RecordingExecutor(behaviours={("hang", "p1"): "hang"})

    await run_eval(run, executor=executor, parallelism=1, cell_timeout_s=0.1)

    cell = run.cells[0]
    assert cell.status == "timeout"
    assert "exceeded 0.1s" in (cell.error or "")
    assert cell.latency_ms is not None
    assert cell.latency_ms <= 1000


@pytest.mark.asyncio
async def test_run_eval_cancellation_marks_cells_cancelled() -> None:
    """Cancelling the eval task transitions running cells to 'cancelled'."""
    store = get_eval_run_store()
    run = store.create(missions=["cancel"], profiles=["p1", "p2"])
    executor = _RecordingExecutor(
        behaviours={
            ("cancel", "p1"): "cancel",
            ("cancel", "p2"): "cancel",
        }
    )

    task = asyncio.create_task(
        run_eval(run, executor=executor, parallelism=2, cell_timeout_s=10.0)
    )
    # Let cells enter ``running`` state, then cancel.
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert run.finished is True
    statuses = {c.status for c in run.cells}
    # Both should land in ``cancelled``; never ``running``.
    assert "running" not in statuses
    assert statuses == {"cancelled"}


@pytest.mark.asyncio
async def test_run_eval_respects_parallelism_limit() -> None:
    store = get_eval_run_store()
    run = store.create(
        missions=[f"m{i}" for i in range(4)],
        profiles=["p"],
    )
    in_flight = {"current": 0, "peak": 0}

    class _BoundedExecutor:
        async def execute_mission(self, *, mission: str, profile: str):
            in_flight["current"] += 1
            in_flight["peak"] = max(in_flight["peak"], in_flight["current"])
            try:
                await asyncio.sleep(0.05)
                return _Result(session_id=f"sess::{mission}")
            finally:
                in_flight["current"] -= 1

    await run_eval(run, executor=_BoundedExecutor(), parallelism=2)
    assert in_flight["peak"] <= 2
    assert all(c.status == "completed" for c in run.cells)
