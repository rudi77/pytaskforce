"""Unit tests for TelegramPoller (getUpdates long-polling)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskforce_extensions.infrastructure.communication.telegram_poller import (
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
def poller(pending_store: AsyncMock, outbound_sender: AsyncMock) -> TelegramPoller:
    return TelegramPoller(
        bot_token="123:FAKE",
        pending_store=pending_store,
        outbound_sender=outbound_sender,
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
):
    """When a pending question exists, the poller resolves it and sends ack."""
    pending_store.resolve.return_value = "session-42"

    update = _make_update(update_id=1, chat_id=100, sender_id=200, text="2026-01-15")
    await poller._handle_update(update)

    pending_store.resolve.assert_called_once_with(
        channel="telegram",
        sender_id="200",
        response="2026-01-15",
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
):
    """When no pending question exists, the message is ignored."""
    pending_store.resolve.return_value = None

    update = _make_update(update_id=2, chat_id=100, sender_id=200, text="Hello")
    await poller._handle_update(update)

    pending_store.resolve.assert_called_once()
    outbound_sender.send.assert_not_called()


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

    update = _make_update(update_id=5, chat_id=100, sender_id=200, text="answer")
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

    update = _make_update(update_id=6, chat_id=100, sender_id=200, text="answer")
    await poller._handle_update(update)

    pending_store.resolve.assert_called_once()
