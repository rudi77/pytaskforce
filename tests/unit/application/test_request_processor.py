"""Tests for RequestProcessor and Future-based RequestQueue (ADR-016 Phase 4)."""

import asyncio
from typing import Any

import pytest

from taskforce.application.conversation_manager import ConversationManager
from taskforce.application.request_queue import RequestProcessor, RequestQueue, RequestResult
from taskforce.core.domain.request import AgentRequest
from taskforce.core.domain.models import ExecutionResult
from taskforce.infrastructure.persistence.file_conversation_store import (
    FileConversationStore,
)


class FakeExecutor:
    """Minimal executor stub returning a canned response."""

    def __init__(self, reply: str = "Agent reply") -> None:
        self._reply = reply
        self.calls: list[dict[str, Any]] = []

    async def execute_mission(self, **kwargs: Any) -> ExecutionResult:
        self.calls.append(kwargs)
        return ExecutionResult(
            session_id=kwargs["session_id"],
            status="completed",
            final_message=self._reply,
        )


class FailingExecutor:
    """Executor that raises on first call, then succeeds."""

    def __init__(self) -> None:
        self.call_count = 0

    async def execute_mission(self, **kwargs: Any) -> ExecutionResult:
        self.call_count += 1
        if self.call_count == 1:
            raise RuntimeError("Simulated execution failure")
        return ExecutionResult(
            session_id=kwargs["session_id"],
            status="completed",
            final_message="Recovered",
        )


@pytest.fixture
def conv_manager(tmp_path):
    store = FileConversationStore(work_dir=str(tmp_path))
    return ConversationManager(store)


# ---------------------------------------------------------------------------
# RequestQueue Future-based tests
# ---------------------------------------------------------------------------


class TestRequestQueueFutures:
    async def test_enqueue_returns_future(self):
        queue = RequestQueue(max_size=10)
        request = AgentRequest(channel="cli", message="Hello")
        future = await queue.enqueue(request)
        assert isinstance(future, asyncio.Future)
        assert not future.done()

    async def test_complete_resolves_future(self):
        queue = RequestQueue(max_size=10)
        request = AgentRequest(channel="cli", message="Hello")
        future = await queue.enqueue(request)

        # Dequeue and complete
        dequeued = await queue.dequeue()
        result = RequestResult(
            request_id=dequeued.request_id, status="completed", reply="Done"
        )
        queue.complete(dequeued.request_id, result)

        assert future.done()
        assert (await future).reply == "Done"

    async def test_fail_resolves_future_with_error(self):
        queue = RequestQueue(max_size=10)
        request = AgentRequest(channel="cli", message="Fail")
        future = await queue.enqueue(request)

        dequeued = await queue.dequeue()
        queue.fail(dequeued.request_id, "Something went wrong")

        result = await future
        assert result.status == "failed"
        assert result.error == "Something went wrong"

    async def test_pending_count(self):
        queue = RequestQueue(max_size=10)
        r1 = AgentRequest(channel="cli", message="a")
        r2 = AgentRequest(channel="cli", message="b")
        await queue.enqueue(r1)
        await queue.enqueue(r2)

        assert queue.pending_count == 2

        dequeued = await queue.dequeue()
        queue.complete(dequeued.request_id, RequestResult(request_id=dequeued.request_id))
        assert queue.pending_count == 1

    async def test_legacy_process_loop_still_works(self):
        """Backward compat: process_loop handler-based API works."""
        queue = RequestQueue(max_size=10)
        processed = []

        async def handler(req: AgentRequest):
            processed.append(req.message)

        await queue.enqueue(AgentRequest(channel="cli", message="Hello"))
        task = asyncio.create_task(queue.process_loop(handler))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert processed == ["Hello"]


# ---------------------------------------------------------------------------
# RequestProcessor tests
# ---------------------------------------------------------------------------


class TestRequestProcessor:
    async def test_processor_executes_request(self):
        queue = RequestQueue(max_size=10)
        executor = FakeExecutor(reply="Processed!")
        processor = RequestProcessor(queue, executor)

        request = AgentRequest(channel="cli", message="Do something")
        future = await queue.enqueue(request)

        task = asyncio.create_task(processor.run())
        result = await asyncio.wait_for(future, timeout=2.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert result.status == "completed"
        assert result.reply == "Processed!"
        assert result.request_id == request.request_id

    async def test_processor_sequential_execution(self):
        """Requests are processed one at a time, not in parallel."""
        queue = RequestQueue(max_size=10)
        active = 0
        max_concurrent = 0
        order = []

        class TrackingExecutor:
            async def execute_mission(self, **kwargs: Any) -> ExecutionResult:
                nonlocal active, max_concurrent
                active += 1
                max_concurrent = max(max_concurrent, active)
                await asyncio.sleep(0.01)
                order.append(kwargs["mission"])
                active -= 1
                return ExecutionResult(
                    session_id=kwargs["session_id"],
                    status="completed",
                    final_message=f"reply-{kwargs['mission']}",
                )

        processor = RequestProcessor(queue, TrackingExecutor())

        futures = []
        for i in range(3):
            f = await queue.enqueue(AgentRequest(channel="cli", message=f"msg-{i}"))
            futures.append(f)

        task = asyncio.create_task(processor.run())
        results = await asyncio.wait_for(
            asyncio.gather(*futures), timeout=5.0
        )
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert max_concurrent == 1
        assert order == ["msg-0", "msg-1", "msg-2"]
        assert all(r.status == "completed" for r in results)

    async def test_processor_handles_execution_failure(self):
        """A failing request doesn't stop the processing loop."""
        queue = RequestQueue(max_size=10)
        executor = FailingExecutor()
        processor = RequestProcessor(queue, executor)

        f1 = await queue.enqueue(AgentRequest(channel="cli", message="will-fail"))
        f2 = await queue.enqueue(AgentRequest(channel="cli", message="will-succeed"))

        task = asyncio.create_task(processor.run())
        r1 = await asyncio.wait_for(f1, timeout=2.0)
        r2 = await asyncio.wait_for(f2, timeout=2.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert r1.status == "failed"
        assert "Simulated" in r1.error
        assert r2.status == "completed"
        assert r2.reply == "Recovered"

    async def test_processor_with_conversation_manager(self, conv_manager):
        """Processor appends user/assistant messages to conversation."""
        queue = RequestQueue(max_size=10)
        executor = FakeExecutor(reply="Bot response")
        processor = RequestProcessor(queue, executor, conversation_manager=conv_manager)

        conv_id = await conv_manager.get_or_create("cli", "user-1")
        request = AgentRequest(
            channel="cli",
            message="User input",
            conversation_id=conv_id,
            sender_id="user-1",
        )
        future = await queue.enqueue(request)

        task = asyncio.create_task(processor.run())
        result = await asyncio.wait_for(future, timeout=2.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert result.conversation_id == conv_id
        messages = await conv_manager.get_messages(conv_id)
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "User input"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Bot response"

    async def test_processor_without_conversation_manager(self):
        """Processor works without ConversationManager (no history)."""
        queue = RequestQueue(max_size=10)
        executor = FakeExecutor()
        processor = RequestProcessor(queue, executor, conversation_manager=None)

        future = await queue.enqueue(AgentRequest(channel="cli", message="No conv"))
        task = asyncio.create_task(processor.run())
        result = await asyncio.wait_for(future, timeout=2.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert result.status == "completed"
        # No conversation_id since no manager
        assert result.conversation_id is None

    async def test_running_property(self):
        queue = RequestQueue(max_size=10)
        executor = FakeExecutor()
        processor = RequestProcessor(queue, executor)

        assert not processor.running

        # Need to enqueue something so the processor doesn't block forever
        await queue.enqueue(AgentRequest(channel="cli", message="test"))
        task = asyncio.create_task(processor.run())
        await asyncio.sleep(0.02)

        assert processor.running

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert not processor.running
