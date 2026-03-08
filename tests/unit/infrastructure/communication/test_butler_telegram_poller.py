"""Tests for ButlerTelegramPoller.

Covers message handling, gateway integration, and error handling.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskforce.core.domain.gateway import GatewayResponse, InboundMessage
from taskforce.infrastructure.communication.butler_telegram_poller import (
    ButlerTelegramPoller,
)


@pytest.fixture
def mock_gateway() -> AsyncMock:
    """Create a mock CommunicationGateway."""
    gateway = AsyncMock()
    gateway.handle_message = AsyncMock(
        return_value=GatewayResponse(
            session_id="test-session",
            status="completed",
            reply="Hello!",
            history=[],
        )
    )
    return gateway


@pytest.fixture
def poller(mock_gateway: AsyncMock) -> ButlerTelegramPoller:
    """Create a ButlerTelegramPoller with mocked gateway."""
    return ButlerTelegramPoller(
        bot_token="123:TEST",
        gateway=mock_gateway,
        profile="butler",
    )


def _make_update(
    update_id: int = 1,
    text: str = "Hello Butler",
    chat_id: int = 12345,
    sender_id: int = 67890,
) -> dict[str, Any]:
    """Build a fake Telegram Update dict."""
    return {
        "update_id": update_id,
        "message": {
            "message_id": 100,
            "text": text,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": sender_id, "first_name": "Test"},
        },
    }


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestButlerTelegramPollerProperties:
    def test_is_not_running_initially(self, poller: ButlerTelegramPoller) -> None:
        assert poller.is_running is False

    def test_initial_offset_is_zero(self, poller: ButlerTelegramPoller) -> None:
        assert poller._offset == 0


# ---------------------------------------------------------------------------
# Handle Update
# ---------------------------------------------------------------------------


class TestButlerTelegramPollerHandleUpdate:
    async def test_handles_text_message(
        self, poller: ButlerTelegramPoller, mock_gateway: AsyncMock
    ) -> None:
        update = _make_update(text="Guten Morgen", chat_id=111, sender_id=222)

        await poller._handle_update(update)

        mock_gateway.handle_message.assert_called_once()
        call_args = mock_gateway.handle_message.call_args
        inbound: InboundMessage = call_args[0][0]
        assert inbound.channel == "telegram"
        assert inbound.conversation_id == "111"
        assert inbound.message == "Guten Morgen"
        assert inbound.sender_id == "222"

    async def test_updates_offset(
        self, poller: ButlerTelegramPoller, mock_gateway: AsyncMock
    ) -> None:
        update = _make_update(update_id=42)

        await poller._handle_update(update)

        assert poller._offset == 43

    async def test_passes_butler_profile(
        self, poller: ButlerTelegramPoller, mock_gateway: AsyncMock
    ) -> None:
        update = _make_update()

        await poller._handle_update(update)

        call_args = mock_gateway.handle_message.call_args
        options = call_args[0][1]
        assert options.profile == "butler"

    async def test_skips_update_without_message(
        self, poller: ButlerTelegramPoller, mock_gateway: AsyncMock
    ) -> None:
        update = {"update_id": 1}

        await poller._handle_update(update)

        mock_gateway.handle_message.assert_not_called()

    async def test_skips_empty_text(
        self, poller: ButlerTelegramPoller, mock_gateway: AsyncMock
    ) -> None:
        update = _make_update(text="")

        await poller._handle_update(update)

        mock_gateway.handle_message.assert_not_called()

    async def test_skips_whitespace_only_text(
        self, poller: ButlerTelegramPoller, mock_gateway: AsyncMock
    ) -> None:
        update = _make_update(text="   ")

        await poller._handle_update(update)

        mock_gateway.handle_message.assert_not_called()

    async def test_skips_missing_chat_id(
        self, poller: ButlerTelegramPoller, mock_gateway: AsyncMock
    ) -> None:
        update = {
            "update_id": 1,
            "message": {
                "text": "Hello",
                "chat": {},
                "from": {"id": 123},
            },
        }

        await poller._handle_update(update)

        mock_gateway.handle_message.assert_not_called()

    async def test_handles_gateway_error_gracefully(
        self, poller: ButlerTelegramPoller, mock_gateway: AsyncMock
    ) -> None:
        mock_gateway.handle_message.side_effect = RuntimeError("Agent failed")
        update = _make_update()

        # Should not raise
        await poller._handle_update(update)

        # Offset should still advance
        assert poller._offset == 2

    async def test_metadata_includes_update_fields(
        self, poller: ButlerTelegramPoller, mock_gateway: AsyncMock
    ) -> None:
        update = _make_update(update_id=99)

        await poller._handle_update(update)

        call_args = mock_gateway.handle_message.call_args
        inbound: InboundMessage = call_args[0][0]
        assert inbound.metadata["update_id"] == 99
        assert inbound.metadata["chat_type"] == "private"

    async def test_handles_multiple_updates_sequentially(
        self, poller: ButlerTelegramPoller, mock_gateway: AsyncMock
    ) -> None:
        updates = [
            _make_update(update_id=1, text="First"),
            _make_update(update_id=2, text="Second"),
            _make_update(update_id=3, text="Third"),
        ]

        for update in updates:
            await poller._handle_update(update)

        assert mock_gateway.handle_message.call_count == 3
        assert poller._offset == 4
