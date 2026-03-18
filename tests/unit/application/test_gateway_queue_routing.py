"""Tests for CommunicationGateway with RequestQueue routing (ADR-016 Phase 4)."""

import asyncio
from typing import Any

import pytest

from taskforce.application.conversation_manager import ConversationManager
from taskforce.application.gateway import CommunicationGateway
from taskforce.application.request_queue import RequestProcessor, RequestQueue
from taskforce.core.domain.gateway import GatewayOptions, InboundMessage
from taskforce.core.domain.models import ExecutionResult
from taskforce.infrastructure.communication.gateway_conversation_store import (
    InMemoryConversationStore,
)
from taskforce.infrastructure.communication.recipient_registry import (
    InMemoryRecipientRegistry,
)
from taskforce.infrastructure.persistence.file_conversation_store import (
    FileConversationStore,
)


class FakeExecutor:
    """Minimal executor stub returning a canned response."""

    def __init__(self, reply: str = "Queued reply") -> None:
        self._reply = reply
        self.calls: list[dict[str, Any]] = []

    async def execute_mission(self, **kwargs: Any) -> ExecutionResult:
        self.calls.append(kwargs)
        return ExecutionResult(
            session_id=kwargs["session_id"],
            status="completed",
            final_message=self._reply,
        )


class FakeSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict[str, Any] | None]] = []

    async def send(
        self,
        *,
        recipient_id: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.sent.append((recipient_id, message, metadata))


@pytest.fixture
def queue_setup(tmp_path):
    """Build gateway with RequestQueue and ConversationManager."""
    conv_store = FileConversationStore(work_dir=str(tmp_path))
    conv_manager = ConversationManager(conv_store)
    legacy_store = InMemoryConversationStore()
    registry = InMemoryRecipientRegistry()
    sender = FakeSender()
    executor = FakeExecutor()
    queue = RequestQueue(max_size=50)

    gateway = CommunicationGateway(
        executor=executor,
        conversation_store=legacy_store,
        recipient_registry=registry,
        outbound_senders={"telegram": sender},
        conversation_manager=conv_manager,
        request_queue=queue,
    )

    # Start the processor in background.
    processor = RequestProcessor(queue, executor, conversation_manager=conv_manager)
    return gateway, queue, processor, conv_manager, legacy_store, sender, executor


@pytest.mark.asyncio
async def test_gateway_routes_via_queue(queue_setup) -> None:
    gateway, queue, processor, conv_mgr, legacy_store, sender, executor = queue_setup

    task = asyncio.create_task(processor.run())
    try:
        msg = InboundMessage(
            channel="telegram",
            conversation_id="chat-42",
            message="Hello via queue!",
            sender_id="user-1",
        )
        response = await asyncio.wait_for(gateway.handle_message(msg), timeout=5.0)

        assert response.reply == "Queued reply"
        assert response.status == "completed"
        assert response.conversation_id is not None
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_queue_preserves_conversation_history(queue_setup) -> None:
    gateway, queue, processor, conv_mgr, legacy_store, sender, executor = queue_setup

    task = asyncio.create_task(processor.run())
    try:
        msg1 = InboundMessage(
            channel="telegram",
            conversation_id="chat-42",
            message="First",
            sender_id="user-1",
        )
        resp1 = await asyncio.wait_for(gateway.handle_message(msg1), timeout=5.0)

        msg2 = InboundMessage(
            channel="telegram",
            conversation_id="chat-42",
            message="Second",
            sender_id="user-1",
        )
        resp2 = await asyncio.wait_for(gateway.handle_message(msg2), timeout=5.0)

        # Same conversation.
        assert resp1.conversation_id == resp2.conversation_id

        # Full history.
        messages = await conv_mgr.get_messages(resp2.conversation_id)
        assert len(messages) == 4  # 2 user + 2 assistant
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_queue_syncs_to_legacy_store(queue_setup) -> None:
    gateway, queue, processor, conv_mgr, legacy_store, sender, executor = queue_setup

    task = asyncio.create_task(processor.run())
    try:
        msg = InboundMessage(
            channel="telegram",
            conversation_id="chat-42",
            message="Sync test",
            sender_id="user-1",
        )
        await asyncio.wait_for(gateway.handle_message(msg), timeout=5.0)

        legacy_history = await legacy_store.load_history("telegram", "chat-42")
        assert len(legacy_history) == 2
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_queue_sends_outbound_reply(queue_setup) -> None:
    gateway, queue, processor, conv_mgr, legacy_store, sender, executor = queue_setup

    task = asyncio.create_task(processor.run())
    try:
        msg = InboundMessage(
            channel="telegram",
            conversation_id="chat-42",
            message="Outbound test",
        )
        await asyncio.wait_for(gateway.handle_message(msg), timeout=5.0)

        assert len(sender.sent) == 1
        assert sender.sent[0][1] == "Queued reply"
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_queue_reuses_stable_session_id(queue_setup) -> None:
    """P1: Executor receives the gateway-resolved session_id, not request_id."""
    gateway, queue, processor, conv_mgr, legacy_store, sender, executor = queue_setup

    task = asyncio.create_task(processor.run())
    try:
        msg1 = InboundMessage(
            channel="telegram",
            conversation_id="chat-42",
            message="First",
            sender_id="user-1",
        )
        resp1 = await asyncio.wait_for(gateway.handle_message(msg1), timeout=5.0)

        msg2 = InboundMessage(
            channel="telegram",
            conversation_id="chat-42",
            message="Second",
            sender_id="user-1",
        )
        resp2 = await asyncio.wait_for(gateway.handle_message(msg2), timeout=5.0)

        # Both gateway responses report the same session_id.
        assert resp1.session_id == resp2.session_id

        # Both executor calls received that same stable session_id.
        assert len(executor.calls) == 2
        assert executor.calls[0]["session_id"] == resp1.session_id
        assert executor.calls[1]["session_id"] == resp2.session_id
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_queue_preserves_gateway_options(queue_setup) -> None:
    """P2: All GatewayOptions fields are forwarded to the executor."""
    gateway, queue, processor, conv_mgr, legacy_store, sender, executor = queue_setup

    task = asyncio.create_task(processor.run())
    try:
        msg = InboundMessage(
            channel="telegram",
            conversation_id="chat-42",
            message="With options",
            sender_id="user-1",
        )
        options = GatewayOptions(
            profile="coding_agent",
            user_context={"org_id": "acme"},
            agent_id="custom-agent-1",
            planning_strategy="spar",
            planning_strategy_params={"max_plan_steps": 5},
            plugin_path="/path/to/plugin",
        )
        await asyncio.wait_for(gateway.handle_message(msg, options), timeout=5.0)

        assert len(executor.calls) == 1
        call = executor.calls[0]
        assert call["profile"] == "coding_agent"
        assert call["user_context"] == {"org_id": "acme"}
        assert call["agent_id"] == "custom-agent-1"
        assert call["planning_strategy"] == "spar"
        assert call["planning_strategy_params"] == {"max_plan_steps": 5}
        assert call["plugin_path"] == "/path/to/plugin"
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_gateway_without_queue_uses_direct_execution() -> None:
    """When no queue is provided, gateway uses direct execution (Phase 3 path)."""
    legacy_store = InMemoryConversationStore()
    registry = InMemoryRecipientRegistry()
    executor = FakeExecutor(reply="Direct reply")
    gateway = CommunicationGateway(
        executor=executor,
        conversation_store=legacy_store,
        recipient_registry=registry,
    )

    msg = InboundMessage(channel="rest", conversation_id="api-1", message="Hello")
    response = await gateway.handle_message(msg)

    assert response.reply == "Direct reply"
    assert response.conversation_id is None  # No ConversationManager
