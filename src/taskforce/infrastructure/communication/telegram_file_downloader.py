"""Telegram Bot API file downloader.

Downloads files (photos, documents) from Telegram and converts them
to base64 data URLs suitable for LLM vision APIs, or saves them to
temporary files for non-image documents.
"""

from __future__ import annotations

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
    """

    def __init__(self, bot_token: str, session: aiohttp.ClientSession | None = None) -> None:
        self._bot_token = bot_token
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._file_url = f"https://api.telegram.org/file/bot{bot_token}"
        self._session = session

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
        """Call Telegram ``getFile`` to resolve file_id to a download path."""
        session = await self._get_session()
        try:
            async with session.get(
                f"{self._base_url}/getFile", params={"file_id": file_id}
            ) as resp:
                if resp.status >= 400:
                    logger.warning("telegram_file.get_file_failed", status=resp.status)
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
        except Exception as exc:
            logger.error("telegram_file.get_file_error", error=str(exc))
            return None

    async def _download_bytes(self, file_path: str) -> bytes | None:
        """Download file bytes from Telegram file storage."""
        session = await self._get_session()
        try:
            async with session.get(f"{self._file_url}/{file_path}") as resp:
                if resp.status >= 400:
                    logger.warning("telegram_file.download_failed", status=resp.status)
                    return None
                data = await resp.read()
                if len(data) > MAX_FILE_SIZE:
                    logger.warning("telegram_file.download_too_large", size=len(data))
                    return None
                return data
        except Exception as exc:
            logger.error("telegram_file.download_error", error=str(exc))
            return None
