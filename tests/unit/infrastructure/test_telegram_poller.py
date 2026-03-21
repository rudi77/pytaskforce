"""Unit tests for TelegramPoller (getUpdates long-polling)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from taskforce.infrastructure.communication.telegram_poller import (
    TelegramPoller,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def pending_store() -> AsyncMock:
    """Mock PendingChannelQuestionStore."""
    store = AsyncMock()
    store.resolve = AsyncMock(return_value=None)
    return store


@pytest.fixture
def outbound_sender() -> AsyncMock:
    """Mock TelegramOutboundSender."""
    sender = AsyncMock()
    sender.send = AsyncMock()
    return sender


@pytest.fixture
def recipient_registry() -> AsyncMock:
    """Mock RecipientRegistry."""
    registry = AsyncMock()
    registry.register = AsyncMock()
    return registry


@pytest.fixture
def inbound_message_handler() -> AsyncMock:
    """Mock inbound Telegram message handler."""
    return AsyncMock()


@pytest.fixture
def poller(
    pending_store: AsyncMock,
    outbound_sender: AsyncMock,
    recipient_registry: AsyncMock,
    inbound_message_handler: AsyncMock,
) -> TelegramPoller:
    return TelegramPoller(
        bot_token="123:FAKE",
        pending_store=pending_store,
        outbound_sender=outbound_sender,
        recipient_registry=recipient_registry,
        inbound_message_handler=inbound_message_handler,
        poll_timeout=0,
    )


def _make_update(
    update_id: int,
    chat_id: int,
    sender_id: int,
    text: str,
) -> dict[str, Any]:
    """Build a minimal Telegram Update object."""
    return {
        "update_id": update_id,
        "message": {
            "chat": {"id": chat_id},
            "from": {"id": sender_id},
            "text": text,
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_update_resolves_pending_question(
    poller: TelegramPoller,
    pending_store: AsyncMock,
    outbound_sender: AsyncMock,
    recipient_registry: AsyncMock,
):
    """When a pending question exists, the poller resolves it and sends ack."""
    pending_store.resolve.return_value = "session-42"

    update = _make_update(
        update_id=1,
        chat_id=100,
        sender_id=200,
        text="2026-01-15",
    )
    await poller._handle_update(update)

    pending_store.resolve.assert_called_once_with(
        channel="telegram",
        sender_id="200",
        response="2026-01-15",
    )
    recipient_registry.register.assert_called_once_with(
        channel="telegram",
        user_id="200",
        reference={"conversation_id": "100"},
    )

    # Acknowledgment sent
    outbound_sender.send.assert_called_once_with(
        recipient_id="100",
        message="✅ Danke, Ihre Antwort wurde weitergeleitet.",
    )


@pytest.mark.asyncio
async def test_handle_update_no_pending_question(
    poller: TelegramPoller,
    pending_store: AsyncMock,
    outbound_sender: AsyncMock,
    recipient_registry: AsyncMock,
    inbound_message_handler: AsyncMock,
):
    """When no pending question exists, the inbound handler is called."""
    pending_store.resolve.return_value = None

    update = _make_update(
        update_id=2,
        chat_id=100,
        sender_id=200,
        text="Hello",
    )
    await poller._handle_update(update)

    # The inbound handler is fire-and-forget via asyncio.create_task,
    # so we need to let the event loop run the background task.
    await asyncio.sleep(0)

    pending_store.resolve.assert_called_once()
    recipient_registry.register.assert_called_once_with(
        channel="telegram",
        user_id="200",
        reference={"conversation_id": "100"},
    )
    outbound_sender.send.assert_not_called()
    inbound_message_handler.assert_awaited_once_with("100", "200", "Hello", None)


@pytest.mark.asyncio
async def test_handle_update_skips_empty_text(
    poller: TelegramPoller,
    pending_store: AsyncMock,
):
    """Updates without text are skipped."""
    update = {
        "update_id": 3,
        "message": {
            "chat": {"id": 100},
            "from": {"id": 200},
            # no text
        },
    }
    await poller._handle_update(update)
    pending_store.resolve.assert_not_called()


@pytest.mark.asyncio
async def test_handle_update_skips_no_message(
    poller: TelegramPoller,
    pending_store: AsyncMock,
):
    """Updates without a message object are skipped."""
    update = {"update_id": 4}
    await poller._handle_update(update)
    pending_store.resolve.assert_not_called()


@pytest.mark.asyncio
async def test_offset_advances(poller: TelegramPoller, pending_store: AsyncMock):
    """The offset advances past processed updates."""
    u1 = _make_update(update_id=10, chat_id=1, sender_id=2, text="a")
    u2 = _make_update(update_id=15, chat_id=1, sender_id=2, text="b")

    await poller._handle_update(u1)
    assert poller._offset == 11

    await poller._handle_update(u2)
    assert poller._offset == 16


@pytest.mark.asyncio
async def test_start_and_stop(poller: TelegramPoller):
    """Poller can be started and stopped without errors."""
    # Patch HTTP calls to avoid real network access
    with patch.object(poller, "_delete_webhook", new_callable=AsyncMock):
        with patch.object(poller, "_get_updates", new_callable=AsyncMock) as mock_get:
            # Return empty updates, then block
            mock_get.side_effect = [[], asyncio.CancelledError()]

            await poller.start()
            assert poller._task is not None

            await poller.stop()
            assert poller._task is None


@pytest.mark.asyncio
async def test_ack_failure_does_not_crash(
    poller: TelegramPoller,
    pending_store: AsyncMock,
    outbound_sender: AsyncMock,
):
    """If the acknowledgment send fails, the poller continues."""
    pending_store.resolve.return_value = "session-42"
    outbound_sender.send.side_effect = ConnectionError("network error")

    update = _make_update(
        update_id=5,
        chat_id=100,
        sender_id=200,
        text="answer",
    )
    # Should not raise
    await poller._handle_update(update)

    pending_store.resolve.assert_called_once()


@pytest.mark.asyncio
async def test_no_outbound_sender(pending_store: AsyncMock):
    """Poller works without an outbound sender (no ack sent)."""
    poller = TelegramPoller(
        bot_token="123:FAKE",
        pending_store=pending_store,
        outbound_sender=None,
    )
    pending_store.resolve.return_value = "session-42"

    update = _make_update(
        update_id=6,
        chat_id=100,
        sender_id=200,
        text="answer",
    )
    await poller._handle_update(update)

    pending_store.resolve.assert_called_once()


@pytest.mark.asyncio
async def test_voice_message_transcribed(
    pending_store: AsyncMock,
    outbound_sender: AsyncMock,
    recipient_registry: AsyncMock,
    inbound_message_handler: AsyncMock,
):
    """Voice messages are transcribed to text when STT service is provided."""
    mock_stt = AsyncMock()
    mock_stt.transcribe = AsyncMock(return_value="Hallo, wie geht es dir?")

    poller = TelegramPoller(
        bot_token="123:FAKE",
        pending_store=pending_store,
        outbound_sender=outbound_sender,
        recipient_registry=recipient_registry,
        inbound_message_handler=inbound_message_handler,
        speech_to_text=mock_stt,
        poll_timeout=0,
    )

    # Mock the file downloader to return fake audio bytes.
    poller._file_downloader = AsyncMock()
    poller._file_downloader.download_bytes = AsyncMock(return_value=b"fake-ogg-data")

    pending_store.resolve.return_value = None

    update = {
        "update_id": 20,
        "message": {
            "chat": {"id": 100},
            "from": {"id": 200},
            "voice": {
                "file_id": "voice-file-123",
                "duration": 5,
            },
        },
    }
    await poller._handle_update(update)

    # Let fire-and-forget task run.
    await asyncio.sleep(0)

    mock_stt.transcribe.assert_awaited_once()
    # The transcribed text should be passed as the message.
    inbound_message_handler.assert_awaited_once_with("100", "200", "Hallo, wie geht es dir?", None)


@pytest.mark.asyncio
async def test_voice_message_skipped_without_stt(
    pending_store: AsyncMock,
    outbound_sender: AsyncMock,
    recipient_registry: AsyncMock,
    inbound_message_handler: AsyncMock,
):
    """Voice messages are ignored when no STT service is configured."""
    poller = TelegramPoller(
        bot_token="123:FAKE",
        pending_store=pending_store,
        outbound_sender=outbound_sender,
        recipient_registry=recipient_registry,
        inbound_message_handler=inbound_message_handler,
        speech_to_text=None,
        poll_timeout=0,
    )

    update = {
        "update_id": 21,
        "message": {
            "chat": {"id": 100},
            "from": {"id": 200},
            "voice": {
                "file_id": "voice-file-456",
                "duration": 3,
            },
        },
    }
    await poller._handle_update(update)

    # No text and no attachments → update is skipped.
    pending_store.resolve.assert_not_called()


@pytest.mark.asyncio
async def test_voice_message_with_text_caption(
    pending_store: AsyncMock,
    outbound_sender: AsyncMock,
    recipient_registry: AsyncMock,
    inbound_message_handler: AsyncMock,
):
    """Voice message with caption combines both texts."""
    mock_stt = AsyncMock()
    mock_stt.transcribe = AsyncMock(return_value="transcribed speech")

    poller = TelegramPoller(
        bot_token="123:FAKE",
        pending_store=pending_store,
        outbound_sender=outbound_sender,
        recipient_registry=recipient_registry,
        inbound_message_handler=inbound_message_handler,
        speech_to_text=mock_stt,
        poll_timeout=0,
    )
    poller._file_downloader = AsyncMock()
    poller._file_downloader.download_bytes = AsyncMock(return_value=b"audio")

    pending_store.resolve.return_value = None

    update = {
        "update_id": 22,
        "message": {
            "chat": {"id": 100},
            "from": {"id": 200},
            "caption": "Listen to this",
            "voice": {
                "file_id": "voice-file-789",
                "duration": 2,
            },
        },
    }
    await poller._handle_update(update)
    await asyncio.sleep(0)

    call_args = inbound_message_handler.call_args
    message_text = call_args[0][2]
    assert "Listen to this" in message_text
    assert "transcribed speech" in message_text
