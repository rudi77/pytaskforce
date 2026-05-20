"""Tests for TelegramOutboundSender.send_typing chat-action keepalive."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from taskforce.infrastructure.communication.outbound_senders import (
    TelegramOutboundSender,
)


class _FakeResponse:
    """Async context-manager response stub."""

    def __init__(self, status: int = 200, body: str = "") -> None:
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def text(self):
        return self._body


class TestSendTyping:
    @pytest.fixture
    def sender(self) -> TelegramOutboundSender:
        return TelegramOutboundSender(token="testtoken")

    async def _run_typing(
        self,
        sender: TelegramOutboundSender,
        recipient_id: str,
        *,
        response: _FakeResponse | None = None,
        raise_exc: Exception | None = None,
    ) -> MagicMock:
        """Patch the session and capture the outgoing POST call."""
        fake_session = MagicMock()
        if raise_exc is not None:
            fake_session.post = MagicMock(side_effect=raise_exc)
        else:
            fake_session.post = MagicMock(
                return_value=response or _FakeResponse(200)
            )
        fake_session.closed = False

        with patch.object(
            sender, "_get_session", AsyncMock(return_value=fake_session)
        ):
            await sender.send_typing(recipient_id)
        return fake_session

    async def test_hits_sendchataction_with_typing_action(
        self, sender: TelegramOutboundSender
    ) -> None:
        fake_session = await self._run_typing(sender, "12345")

        # Exactly one POST should have been issued.
        assert fake_session.post.call_count == 1
        url = fake_session.post.call_args.args[0]
        assert url.endswith("/sendChatAction")
        payload = fake_session.post.call_args.kwargs["json"]
        assert payload == {"chat_id": "12345", "action": "typing"}

    async def test_skips_call_when_recipient_id_empty(
        self, sender: TelegramOutboundSender
    ) -> None:
        # No recipient => no API hit. Patch _get_session to assert it isn't
        # even invoked (the early-return saves a wasted session lookup).
        with patch.object(
            sender, "_get_session", AsyncMock(side_effect=AssertionError("called"))
        ):
            await sender.send_typing("")

    async def test_swallows_http_400(self, sender: TelegramOutboundSender) -> None:
        # The protocol contract says send_typing must never raise so a
        # flaky indicator can't block message delivery.
        await self._run_typing(sender, "12345", response=_FakeResponse(400, "Bad Request"))

    async def test_swallows_network_error(
        self, sender: TelegramOutboundSender
    ) -> None:
        # Same contract: ClientError / TimeoutError stay inside the method.
        await self._run_typing(
            sender, "12345", raise_exc=aiohttp.ClientConnectionError("boom")
        )
        await self._run_typing(sender, "12345", raise_exc=asyncio.TimeoutError())

    async def test_uses_short_timeout(self, sender: TelegramOutboundSender) -> None:
        # The keepalive fires every 4 s; a typing call that hangs for the
        # full 15 s default would stack up and starve the loop. The
        # method must pass a short timeout (≤ keepalive interval).
        fake_session = await self._run_typing(sender, "12345")
        timeout = fake_session.post.call_args.kwargs["timeout"]
        assert isinstance(timeout, aiohttp.ClientTimeout)
        assert timeout.total is not None and timeout.total <= 5
