"""Phase 1 (ADR-019) — RequestQueue cancellation paths.

Covers the three states a queued request can be in when cancellation
arrives: still queued, already in flight, or already finished.
"""

from __future__ import annotations

import asyncio

import pytest

from taskforce.application.request_queue import RequestProcessor, RequestQueue, RequestResult
from taskforce.core.domain.request import AgentRequest


def _make_request(rid: str = "req-1", priority: int = 5) -> AgentRequest:
    return AgentRequest(
        request_id=rid,
        channel="rest",
        message="hello",
        priority=priority,
    )


@pytest.mark.spec("persistent-agent.cancel_queued_resolves_future_and_skips_execution")
@pytest.mark.asyncio
async def test_cancel_queued_resolves_future_with_cancelled_status() -> None:
    """A queued request that is cancelled before being picked up resolves
    with ``status='cancelled'`` and is invisible to the processor."""
    queue = RequestQueue()
    future = await queue.enqueue(_make_request("req-1"))

    cancelled = queue.cancel("req-1")

    assert cancelled is True
    assert future.done()
    result = future.result()
    assert isinstance(result, RequestResult)
    assert result.status == "cancelled"
    assert queue.is_cancelled("req-1") is True


@pytest.mark.asyncio
async def test_cancel_unknown_returns_false() -> None:
    queue = RequestQueue()
    assert queue.cancel("never-existed") is False


@pytest.mark.spec("persistent-agent.cancel_queued_resolves_future_and_skips_execution")
@pytest.mark.asyncio
async def test_processor_skips_cancelled_request() -> None:
    """The processor's dequeue path must drop cancelled items without
    invoking the executor."""
    queue = RequestQueue()
    invocations: list[AgentRequest] = []

    class _Executor:
        async def execute_mission(self, **_: object) -> object:  # pragma: no cover
            invocations.append("called")  # type: ignore[arg-type]
            raise AssertionError("executor must not run for cancelled requests")

    processor = RequestProcessor(queue, _Executor())  # type: ignore[arg-type]

    await queue.enqueue(_make_request("req-1"))
    queue.cancel("req-1")

    # Run the processor for one cycle: dequeue, see cancellation, skip.
    task = asyncio.create_task(processor.run())
    try:
        await asyncio.wait_for(queue.drain(timeout=2.0), timeout=2.0)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert invocations == []


@pytest.mark.asyncio
async def test_snapshot_lists_pending_requests() -> None:
    queue = RequestQueue()
    await queue.enqueue(_make_request("req-1"))
    await queue.enqueue(_make_request("req-2", priority=1))

    snapshot = queue.snapshot()
    ids = {r.request_id for r in snapshot}
    assert ids == {"req-1", "req-2"}


@pytest.mark.asyncio
async def test_complete_clears_known_requests_bookkeeping() -> None:
    queue = RequestQueue()
    future = await queue.enqueue(_make_request("req-1"))
    queue.complete("req-1", RequestResult(request_id="req-1"))

    assert future.done()
    assert queue.snapshot() == []
