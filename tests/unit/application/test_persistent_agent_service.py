"""Tests for PersistentAgentService (ADR-016 Phase 5)."""

import asyncio
from typing import Any

import pytest

from taskforce.application.conversation_manager import ConversationManager
from taskforce.application.persistent_agent_service import PersistentAgentService
from taskforce.core.domain.models import ExecutionResult
from taskforce.core.domain.request import AgentRequest
from taskforce.infrastructure.persistence.file_agent_state import FileAgentState
from taskforce.infrastructure.persistence.file_conversation_store import (
    FileConversationStore,
)


class FakeExecutor:
    """Minimal executor stub."""

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


class SlowExecutor:
    """Executor that takes time, for testing drain."""

    async def execute_mission(self, **kwargs: Any) -> ExecutionResult:
        await asyncio.sleep(0.05)
        return ExecutionResult(
            session_id=kwargs["session_id"],
            status="completed",
            final_message="Slow reply",
        )


class FailingExecutor:
    """Executor that fails on first call."""

    def __init__(self) -> None:
        self.call_count = 0

    async def execute_mission(self, **kwargs: Any) -> ExecutionResult:
        self.call_count += 1
        if self.call_count == 1:
            raise RuntimeError("Boom")
        return ExecutionResult(
            session_id=kwargs["session_id"],
            status="completed",
            final_message="Recovered",
        )


@pytest.fixture
def service_parts(tmp_path):
    """Build service components with temp directory."""
    conv_store = FileConversationStore(work_dir=str(tmp_path / "conv"))
    conv_manager = ConversationManager(conv_store)
    agent_state = FileAgentState(work_dir=str(tmp_path / "state"))
    executor = FakeExecutor()
    return executor, agent_state, conv_manager


@pytest.fixture
def service(service_parts):
    executor, agent_state, conv_manager = service_parts
    return PersistentAgentService(
        executor=executor,
        agent_state=agent_state,
        conversation_manager=conv_manager,
        queue_max_size=50,
    )


class TestLifecycle:
    async def test_start_and_stop(self, service):
        assert not service.running

        await service.start()
        assert service.running

        await service.stop()
        assert not service.running

    async def test_start_twice_raises(self, service):
        await service.start()
        try:
            with pytest.raises(RuntimeError, match="already running"):
                await service.start()
        finally:
            await service.stop()

    async def test_stop_when_not_started_is_noop(self, service):
        await service.stop()  # Should not raise

    async def test_state_saved_on_stop(self, service_parts):
        executor, agent_state, conv_manager = service_parts
        service = PersistentAgentService(
            executor=executor,
            agent_state=agent_state,
            conversation_manager=conv_manager,
        )

        await service.start()
        await service.stop()

        state = await agent_state.load()
        assert state is not None
        assert "started_at" in state
        assert "active_conversation_ids" in state
        assert state["_version"] >= 1

    async def test_state_loaded_on_start(self, service_parts):
        executor, agent_state, conv_manager = service_parts

        # Pre-save some state. FileAgentState.save() increments _version,
        # so saving with _version=5 persists _version=6.
        await agent_state.save({"_version": 5, "custom": "data"})
        saved = await agent_state.load()
        expected_version = saved["_version"]

        service = PersistentAgentService(
            executor=executor,
            agent_state=agent_state,
            conversation_manager=conv_manager,
        )
        await service.start()
        try:
            status = await service.status()
            assert status.state_version == expected_version
        finally:
            await service.stop()


class TestSubmit:
    async def test_submit_request(self, service):
        await service.start()
        try:
            request = AgentRequest(channel="cli", message="Hello")
            result = await asyncio.wait_for(service.submit(request), timeout=5.0)

            assert result.status == "completed"
            assert result.reply == "Agent reply"
        finally:
            await service.stop()

    async def test_submit_when_not_running_raises(self, service):
        with pytest.raises(RuntimeError, match="not running"):
            await service.submit(AgentRequest(channel="cli", message="test"))

    async def test_multiple_sequential_requests(self, service):
        await service.start()
        try:
            results = []
            for i in range(3):
                r = await asyncio.wait_for(
                    service.submit(AgentRequest(channel="cli", message=f"msg-{i}")),
                    timeout=5.0,
                )
                results.append(r)

            assert len(results) == 3
            assert all(r.status == "completed" for r in results)
        finally:
            await service.stop()

    async def test_submit_with_conversation(self, service_parts):
        executor, agent_state, conv_manager = service_parts
        service = PersistentAgentService(
            executor=executor,
            agent_state=agent_state,
            conversation_manager=conv_manager,
        )

        await service.start()
        try:
            conv_id = await conv_manager.get_or_create("cli", "user-1")
            request = AgentRequest(
                channel="cli",
                message="With conversation",
                conversation_id=conv_id,
                sender_id="user-1",
            )
            result = await asyncio.wait_for(service.submit(request), timeout=5.0)

            assert result.conversation_id == conv_id

            messages = await conv_manager.get_messages(conv_id)
            assert len(messages) == 2
            assert messages[0]["role"] == "user"
            assert messages[1]["role"] == "assistant"
        finally:
            await service.stop()

    async def test_failed_request_doesnt_crash_service(self, service_parts):
        _, agent_state, conv_manager = service_parts
        executor = FailingExecutor()
        service = PersistentAgentService(
            executor=executor,
            agent_state=agent_state,
            conversation_manager=conv_manager,
        )

        await service.start()
        try:
            r1 = await asyncio.wait_for(
                service.submit(AgentRequest(channel="cli", message="will-fail")),
                timeout=5.0,
            )
            assert r1.status == "failed"

            # Service is still running — next request works.
            assert service.running

            r2 = await asyncio.wait_for(
                service.submit(AgentRequest(channel="cli", message="will-succeed")),
                timeout=5.0,
            )
            assert r2.status == "completed"
        finally:
            await service.stop()


class TestStatus:
    async def test_status_when_running(self, service):
        await service.start()
        try:
            status = await service.status()
            assert status.running is True
            assert status.queue_size == 0
            assert status.started_at is not None
        finally:
            await service.stop()

    async def test_status_when_stopped(self, service):
        status = await service.status()
        assert status.running is False

    async def test_last_activity_updated_after_submit(self, service):
        await service.start()
        try:
            status_before = await service.status()
            assert status_before.last_activity is None

            await asyncio.wait_for(
                service.submit(AgentRequest(channel="cli", message="test")),
                timeout=5.0,
            )

            status_after = await service.status()
            assert status_after.last_activity is not None
        finally:
            await service.stop()

    async def test_active_conversations_in_status(self, service_parts):
        executor, agent_state, conv_manager = service_parts
        service = PersistentAgentService(
            executor=executor,
            agent_state=agent_state,
            conversation_manager=conv_manager,
        )

        # Create some conversations.
        await conv_manager.get_or_create("telegram", "user-1")
        await conv_manager.get_or_create("cli", "user-2")

        await service.start()
        try:
            status = await service.status()
            assert status.active_conversations == 2
        finally:
            await service.stop()


class TestDrain:
    async def test_drain_on_stop(self, service_parts):
        _, agent_state, conv_manager = service_parts
        executor = SlowExecutor()
        service = PersistentAgentService(
            executor=executor,
            agent_state=agent_state,
            conversation_manager=conv_manager,
            drain_timeout=5.0,
        )

        await service.start()

        # Submit without awaiting — let queue fill up.
        futures = []
        for i in range(3):
            f = await service.queue.enqueue(AgentRequest(channel="cli", message=f"drain-{i}"))
            futures.append(f)

        # Stop should drain all pending requests.
        await service.stop()

        # All futures should be resolved.
        for f in futures:
            assert f.done()

    async def test_queue_property(self, service):
        assert service.queue is not None
        assert service.queue.size == 0
