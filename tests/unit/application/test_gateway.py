"""Tests for CommunicationGateway."""

from typing import Any

import pytest

from taskforce.application.gateway import (
    CommunicationGateway,
    _append_message,
    _build_multimodal_content,
)
from taskforce.core.domain.gateway import (
    GatewayOptions,
    InboundMessage,
    NotificationRequest,
)
from taskforce.core.domain.models import ExecutionResult
from taskforce.infrastructure.communication.gateway_conversation_store import (
    InMemoryConversationStore,
)
from taskforce.infrastructure.communication.recipient_registry import (
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


class FailingSender:
    """Sender that raises ConnectionError to test error propagation."""

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
        raise ConnectionError("Telegram API returned HTTP 403: bot blocked by user")


@pytest.mark.asyncio
async def test_send_notification_sender_raises_returns_failure() -> None:
    """When the OutboundSender raises, send_notification returns failure."""
    store = InMemoryConversationStore()
    registry = InMemoryRecipientRegistry()
    gateway = CommunicationGateway(
        executor=FakeExecutor(),
        conversation_store=store,
        recipient_registry=registry,
        outbound_senders={"telegram": FailingSender()},
    )

    await registry.register(
        channel="telegram",
        user_id="user-1",
        reference={"conversation_id": "chat-1"},
    )

    result = await gateway.send_notification(
        NotificationRequest(
            channel="telegram",
            recipient_id="user-1",
            message="This will fail",
        )
    )

    assert not result.success
    assert "HTTP 403" in result.error


@pytest.mark.asyncio
async def test_handle_message_outbound_failure_does_not_lose_response() -> None:
    """When outbound reply fails, the gateway response is still returned."""
    store = InMemoryConversationStore()
    registry = InMemoryRecipientRegistry()
    gateway = CommunicationGateway(
        executor=FakeExecutor(),
        conversation_store=store,
        recipient_registry=registry,
        outbound_senders={"telegram": FailingSender()},
    )

    msg = InboundMessage(channel="telegram", conversation_id="chat-42", message="Hi")
    response = await gateway.handle_message(msg)

    # Response should still be returned even though outbound failed
    assert response.reply == "Agent reply"
    assert response.status == "completed"

    # History should still be persisted
    history = await store.load_history("telegram", "chat-42")
    assert len(history) == 2


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


# ---------------------------------------------------------------------------
# Pending channel question tests
# ---------------------------------------------------------------------------


class FakePendingStore:
    """In-memory pending channel question store for testing."""

    def __init__(self) -> None:
        self._questions: dict[str, dict[str, Any]] = {}
        self._index: dict[str, str] = {}  # channel:recipient_id -> session_id

    async def register(
        self,
        *,
        session_id: str,
        channel: str,
        recipient_id: str,
        question: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        key = f"{channel}:{recipient_id}"
        self._questions[session_id] = {
            "channel": channel,
            "recipient_id": recipient_id,
            "question": question,
            "response": None,
        }
        self._index[key] = session_id

    async def resolve(
        self, *, channel: str, sender_id: str, response: str
    ) -> str | None:
        key = f"{channel}:{sender_id}"
        session_id = self._index.get(key)
        if not session_id or session_id not in self._questions:
            return None
        entry = self._questions[session_id]
        if entry["response"] is not None:
            return None
        entry["response"] = response
        self._index.pop(key, None)
        return session_id

    async def get_response(self, *, session_id: str) -> str | None:
        entry = self._questions.get(session_id)
        if not entry:
            return None
        return entry["response"]

    async def remove(self, *, session_id: str) -> None:
        entry = self._questions.pop(session_id, None)
        if entry:
            key = f"{entry['channel']}:{entry['recipient_id']}"
            self._index.pop(key, None)


@pytest.fixture
def gateway_with_pending():
    """Build gateway with pending channel question store."""
    store = InMemoryConversationStore()
    registry = InMemoryRecipientRegistry()
    sender = FakeSender()
    pending = FakePendingStore()
    gateway = CommunicationGateway(
        executor=FakeExecutor(),
        conversation_store=store,
        recipient_registry=registry,
        outbound_senders={"telegram": sender},
        pending_channel_store=pending,
    )
    return gateway, store, registry, sender, pending


@pytest.mark.asyncio
async def test_inbound_resolves_pending_question(gateway_with_pending) -> None:
    """When a message matches a pending question, resolve instead of new execution."""
    gateway, store, registry, sender, pending = gateway_with_pending

    # Register a pending question
    await pending.register(
        session_id="paused-sess-1",
        channel="telegram",
        recipient_id="user-42",
        question="What is the invoice date?",
    )

    # Inbound message from the same user on the same channel
    msg = InboundMessage(
        channel="telegram",
        conversation_id="chat-42",
        message="2026-01-15",
        sender_id="user-42",
    )
    response = await gateway.handle_message(msg)

    assert response.status == "channel_response_received"
    assert response.session_id == "paused-sess-1"

    # The response should be stored
    stored_response = await pending.get_response(session_id="paused-sess-1")
    assert stored_response == "2026-01-15"


@pytest.mark.asyncio
async def test_inbound_no_pending_question_runs_normally(gateway_with_pending) -> None:
    """Without a pending question, normal agent execution happens."""
    gateway, store, registry, sender, pending = gateway_with_pending

    msg = InboundMessage(
        channel="telegram",
        conversation_id="chat-42",
        message="Hello!",
        sender_id="user-42",
    )
    response = await gateway.handle_message(msg)

    assert response.status == "completed"
    assert response.reply == "Agent reply"


@pytest.mark.asyncio
async def test_send_channel_question(gateway_with_pending) -> None:
    """Test sending a channel question via the gateway."""
    gateway, store, registry, sender, pending = gateway_with_pending

    # Register recipient first
    await registry.register(
        channel="telegram",
        user_id="user-42",
        reference={"conversation_id": "chat-42"},
    )

    success = await gateway.send_channel_question(
        session_id="sess-1",
        channel="telegram",
        recipient_id="user-42",
        question="What is the invoice date?",
    )

    assert success

    # Question should have been sent via the sender
    assert len(sender.sent) == 1
    assert "invoice date" in sender.sent[0][1]

    # Question should be registered as pending
    # (We can verify by resolving it)
    result = await pending.resolve(
        channel="telegram", sender_id="user-42", response="2026-01-15"
    )
    assert result == "sess-1"


@pytest.mark.asyncio
async def test_send_channel_question_fallback_single_recipient(
    gateway_with_pending,
) -> None:
    """Fallback to the only known recipient when model sends a bad ID."""
    gateway, store, registry, sender, pending = gateway_with_pending

    await registry.register(
        channel="telegram",
        user_id="5865840420",
        reference={"conversation_id": "5865840420"},
    )

    success = await gateway.send_channel_question(
        session_id="sess-1",
        channel="telegram",
        recipient_id="musterbetrieb",
        question="Bitte fehlende Angaben nachreichen.",
    )

    assert success
    assert len(sender.sent) == 1
    assert "fehlende Angaben" in sender.sent[0][1]

    result = await pending.resolve(
        channel="telegram",
        sender_id="5865840420",
        response="Kommt sofort",
    )
    assert result == "sess-1"


@pytest.mark.asyncio
async def test_send_channel_question_fallback_by_conversation_id(
    gateway_with_pending,
) -> None:
    """Fallback resolves user_id when model passed conversation_id."""
    gateway, store, registry, sender, pending = gateway_with_pending

    await registry.register(
        channel="telegram",
        user_id="user-42",
        reference={"conversation_id": "chat-42"},
    )

    success = await gateway.send_channel_question(
        session_id="sess-2",
        channel="telegram",
        recipient_id="chat-42",
        question="Bitte antworten Sie kurz.",
    )

    assert success
    result = await pending.resolve(
        channel="telegram",
        sender_id="user-42",
        response="OK",
    )
    assert result == "sess-2"


@pytest.mark.asyncio
async def test_send_channel_question_fails_without_sender(gateway_with_pending) -> None:
    """Channel question fails when no outbound sender for channel."""
    gateway, store, registry, sender, pending = gateway_with_pending

    success = await gateway.send_channel_question(
        session_id="sess-1",
        channel="slack",  # no sender configured
        recipient_id="user-42",
        question="Test?",
    )

    assert not success


@pytest.mark.asyncio
async def test_poll_channel_response(gateway_with_pending) -> None:
    """Test polling for a channel response."""
    gateway, store, registry, sender, pending = gateway_with_pending

    await pending.register(
        session_id="sess-1",
        channel="telegram",
        recipient_id="user-42",
        question="Date?",
    )

    # Before resolve: no response
    result = await gateway.poll_channel_response(session_id="sess-1")
    assert result is None

    # Resolve the question
    await pending.resolve(
        channel="telegram", sender_id="user-42", response="2026-01-15"
    )

    # After resolve: response available
    result = await gateway.poll_channel_response(session_id="sess-1")
    assert result == "2026-01-15"


@pytest.mark.asyncio
async def test_clear_channel_question(gateway_with_pending) -> None:
    """Test clearing a pending channel question."""
    gateway, store, registry, sender, pending = gateway_with_pending

    await pending.register(
        session_id="sess-1",
        channel="telegram",
        recipient_id="user-42",
        question="Date?",
    )

    await gateway.clear_channel_question(session_id="sess-1")

    # After clearing, resolve should return None
    result = await pending.resolve(
        channel="telegram", sender_id="user-42", response="Answer"
    )
    assert result is None


@pytest.mark.asyncio
async def test_inbound_sends_acknowledgment(gateway_with_pending) -> None:
    """When resolving a pending question, an acknowledgment is sent back."""
    gateway, store, registry, sender, pending = gateway_with_pending

    await pending.register(
        session_id="paused-sess-1",
        channel="telegram",
        recipient_id="user-42",
        question="Invoice date?",
    )

    msg = InboundMessage(
        channel="telegram",
        conversation_id="chat-42",
        message="2026-01-15",
        sender_id="user-42",
    )
    await gateway.handle_message(msg)

    # Acknowledgment should have been sent
    assert len(sender.sent) == 1
    assert "Danke" in sender.sent[0][1] or "weitergeleitet" in sender.sent[0][1]


# ---------------------------------------------------------------------------
# Reset command tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["/start", "/new", "/reset", "/RESET", " /start "])
async def test_reset_commands_clear_history_and_return_welcome(
    gateway_parts, command: str
) -> None:
    """Reset commands (/start, /new, /reset) wipe history and return welcome."""
    gateway, store, registry, sender = gateway_parts

    # Seed some history first (session_id must be set before saving history)
    await store.set_session_id("telegram", "chat-42", "old-session")
    await store.save_history(
        "telegram",
        "chat-42",
        [{"role": "user", "content": "old message"}],
    )

    msg = InboundMessage(
        channel="telegram",
        conversation_id="chat-42",
        message=command,
        sender_id="user-1",
    )
    response = await gateway.handle_message(msg)

    assert response.status == "conversation_reset"
    assert "Willkommen" in response.reply
    assert response.history == []
    assert response.session_id == ""


@pytest.mark.asyncio
async def test_reset_sends_welcome_via_outbound(gateway_parts) -> None:
    """Reset sends a welcome message through the outbound sender."""
    gateway, store, registry, sender = gateway_parts

    msg = InboundMessage(
        channel="telegram",
        conversation_id="chat-42",
        message="/start",
    )
    await gateway.handle_message(msg)

    assert len(sender.sent) == 1
    assert sender.sent[0][0] == "chat-42"
    assert "Willkommen" in sender.sent[0][1]


@pytest.mark.asyncio
async def test_reset_welcome_failure_does_not_raise() -> None:
    """If outbound sender fails during reset, no exception propagates."""
    store = InMemoryConversationStore()
    registry = InMemoryRecipientRegistry()
    gateway = CommunicationGateway(
        executor=FakeExecutor(),
        conversation_store=store,
        recipient_registry=registry,
        outbound_senders={"telegram": FailingSender()},
    )

    msg = InboundMessage(
        channel="telegram",
        conversation_id="chat-42",
        message="/reset",
    )
    response = await gateway.handle_message(msg)

    assert response.status == "conversation_reset"


@pytest.mark.asyncio
async def test_reset_without_outbound_sender() -> None:
    """Reset works even when no outbound sender is configured."""
    store = InMemoryConversationStore()
    registry = InMemoryRecipientRegistry()
    gateway = CommunicationGateway(
        executor=FakeExecutor(),
        conversation_store=store,
        recipient_registry=registry,
    )

    msg = InboundMessage(
        channel="rest",
        conversation_id="api-1",
        message="/new",
    )
    response = await gateway.handle_message(msg)

    assert response.status == "conversation_reset"


# ---------------------------------------------------------------------------
# History trimming tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trim_history_limits_messages() -> None:
    """Conversation history is trimmed to max_conversation_history."""
    store = InMemoryConversationStore()
    registry = InMemoryRecipientRegistry()
    calls: list[dict[str, Any]] = []

    class CapturingExecutor:
        async def execute_mission(self, **kwargs: Any) -> ExecutionResult:
            calls.append(kwargs)
            return ExecutionResult(
                session_id=kwargs["session_id"],
                status="completed",
                final_message="Reply",
            )

    gateway = CommunicationGateway(
        executor=CapturingExecutor(),
        conversation_store=store,
        recipient_registry=registry,
        max_conversation_history=4,
    )

    # Seed history beyond the limit (session_id must be set before saving history)
    await store.set_session_id("telegram", "chat-1", "sess-1")
    big_history = [
        {"role": "user", "content": f"msg-{i}"} for i in range(10)
    ]
    await store.save_history("telegram", "chat-1", big_history)

    msg = InboundMessage(channel="telegram", conversation_id="chat-1", message="new")
    await gateway.handle_message(msg)

    # The conversation_history passed to execute should be trimmed
    passed_history = calls[0]["conversation_history"]
    assert len(passed_history) <= 4


# ---------------------------------------------------------------------------
# Module-level helper function tests
# ---------------------------------------------------------------------------


class TestBuildMultimodalContent:
    """Tests for _build_multimodal_content."""

    def test_no_attachments_returns_plain_text(self) -> None:
        result = _build_multimodal_content("Hello", None)
        assert result == "Hello"

    def test_empty_attachments_returns_plain_text(self) -> None:
        result = _build_multimodal_content("Hello", [])
        assert result == "Hello"

    def test_image_attachment_returns_content_array(self) -> None:
        attachments = [
            {"type": "image", "data_url": "data:image/png;base64,abc123"}
        ]
        result = _build_multimodal_content("Look at this", attachments)
        assert isinstance(result, list)
        assert result[0] == {"type": "text", "text": "Look at this"}
        assert result[1]["type"] == "image_url"
        assert result[1]["image_url"]["url"] == "data:image/png;base64,abc123"

    def test_document_attachment_returns_enriched_text(self) -> None:
        attachments = [
            {
                "type": "document",
                "file_path": "/tmp/invoice.pdf",
                "file_name": "invoice.pdf",
                "mime_type": "application/pdf",
            }
        ]
        result = _build_multimodal_content("Process this", attachments)
        assert isinstance(result, str)
        assert "invoice.pdf" in result
        assert "/tmp/invoice.pdf" in result
        assert "Process this" in result

    def test_mixed_image_and_document_returns_content_array(self) -> None:
        attachments = [
            {"type": "image", "data_url": "data:image/png;base64,abc"},
            {
                "type": "document",
                "file_path": "/tmp/doc.txt",
                "file_name": "doc.txt",
                "mime_type": "text/plain",
            },
        ]
        result = _build_multimodal_content("Mixed", attachments)
        assert isinstance(result, list)
        assert len(result) == 3  # text + image + doc reference text
        assert result[0]["type"] == "text"
        assert result[1]["type"] == "image_url"
        assert result[2]["type"] == "text"
        assert "doc.txt" in result[2]["text"]


class TestAppendMessage:
    """Tests for _append_message."""

    def test_appends_to_empty_history(self) -> None:
        result = _append_message([], "user", "Hello")
        assert result == [{"role": "user", "content": "Hello"}]

    def test_appends_without_mutating_original(self) -> None:
        original = [{"role": "user", "content": "first"}]
        result = _append_message(original, "assistant", "second")
        assert len(result) == 2
        assert len(original) == 1  # original not modified


# ---------------------------------------------------------------------------
# Edge cases for poll/clear without pending store
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poll_channel_response_without_store(gateway_parts) -> None:
    """poll_channel_response returns None when no pending store is configured."""
    gateway, _, _, _ = gateway_parts
    result = await gateway.poll_channel_response(session_id="any-session")
    assert result is None


@pytest.mark.asyncio
async def test_clear_channel_question_without_store(gateway_parts) -> None:
    """clear_channel_question is a no-op when no pending store is configured."""
    gateway, _, _, _ = gateway_parts
    # Should not raise
    await gateway.clear_channel_question(session_id="any-session")


# ---------------------------------------------------------------------------
# Notification with metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_notification_passes_metadata(gateway_parts) -> None:
    """Notification metadata is forwarded to the outbound sender."""
    gateway, store, registry, sender = gateway_parts

    await registry.register(
        channel="telegram",
        user_id="user-1",
        reference={"conversation_id": "chat-1"},
    )

    request = NotificationRequest(
        channel="telegram",
        recipient_id="user-1",
        message="Alert!",
        metadata={"parse_mode": "HTML"},
    )
    result = await gateway.send_notification(request)

    assert result.success
    assert sender.sent[0][2] == {"parse_mode": "HTML"}


# ---------------------------------------------------------------------------
# Broadcast edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broadcast_empty_recipients(gateway_parts) -> None:
    """Broadcast with no registered recipients returns empty list."""
    gateway, store, registry, sender = gateway_parts

    results = await gateway.broadcast(channel="telegram", message="Nobody here")
    assert results == []
    assert len(sender.sent) == 0


@pytest.mark.asyncio
async def test_broadcast_partial_failure() -> None:
    """Broadcast returns per-recipient results even when some fail."""
    store = InMemoryConversationStore()
    registry = InMemoryRecipientRegistry()

    call_count = 0

    class AlternatingSender:
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
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                raise ConnectionError("Intermittent failure")

    gateway = CommunicationGateway(
        executor=FakeExecutor(),
        conversation_store=store,
        recipient_registry=registry,
        outbound_senders={"telegram": AlternatingSender()},
    )

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

    results = await gateway.broadcast(channel="telegram", message="Test")
    assert len(results) == 2
    successes = [r for r in results if r.success]
    failures = [r for r in results if not r.success]
    assert len(successes) == 1
    assert len(failures) == 1


# ---------------------------------------------------------------------------
# Supported channels introspection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_supported_channels_empty() -> None:
    """supported_channels returns empty set when no senders configured."""
    store = InMemoryConversationStore()
    registry = InMemoryRecipientRegistry()
    gateway = CommunicationGateway(
        executor=FakeExecutor(),
        conversation_store=store,
        recipient_registry=registry,
    )
    assert gateway.supported_channels() == set()


@pytest.mark.asyncio
async def test_supported_channels_multiple() -> None:
    """supported_channels returns all configured channel names."""
    store = InMemoryConversationStore()
    registry = InMemoryRecipientRegistry()
    sender = FakeSender()
    gateway = CommunicationGateway(
        executor=FakeExecutor(),
        conversation_store=store,
        recipient_registry=registry,
        outbound_senders={"telegram": sender, "teams": sender},
    )
    assert gateway.supported_channels() == {"telegram", "teams"}


# ---------------------------------------------------------------------------
# Message handling with attachments (multimodal inbound)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_message_with_image_attachment(gateway_parts) -> None:
    """Inbound message with image attachment stores multimodal content."""
    gateway, store, registry, sender = gateway_parts

    msg = InboundMessage(
        channel="telegram",
        conversation_id="chat-42",
        message="What is this?",
        metadata={
            "attachments": [
                {"type": "image", "data_url": "data:image/png;base64,abc"}
            ]
        },
    )
    response = await gateway.handle_message(msg)
    assert response.status == "completed"

    history = await store.load_history("telegram", "chat-42")
    # User message content should be multimodal (list)
    assert isinstance(history[0]["content"], list)
    assert history[0]["content"][0]["type"] == "text"
    assert history[0]["content"][1]["type"] == "image_url"


@pytest.mark.asyncio
async def test_handle_message_with_document_attachment(gateway_parts) -> None:
    """Inbound message with document attachment appends file reference."""
    gateway, store, registry, sender = gateway_parts

    msg = InboundMessage(
        channel="telegram",
        conversation_id="chat-42",
        message="Process this file",
        metadata={
            "attachments": [
                {
                    "type": "document",
                    "file_path": "/tmp/report.pdf",
                    "file_name": "report.pdf",
                    "mime_type": "application/pdf",
                }
            ]
        },
    )
    response = await gateway.handle_message(msg)
    assert response.status == "completed"

    history = await store.load_history("telegram", "chat-42")
    user_content = history[0]["content"]
    assert isinstance(user_content, str)
    assert "report.pdf" in user_content
    assert "/tmp/report.pdf" in user_content
