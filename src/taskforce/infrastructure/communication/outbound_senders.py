"""Outbound sender adapters implementing OutboundSenderProtocol.

Each sender knows how to deliver a message to a specific channel's API.
Senders are stateless callables that manage their own HTTP sessions.
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
import structlog


class TelegramOutboundSender:
    """Send messages via the Telegram Bot API.

    Uses a shared ``aiohttp.ClientSession`` for connection pooling.
    The session is created lazily on first send and closed via ``close()``.

    Includes automatic retry with exponential backoff for transient
    network errors (connection drops, timeouts, DNS issues).
    """

    def __init__(
        self,
        token: str,
        *,
        max_retries: int = 3,
        base_backoff: float = 1.0,
    ) -> None:
        self._base_url = f"https://api.telegram.org/bot{token}/sendMessage"
        self._session: aiohttp.ClientSession | None = None
        self._max_retries = max_retries
        self._base_backoff = base_backoff
        self._logger = structlog.get_logger()

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
        """Send a message via Telegram Bot API sendMessage.

        Retries up to ``max_retries`` times on transient network errors
        with exponential backoff (1s, 2s, 4s).

        Args:
            recipient_id: Telegram chat_id.
            message: Text message body.
            metadata: Optional keys: parse_mode ('HTML'|'Markdown').
        """
        # Telegram has a 4096-char limit per message. Split long messages
        # into chunks, breaking at newlines when possible.
        max_len = 4000  # Leave margin below the 4096 hard limit
        if len(message) > max_len:
            chunks = _split_message(message, max_len)
            for chunk in chunks:
                await self.send(
                    recipient_id=recipient_id, message=chunk, metadata=metadata
                )
            return

        payload: dict[str, Any] = {"chat_id": recipient_id, "text": message}
        if metadata and "parse_mode" in metadata:
            payload["parse_mode"] = metadata["parse_mode"]

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                # Recreate session on retry in case the connection pool is stale.
                if attempt > 0:
                    await self._close_session()
                session = await self._get_session()
                async with session.post(self._base_url, json=payload) as response:
                    if response.status >= 400:
                        body = await response.text()
                        self._logger.error(
                            "telegram.send_failed",
                            status=response.status,
                            response=body,
                            recipient_id=recipient_id,
                        )
                        # 4xx errors (except 429) are not retryable.
                        if response.status != 429 and response.status < 500:
                            raise ConnectionError(
                                f"Telegram API returned HTTP {response.status}: {body}"
                            )
                        last_error = ConnectionError(
                            f"Telegram API returned HTTP {response.status}: {body}"
                        )
                    else:
                        if attempt > 0:
                            self._logger.info(
                                "telegram.send_retry_success",
                                attempt=attempt + 1,
                                recipient_id=recipient_id,
                            )
                        return  # Success
            except (TimeoutError, aiohttp.ClientError, OSError) as exc:
                last_error = exc
                if attempt < self._max_retries:
                    backoff = self._base_backoff * (2 ** attempt)
                    self._logger.warning(
                        "telegram.send_retry",
                        attempt=attempt + 1,
                        max_retries=self._max_retries,
                        backoff_s=backoff,
                        error=str(exc),
                        recipient_id=recipient_id,
                    )
                    await asyncio.sleep(backoff)

        self._logger.error(
            "telegram.send_error",
            error=str(last_error),
            recipient_id=recipient_id,
            attempts=self._max_retries + 1,
        )
        raise ConnectionError(
            f"Telegram API request failed after {self._max_retries + 1} attempts: {last_error}"
        ) from last_error

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        await self._close_session()

    async def _close_session(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=15)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session


def _split_message(text: str, max_len: int) -> list[str]:
    """Split a long message into chunks, breaking at newlines when possible."""
    chunks: list[str] = []
    while len(text) > max_len:
        # Try to break at a newline within the last 20% of the chunk
        split_at = text.rfind("\n", 0, max_len)
        if split_at < max_len // 2:
            # No good newline break — just cut at max_len
            split_at = max_len
        chunks.append(text[:split_at].rstrip())
        text = text[split_at:].lstrip("\n")
    if text.strip():
        chunks.append(text)
    return chunks


class TeamsOutboundSender:
    """Placeholder sender for Microsoft Teams Bot Framework.

    A full implementation would use the Bot Framework REST API with
    ``continueConversation`` and stored ``ConversationReference``.
    """

    def __init__(self, app_id: str = "", app_password: str = "") -> None:
        self._app_id = app_id
        self._app_password = app_password
        self._logger = structlog.get_logger()

    @property
    def channel(self) -> str:
        return "teams"

    async def send(
        self,
        *,
        recipient_id: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Send a proactive message to a Teams conversation.

        Args:
            recipient_id: Serialized ConversationReference (JSON string or ID).
            message: Plain text or Adaptive Card JSON.
            metadata: Optional keys: card (Adaptive Card payload).
        """
        self._logger.warning(
            "teams.send_not_implemented",
            recipient_id=recipient_id,
            message_preview=message[:80],
        )
