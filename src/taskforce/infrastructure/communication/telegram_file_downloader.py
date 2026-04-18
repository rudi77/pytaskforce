"""Telegram Bot API file downloader.

Downloads files (photos, documents) from Telegram and converts them
to base64 data URLs suitable for LLM vision APIs, or saves them to
temporary files for non-image documents.

Retries transient network errors automatically with exponential
backoff — the most common failure mode in production is a brief DNS /
TLS hiccup that recovers within a couple of seconds, and silently
dropping a customer's photo because of that is unacceptable.
"""

from __future__ import annotations

import asyncio
import base64
import tempfile
from pathlib import Path
from typing import Any

import aiohttp
import structlog

logger = structlog.get_logger(__name__)

# 10 MB guard to prevent memory issues with large files.
MAX_FILE_SIZE = 10 * 1024 * 1024


class TelegramFileDownloader:
    """Download files from Telegram Bot API.

    Args:
        bot_token: Telegram bot token for API authentication.
        session: Optional shared aiohttp session. If not provided,
            a new session is created per download.
        max_retries: Number of retry attempts on transient network
            failures (DNS hiccup, TLS reset, timeout). Default 3.
        base_backoff: Initial backoff in seconds between retries; doubles
            each attempt (1s → 2s → 4s).
    """

    def __init__(
        self,
        bot_token: str,
        session: aiohttp.ClientSession | None = None,
        *,
        max_retries: int = 3,
        base_backoff: float = 1.0,
    ) -> None:
        self._bot_token = bot_token
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._file_url = f"https://api.telegram.org/file/bot{bot_token}"
        self._session = session
        self._max_retries = max_retries
        self._base_backoff = base_backoff

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def download_as_data_url(
        self, file_id: str, mime_type: str = "image/jpeg"
    ) -> str | None:
        """Download a Telegram file and return it as a base64 data URL.

        Args:
            file_id: Telegram file_id from the message object.
            mime_type: MIME type for the data URL prefix.

        Returns:
            Data URL string (``data:{mime};base64,...``) or None on failure.
        """
        file_path = await self._get_file_path(file_id)
        if not file_path:
            return None

        data = await self._download_bytes(file_path)
        if not data:
            return None

        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{mime_type};base64,{b64}"

    async def download_to_temp_file(
        self, file_id: str, file_name: str = "document"
    ) -> str | None:
        """Download a Telegram file and save to a temporary file.

        Args:
            file_id: Telegram file_id from the message object.
            file_name: Original file name for the suffix.

        Returns:
            Path to the temporary file, or None on failure.
        """
        file_path = await self._get_file_path(file_id)
        if not file_path:
            return None

        data = await self._download_bytes(file_path)
        if not data:
            return None

        suffix = Path(file_name).suffix or ""
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="tg_")
        tmp.write(data)
        tmp.close()
        return tmp.name

    async def _get_file_path(self, file_id: str) -> str | None:
        """Call Telegram ``getFile`` to resolve file_id to a download path.

        Retries transient network errors with exponential backoff. Only
        returns None on a permanent failure (4xx response, file too
        large, or all retries exhausted).
        """
        for attempt in range(self._max_retries + 1):
            try:
                session = await self._get_session()
                async with session.get(
                    f"{self._base_url}/getFile", params={"file_id": file_id}
                ) as resp:
                    if resp.status >= 400:
                        logger.warning(
                            "telegram_file.get_file_failed", status=resp.status
                        )
                        return None
                    data: dict[str, Any] = await resp.json()
                    result = data.get("result", {})
                    file_size = result.get("file_size", 0)
                    if file_size > MAX_FILE_SIZE:
                        logger.warning(
                            "telegram_file.too_large",
                            file_size=file_size,
                            max_size=MAX_FILE_SIZE,
                        )
                        return None
                    return result.get("file_path")
            except (TimeoutError, aiohttp.ClientError, OSError) as exc:
                if attempt < self._max_retries:
                    backoff = self._base_backoff * (2 ** attempt)
                    logger.warning(
                        "telegram_file.get_file_retry",
                        attempt=attempt + 1,
                        max_retries=self._max_retries,
                        backoff_s=backoff,
                        error=str(exc),
                    )
                    # Recreate session on retry in case the pool went stale.
                    if self._session and not self._session.closed:
                        try:
                            await self._session.close()
                        except Exception:
                            pass
                        self._session = None
                    await asyncio.sleep(backoff)
                else:
                    logger.error(
                        "telegram_file.get_file_error",
                        error=str(exc),
                        attempts=self._max_retries + 1,
                    )
                    return None
            except Exception as exc:  # non-retryable
                logger.error("telegram_file.get_file_error", error=str(exc))
                return None
        return None

    async def _download_bytes(self, file_path: str) -> bytes | None:
        """Download file bytes from Telegram file storage.

        Same retry policy as :meth:`_get_file_path`.
        """
        for attempt in range(self._max_retries + 1):
            try:
                session = await self._get_session()
                async with session.get(f"{self._file_url}/{file_path}") as resp:
                    if resp.status >= 400:
                        logger.warning(
                            "telegram_file.download_failed", status=resp.status
                        )
                        return None
                    data = await resp.read()
                    if len(data) > MAX_FILE_SIZE:
                        logger.warning(
                            "telegram_file.download_too_large", size=len(data)
                        )
                        return None
                    return data
            except (TimeoutError, aiohttp.ClientError, OSError) as exc:
                if attempt < self._max_retries:
                    backoff = self._base_backoff * (2 ** attempt)
                    logger.warning(
                        "telegram_file.download_retry",
                        attempt=attempt + 1,
                        max_retries=self._max_retries,
                        backoff_s=backoff,
                        error=str(exc),
                    )
                    if self._session and not self._session.closed:
                        try:
                            await self._session.close()
                        except Exception:
                            pass
                        self._session = None
                    await asyncio.sleep(backoff)
                else:
                    logger.error(
                        "telegram_file.download_error",
                        error=str(exc),
                        attempts=self._max_retries + 1,
                    )
                    return None
            except Exception as exc:  # non-retryable
                logger.error("telegram_file.download_error", error=str(exc))
                return None
        return None
