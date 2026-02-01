"""Telegram outbound sender helper."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp
import structlog

from taskforce_extensions.infrastructure.communication.providers import OutboundSender


def build_telegram_sender(token: str) -> OutboundSender:
    """Build an outbound sender for Telegram Bot API."""
    logger = structlog.get_logger()
    base_url = f"https://api.telegram.org/bot{token}/sendMessage"

    async def _send(
        conversation_id: str,
        message: str,
        metadata: dict[str, Any] | None,
    ) -> None:
        payload = {"chat_id": conversation_id, "text": message}
        timeout = aiohttp.ClientTimeout(total=10)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(base_url, json=payload) as response:
                    if response.status >= 400:
                        response_text = await response.text()
                        logger.error(
                            "telegram.send_failed",
                            status=response.status,
                            response=response_text,
                            conversation_id=conversation_id,
                        )
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.error(
                "telegram.send_error",
                error=str(exc),
                conversation_id=conversation_id,
            )

    return _send
