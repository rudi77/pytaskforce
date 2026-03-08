"""Telegram long-polling receiver for the Butler daemon.

Unlike the CLI ``TelegramPoller`` (which only resolves pending ask_user
channel questions), this poller routes **all** incoming Telegram messages
through the ``CommunicationGateway.handle_message()`` flow — creating
agent sessions, executing missions, and sending replies automatically.

Usage::

    poller = ButlerTelegramPoller(
        bot_token="123:ABC",
        gateway=gateway,
        profile="butler",
    )
    await poller.start()   # runs in background
    ...
    await poller.stop()
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
import structlog

from taskforce.core.domain.gateway import GatewayOptions, InboundMessage

logger = structlog.get_logger(__name__)


class ButlerTelegramPoller:
    """Poll Telegram ``getUpdates`` and route messages through the gateway.

    Every text message received is converted to an ``InboundMessage`` and
    dispatched to ``CommunicationGateway.handle_message()``, which handles
    session management, agent execution, conversation history, and outbound
    reply dispatch.
    """

    def __init__(
        self,
        *,
        bot_token: str,
        gateway: Any,
        profile: str = "butler",
        poll_timeout: int = 30,
    ) -> None:
        self._bot_token = bot_token
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._gateway = gateway
        self._profile = profile
        self._poll_timeout = poll_timeout
        self._offset: int = 0
        self._task: asyncio.Task[None] | None = None
        self._session: aiohttp.ClientSession | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background polling task."""
        if self._task is not None:
            return
        await self._delete_webhook()
        self._task = asyncio.create_task(
            self._poll_loop(), name="butler-telegram-poller"
        )
        logger.info("butler_telegram_poller.started")

    async def stop(self) -> None:
        """Cancel the background polling task and close the HTTP session."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
        logger.info("butler_telegram_poller.stopped")

    @property
    def is_running(self) -> bool:
        """Whether the poller task is active."""
        return self._task is not None and not self._task.done()

    # ------------------------------------------------------------------
    # Internal polling loop
    # ------------------------------------------------------------------

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self._poll_timeout + 10)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _delete_webhook(self) -> None:
        """Remove any registered webhook so long-polling works."""
        session = await self._get_session()
        try:
            async with session.post(f"{self._base_url}/deleteWebhook") as resp:
                if resp.status < 400:
                    logger.info("butler_telegram_poller.webhook_deleted")
        except Exception as exc:
            logger.warning(
                "butler_telegram_poller.delete_webhook_failed", error=str(exc)
            )

    async def _poll_loop(self) -> None:
        """Continuously poll ``getUpdates`` until cancelled."""
        while True:
            try:
                updates = await self._get_updates()
                for update in updates:
                    await self._handle_update(update)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "butler_telegram_poller.poll_error", error=str(exc)
                )
                await asyncio.sleep(2.0)

    async def _get_updates(self) -> list[dict[str, Any]]:
        """Call Telegram ``getUpdates`` with long-polling."""
        session = await self._get_session()
        params: dict[str, Any] = {"timeout": self._poll_timeout}
        if self._offset:
            params["offset"] = self._offset

        async with session.get(
            f"{self._base_url}/getUpdates", params=params
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                logger.error(
                    "butler_telegram_poller.get_updates_failed",
                    status=resp.status,
                    body=body[:200],
                )
                await asyncio.sleep(2.0)
                return []

            data = await resp.json()
            return data.get("result", [])

    async def _handle_update(self, update: dict[str, Any]) -> None:
        """Process a single Telegram Update object via the gateway."""
        update_id = update.get("update_id", 0)
        self._offset = max(self._offset, update_id + 1)

        message_obj = update.get("message")
        if not message_obj:
            return

        text = message_obj.get("text", "").strip()
        if not text:
            return

        chat = message_obj.get("chat", {})
        chat_id = str(chat.get("id", ""))
        sender = message_obj.get("from", {})
        sender_id = str(sender.get("id", ""))

        if not chat_id:
            return

        logger.info(
            "butler_telegram_poller.message_received",
            sender_id=sender_id,
            chat_id=chat_id,
            text_preview=text[:80],
        )

        inbound = InboundMessage(
            channel="telegram",
            conversation_id=chat_id,
            message=text,
            sender_id=sender_id or None,
            metadata={
                "update_id": update_id,
                "chat_type": chat.get("type"),
                "message_id": message_obj.get("message_id"),
            },
        )

        options = GatewayOptions(profile=self._profile)

        try:
            response = await self._gateway.handle_message(inbound, options)
            logger.info(
                "butler_telegram_poller.message_handled",
                session_id=response.session_id,
                status=response.status,
            )
        except Exception as exc:
            logger.error(
                "butler_telegram_poller.handle_failed",
                chat_id=chat_id,
                error=str(exc),
            )
