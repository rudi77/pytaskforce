"""Tests for CommunicationGateway with ConversationManager (ADR-016 Phase 3)."""

from typing import Any

import pytest

from taskforce.application.conversation_manager import ConversationManager
from taskforce.application.gateway import CommunicationGateway
from taskforce.core.domain.gateway import (
    GatewayOptions,
    InboundMessage,
)
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


class FakeSender:
    """Records all sent messages for assertions."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict[str, Any] | None]] = []

    @property
    def channel(self) -> str:
        return "telegram"

    async def send(
        self,
        *,
        recipient_id: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.sent.append((recipient_id, message, metadata))


@pytest.fixture
def conv_manager(tmp_path):
    """ConversationManager backed by a temporary file store."""
    store = FileConversationStore(work_dir=str(tmp_path))
    return ConversationManager(store)


@pytest.fixture
def gateway_with_conv_manager(conv_manager):
    """Build gateway with ConversationManager wired in."""
    legacy_store = InMemoryConversationStore()
    registry = InMemoryRecipientRegistry()
    sender = FakeSender()
    executor = FakeExecutor()
    gateway = CommunicationGateway(
        executor=executor,
        conversation_store=legacy_store,
        recipient_registry=registry,
        outbound_senders={"telegram": sender},
        conversation_manager=conv_manager,
    )
    return gateway, conv_manager, legacy_store, registry, sender, executor


@pytest.mark.asyncio
async def test_handle_message_uses_conversation_manager(
    gateway_with_conv_manager,
) -> None:
    gateway, conv_mgr, legacy_store, registry, sender, executor = gateway_with_conv_manager

    msg = InboundMessage(
        channel="telegram",
        conversation_id="chat-42",
        message="Hallo!",
        sender_id="user-1",
    )
    response = await gateway.handle_message(msg)

    # Response includes conversation_id.
    assert response.conversation_id is not None
    assert response.reply == "Agent reply"
    assert response.status == "completed"

    # Messages stored via ConversationManager.
    messages = await conv_mgr.get_messages(response.conversation_id)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hallo!"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "Agent reply"


@pytest.mark.asyncio
async def test_conversation_persists_across_messages(
    gateway_with_conv_manager,
) -> None:
    gateway, conv_mgr, *_ = gateway_with_conv_manager

    msg1 = InboundMessage(
        channel="telegram",
        conversation_id="chat-42",
        message="First",
        sender_id="user-1",
    )
    resp1 = await gateway.handle_message(msg1)

    msg2 = InboundMessage(
        channel="telegram",
        conversation_id="chat-42",
        message="Second",
        sender_id="user-1",
    )
    resp2 = await gateway.handle_message(msg2)

    # Same conversation.
    assert resp1.conversation_id == resp2.conversation_id

    # Full history.
    messages = await conv_mgr.get_messages(resp2.conversation_id)
    assert len(messages) == 4  # 2 user + 2 assistant


@pytest.mark.asyncio
async def test_different_senders_get_separate_conversations(
    gateway_with_conv_manager,
) -> None:
    gateway, conv_mgr, *_ = gateway_with_conv_manager

    msg_a = InboundMessage(
        channel="telegram",
        conversation_id="chat-a",
        message="Hi from A",
        sender_id="user-a",
    )
    resp_a = await gateway.handle_message(msg_a)

    msg_b = InboundMessage(
        channel="telegram",
        conversation_id="chat-b",
        message="Hi from B",
        sender_id="user-b",
    )
    resp_b = await gateway.handle_message(msg_b)

    assert resp_a.conversation_id != resp_b.conversation_id


@pytest.mark.asyncio
async def test_legacy_store_also_receives_history(
    gateway_with_conv_manager,
) -> None:
    """Backward compat: legacy ConversationStore is also updated."""
    gateway, conv_mgr, legacy_store, *_ = gateway_with_conv_manager

    msg = InboundMessage(
        channel="telegram",
        conversation_id="chat-42",
        message="Test",
        sender_id="user-1",
    )
    await gateway.handle_message(msg)

    legacy_history = await legacy_store.load_history("telegram", "chat-42")
    assert len(legacy_history) == 2


@pytest.mark.asyncio
async def test_outbound_reply_sent(
    gateway_with_conv_manager,
) -> None:
    gateway, conv_mgr, legacy_store, registry, sender, executor = gateway_with_conv_manager

    msg = InboundMessage(
        channel="telegram",
        conversation_id="chat-42",
        message="Status?",
    )
    await gateway.handle_message(msg)

    assert len(sender.sent) == 1
    assert sender.sent[0][1] == "Agent reply"


@pytest.mark.asyncio
async def test_executor_receives_full_conversation_history(
    gateway_with_conv_manager,
) -> None:
    gateway, conv_mgr, legacy_store, registry, sender, executor = gateway_with_conv_manager

    msg1 = InboundMessage(channel="telegram", conversation_id="chat-42", message="First")
    await gateway.handle_message(msg1)

    msg2 = InboundMessage(channel="telegram", conversation_id="chat-42", message="Second")
    await gateway.handle_message(msg2)

    # Second call should receive full history (user1 + assistant1 + user2).
    second_call = executor.calls[1]
    history = second_call["conversation_history"]
    assert len(history) == 3
    assert history[0]["content"] == "First"
    assert history[1]["content"] == "Agent reply"
    assert history[2]["content"] == "Second"


@pytest.mark.asyncio
async def test_gateway_without_conversation_manager_returns_no_conversation_id() -> None:
    """Legacy mode: no ConversationManager → conversation_id is None."""
    legacy_store = InMemoryConversationStore()
    registry = InMemoryRecipientRegistry()
    gateway = CommunicationGateway(
        executor=FakeExecutor(),
        conversation_store=legacy_store,
        recipient_registry=registry,
    )

    msg = InboundMessage(channel="rest", conversation_id="api-1", message="Hello")
    response = await gateway.handle_message(msg)

    assert response.conversation_id is None
    assert response.reply == "Agent reply"
