"""Tests for CommunicationGateway."""

from typing import Any

import pytest

from taskforce.application.gateway import CommunicationGateway
from taskforce.core.domain.gateway import (
    GatewayOptions,
    InboundMessage,
    NotificationRequest,
)
from taskforce.core.domain.models import ExecutionResult
from taskforce_extensions.infrastructure.communication.gateway_conversation_store import (
    InMemoryConversationStore,
)
from taskforce_extensions.infrastructure.communication.recipient_registry import (
    InMemoryRecipientRegistry,
)


class FakeExecutor:
    """Minimal executor stub returning a canned response."""

    async def execute_mission(self, **kwargs: Any) -> ExecutionResult:
        return ExecutionResult(
            session_id=kwargs["session_id"],
            status="completed",
            final_message="Agent reply",
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
def gateway_parts():
    """Build gateway with in-memory stores and a fake sender."""
    store = InMemoryConversationStore()
    registry = InMemoryRecipientRegistry()
    sender = FakeSender()
    gateway = CommunicationGateway(
        executor=FakeExecutor(),
        conversation_store=store,
        recipient_registry=registry,
        outbound_senders={"telegram": sender},
    )
    return gateway, store, registry, sender


@pytest.mark.asyncio
async def test_handle_message_creates_session_and_persists_history(
    gateway_parts,
) -> None:
    gateway, store, registry, sender = gateway_parts

    msg = InboundMessage(
        channel="telegram",
        conversation_id="chat-42",
        message="Hallo!",
        sender_id="user-1",
    )
    response = await gateway.handle_message(msg)

    assert response.reply == "Agent reply"
    assert response.status == "completed"
    assert response.session_id

    # History should contain user + assistant messages
    history = await store.load_history("telegram", "chat-42")
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "Hallo!"}
    assert history[1] == {"role": "assistant", "content": "Agent reply"}


@pytest.mark.asyncio
async def test_handle_message_sends_outbound_reply(gateway_parts) -> None:
    gateway, store, registry, sender = gateway_parts

    msg = InboundMessage(
        channel="telegram",
        conversation_id="chat-42",
        message="Status?",
    )
    await gateway.handle_message(msg)

    assert len(sender.sent) == 1
    recipient_id, message, metadata = sender.sent[0]
    assert recipient_id == "chat-42"
    assert message == "Agent reply"
    assert metadata == {"status": "completed"}


@pytest.mark.asyncio
async def test_handle_message_auto_registers_recipient(gateway_parts) -> None:
    gateway, store, registry, sender = gateway_parts

    msg = InboundMessage(
        channel="telegram",
        conversation_id="chat-42",
        message="Hi",
        sender_id="user-99",
    )
    await gateway.handle_message(msg)

    ref = await registry.resolve(channel="telegram", user_id="user-99")
    assert ref is not None
    assert ref["conversation_id"] == "chat-42"


@pytest.mark.asyncio
async def test_handle_message_resumes_existing_session(gateway_parts) -> None:
    gateway, store, registry, sender = gateway_parts

    msg1 = InboundMessage(channel="telegram", conversation_id="chat-42", message="First")
    resp1 = await gateway.handle_message(msg1)

    msg2 = InboundMessage(channel="telegram", conversation_id="chat-42", message="Second")
    resp2 = await gateway.handle_message(msg2)

    assert resp1.session_id == resp2.session_id

    history = await store.load_history("telegram", "chat-42")
    assert len(history) == 4  # 2 user + 2 assistant


@pytest.mark.asyncio
async def test_handle_message_with_explicit_session_id(gateway_parts) -> None:
    gateway, store, registry, sender = gateway_parts

    msg = InboundMessage(channel="telegram", conversation_id="chat-42", message="Hi")
    options = GatewayOptions(session_id="explicit-session-123")
    response = await gateway.handle_message(msg, options)

    assert response.session_id == "explicit-session-123"


@pytest.mark.asyncio
async def test_send_notification_success(gateway_parts) -> None:
    gateway, store, registry, sender = gateway_parts

    # Register a recipient first
    await registry.register(
        channel="telegram",
        user_id="user-77",
        reference={"conversation_id": "chat-77"},
    )

    request = NotificationRequest(
        channel="telegram",
        recipient_id="user-77",
        message="Dein Report ist fertig!",
    )
    result = await gateway.send_notification(request)

    assert result.success
    assert result.channel == "telegram"
    assert result.recipient_id == "user-77"

    assert len(sender.sent) == 1
    assert sender.sent[0][0] == "chat-77"  # uses conversation_id from reference
    assert sender.sent[0][1] == "Dein Report ist fertig!"


@pytest.mark.asyncio
async def test_send_notification_no_sender(gateway_parts) -> None:
    gateway, store, registry, sender = gateway_parts

    request = NotificationRequest(
        channel="slack",  # no sender configured
        recipient_id="user-1",
        message="test",
    )
    result = await gateway.send_notification(request)

    assert not result.success
    assert "No outbound sender" in result.error


@pytest.mark.asyncio
async def test_send_notification_unregistered_recipient(gateway_parts) -> None:
    gateway, store, registry, sender = gateway_parts

    request = NotificationRequest(
        channel="telegram",
        recipient_id="unknown-user",
        message="test",
    )
    result = await gateway.send_notification(request)

    assert not result.success
    assert "not registered" in result.error


@pytest.mark.asyncio
async def test_broadcast(gateway_parts) -> None:
    gateway, store, registry, sender = gateway_parts

    await registry.register(
        channel="telegram",
        user_id="user-1",
        reference={"conversation_id": "chat-1"},
    )
    await registry.register(
        channel="telegram",
        user_id="user-2",
        reference={"conversation_id": "chat-2"},
    )

    results = await gateway.broadcast(channel="telegram", message="Broadcast!")

    assert len(results) == 2
    assert all(r.success for r in results)
    assert len(sender.sent) == 2


@pytest.mark.asyncio
async def test_supported_channels(gateway_parts) -> None:
    gateway, _, _, _ = gateway_parts
    assert "telegram" in gateway.supported_channels()


@pytest.mark.asyncio
async def test_no_outbound_for_unconfigured_channel() -> None:
    """Gateway works without outbound sender -- just no push."""
    store = InMemoryConversationStore()
    registry = InMemoryRecipientRegistry()
    gateway = CommunicationGateway(
        executor=FakeExecutor(),
        conversation_store=store,
        recipient_registry=registry,
        outbound_senders={},
    )

    msg = InboundMessage(channel="rest", conversation_id="api-call-1", message="Hello")
    response = await gateway.handle_message(msg)
    assert response.reply == "Agent reply"
