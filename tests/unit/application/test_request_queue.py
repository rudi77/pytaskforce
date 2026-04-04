"""Tests for RequestQueue — the central agent request queue."""

import asyncio

import pytest

from taskforce.application.request_queue import RequestQueue
from taskforce.core.domain.request import AgentRequest


class TestRequestQueue:
    @pytest.fixture
    def queue(self):
        return RequestQueue(max_size=10)

    async def test_enqueue_and_process(self, queue):
        processed = []

        async def handler(req: AgentRequest):
            processed.append(req)

        await queue.enqueue(AgentRequest(channel="cli", message="Hello"))
        await queue.enqueue(AgentRequest(channel="telegram", message="World"))

        task = asyncio.create_task(queue.process_loop(handler))
        # Give the loop time to process both items.
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert len(processed) == 2
        assert processed[0].message == "Hello"
        assert processed[1].message == "World"

    async def test_sequential_processing(self, queue):
        """Verify requests are processed one at a time, not in parallel."""
        processing_order = []
        active_count = 0
        max_concurrent = 0

        async def handler(req: AgentRequest):
            nonlocal active_count, max_concurrent
            active_count += 1
            max_concurrent = max(max_concurrent, active_count)
            await asyncio.sleep(0.01)
            processing_order.append(req.message)
            active_count -= 1

        for i in range(3):
            await queue.enqueue(AgentRequest(channel="cli", message=f"msg-{i}"))

        task = asyncio.create_task(queue.process_loop(handler))
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert max_concurrent == 1
        assert processing_order == ["msg-0", "msg-1", "msg-2"]

    async def test_handler_error_doesnt_stop_loop(self, queue):
        processed = []
        call_count = 0

        async def handler(req: AgentRequest):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Simulated error")
            processed.append(req.message)

        await queue.enqueue(AgentRequest(channel="cli", message="will-fail"))
        await queue.enqueue(AgentRequest(channel="cli", message="will-succeed"))

        task = asyncio.create_task(queue.process_loop(handler))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert len(processed) == 1
        assert processed[0] == "will-succeed"

    async def test_size_property(self, queue):
        assert queue.size == 0
        await queue.enqueue(AgentRequest(channel="cli", message="a"))
        assert queue.size == 1

    async def test_drain(self, queue):
        processed = []

        async def handler(req: AgentRequest):
            processed.append(req.message)

        await queue.enqueue(AgentRequest(channel="cli", message="drain-me"))
        task = asyncio.create_task(queue.process_loop(handler))
        await queue.drain(timeout=2.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert processed == ["drain-me"]
