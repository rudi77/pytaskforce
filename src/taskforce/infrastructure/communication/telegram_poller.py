"""Telegram long-polling receiver for CLI mode.

When Taskforce runs as a CLI (no HTTP server), incoming Telegram
messages cannot arrive via webhook.  This module provides a lightweight
poller that calls the Telegram Bot API ``getUpdates`` endpoint and
feeds new messages into the ``PendingChannelQuestionStore`` so that the
executor's channel-routing loop can pick up responses.

Usage::

    poller = TelegramPoller(
        bot_token="123:ABC",
        pending_store=store,
        outbound_sender=sender,       # optional, for acknowledgment
    )
    await poller.start()   # runs in background
    ...
    await poller.stop()
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp
import structlog

from taskforce.core.interfaces.channel_ask import PendingChannelQuestionStoreProtocol
from taskforce.core.interfaces.gateway import RecipientRegistryProtocol
from taskforce.infrastructure.communication.telegram_file_downloader import (
    TelegramFileDownloader,
)

logger = structlog.get_logger(__name__)


class TelegramPoller:
    """Poll Telegram ``getUpdates`` and resolve pending channel questions.

    The poller runs as an ``asyncio.Task`` in the background.  For every
    text message received it checks the ``PendingChannelQuestionStore``:

    * If a pending question exists for ``(telegram, sender_id)`` the
      response is stored and (optionally) an acknowledgment is sent back.
    * Otherwise an optional inbound handler can process unsolicited
      Telegram messages as regular chat input.
    """

    def __init__(
        self,
        *,
        bot_token: str,
        pending_store: PendingChannelQuestionStoreProtocol,
        outbound_sender: Any | None = None,
        recipient_registry: RecipientRegistryProtocol | None = None,
        inbound_message_handler: (
            Callable[[str, str, str, list[dict[str, Any]] | None], Awaitable[None]] | None
        ) = None,
        poll_timeout: int = 10,
    ) -> None:
        self._bot_token = bot_token
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._pending_store = pending_store
        self._outbound_sender = outbound_sender
        self._recipient_registry = recipient_registry
        self._inbound_message_handler = inbound_message_handler
        self._poll_timeout = poll_timeout
        self._file_downloader = TelegramFileDownloader(bot_token)
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
        # Delete any existing webhook so getUpdates works
        await self._delete_webhook()
        self._task = asyncio.create_task(self._poll_loop(), name="telegram-poller")
        logger.info("telegram_poller.started")

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
        logger.info("telegram_poller.stopped")

    # ------------------------------------------------------------------
    # Internal polling loop
    # ------------------------------------------------------------------

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _delete_webhook(self) -> None:
        """Remove any registered webhook so long-polling works."""
        session = await self._get_session()
        try:
            async with session.post(f"{self._base_url}/deleteWebhook") as resp:
                if resp.status < 400:
                    logger.info("telegram_poller.webhook_deleted")
        except Exception as exc:
            logger.warning("telegram_poller.delete_webhook_failed", error=str(exc))

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
                logger.error("telegram_poller.poll_error", error=str(exc))
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
                    "telegram_poller.get_updates_failed",
                    status=resp.status,
                    body=body[:200],
                )
                await asyncio.sleep(2.0)
                return []

            data = await resp.json()
            return data.get("result", [])

    async def _handle_update(self, update: dict[str, Any]) -> None:
        """Process a single Telegram Update object."""
        update_id = update.get("update_id", 0)
        self._offset = max(self._offset, update_id + 1)

        message_obj = update.get("message")
        if not message_obj:
            return

        text = (message_obj.get("text") or message_obj.get("caption") or "").strip()
        attachments = await self._extract_attachments(message_obj)

        if not text and not attachments:
            return

        # Default prompt when media is sent without text/caption.
        if attachments and not text:
            text = "Bitte analysiere diese Datei."

        chat = message_obj.get("chat", {})
        chat_id = str(chat.get("id", ""))
        sender = message_obj.get("from", {})
        sender_id = str(sender.get("id", ""))

        if not sender_id:
            return

        # In CLI long-polling mode there is no inbound webhook flow that would
        # auto-register recipients. Register the sender here so outbound
        # channel-targeted ask_user/send_notification can reach this chat.
        if self._recipient_registry and chat_id:
            await self._recipient_registry.register(
                channel="telegram",
                user_id=sender_id,
                reference={"conversation_id": chat_id},
            )

        # Try to resolve a pending channel question
        resolved_session = await self._pending_store.resolve(
            channel="telegram",
            sender_id=sender_id,
            response=text,
        )

        if resolved_session:
            logger.info(
                "telegram_poller.question_resolved",
                session_id=resolved_session,
                sender_id=sender_id,
            )
            # Send acknowledgment
            if self._outbound_sender and chat_id:
                try:
                    await self._outbound_sender.send(
                        recipient_id=chat_id,
                        message="✅ Danke, Ihre Antwort wurde weitergeleitet.",
                    )
                except Exception:
                    pass  # Best-effort acknowledgment
        else:
            logger.debug(
                "telegram_poller.inbound_message",
                sender_id=sender_id,
                text=text[:50],
                has_attachments=bool(attachments),
            )
            if self._inbound_message_handler and chat_id:
                await self._inbound_message_handler(chat_id, sender_id, text, attachments)

    # ------------------------------------------------------------------
    # Media extraction
    # ------------------------------------------------------------------

    _IMAGE_MIME_PREFIXES = ("image/",)

    async def _extract_attachments(
        self, message_obj: dict[str, Any]
    ) -> list[dict[str, Any]] | None:
        """Extract photo/document attachments from a Telegram message.

        Returns a list of attachment dicts or None if no media is present.
        Each dict has ``type`` ("image" or "document") and either
        ``data_url`` (base64 data URL) or ``file_path`` + ``file_name``.
        """
        attachments: list[dict[str, Any]] = []

        # Photos: Telegram sends an array of sizes; take the largest.
        photos = message_obj.get("photo")
        if photos:
            largest = photos[-1]
            file_id = largest.get("file_id", "")
            if file_id:
                data_url = await self._file_downloader.download_as_data_url(
                    file_id, mime_type="image/jpeg"
                )
                if data_url:
                    attachments.append({"type": "image", "data_url": data_url})

        # Documents (PDF, images sent as file, etc.)
        document = message_obj.get("document")
        if document:
            file_id = document.get("file_id", "")
            mime_type = document.get("mime_type", "application/octet-stream")
            file_name = document.get("file_name", "document")
            if file_id:
                if mime_type.startswith(self._IMAGE_MIME_PREFIXES[0]):
                    data_url = await self._file_downloader.download_as_data_url(
                        file_id, mime_type=mime_type
                    )
                    if data_url:
                        attachments.append({"type": "image", "data_url": data_url})
                else:
                    tmp_path = await self._file_downloader.download_to_temp_file(
                        file_id, file_name=file_name
                    )
                    if tmp_path:
                        attachments.append(
                            {
                                "type": "document",
                                "file_path": tmp_path,
                                "file_name": file_name,
                                "mime_type": mime_type,
                            }
                        )

        return attachments or None
