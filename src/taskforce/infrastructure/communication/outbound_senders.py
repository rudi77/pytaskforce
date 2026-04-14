"""Outbound sender adapters implementing OutboundSenderProtocol.

Each sender knows how to deliver a message to a specific channel's API.
Senders are stateless callables that manage their own HTTP sessions.
"""

from __future__ import annotations

import asyncio
import html
import re
from typing import Any

import aiohttp
import structlog


def _markdown_to_telegram_html(text: str) -> str:
    """Convert common Markdown patterns to Telegram-compatible HTML.

    Telegram's HTML mode supports a limited tag set: <b>, <i>, <u>, <s>,
    <code>, <pre>, <a href="...">, <blockquote>.  This function converts
    the most common LLM-generated Markdown to that subset and HTML-escapes
    everything else so Telegram doesn't reject the message.

    The conversion is best-effort — if the input is plain text it will
    simply be HTML-escaped and displayed correctly.
    """
    # Step 1: Extract code blocks and inline code to protect them from
    # further processing.  We replace them with placeholders.
    code_blocks: list[str] = []
    inline_codes: list[str] = []

    def _replace_code_block(m: re.Match) -> str:
        lang = m.group(1) or ""
        code = html.escape(m.group(2).strip("\n"))
        code_blocks.append(f"<pre><code>{code}</code></pre>" if not lang
                           else f'<pre><code class="language-{html.escape(lang)}">'
                                f"{code}</code></pre>")
        return f"\x00CODEBLOCK{len(code_blocks) - 1}\x00"

    def _replace_inline_code(m: re.Match) -> str:
        inline_codes.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00INLINE{len(inline_codes) - 1}\x00"

    # Fenced code blocks (```lang\n...\n```)
    text = re.sub(r"```(\w*)\n(.*?)```", _replace_code_block, text, flags=re.DOTALL)
    # Inline code (`...`)
    text = re.sub(r"`([^`\n]+)`", _replace_inline_code, text)

    # Step 2: HTML-escape the remaining text so special chars are safe.
    text = html.escape(text)

    # Step 3: Convert Markdown patterns to HTML tags.
    # Bold: **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    # Italic: *text* or _text_ (but not inside words with underscores)
    text = re.sub(r"(?<!\w)\*([^*\n]+?)\*(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", r"<i>\1</i>", text)
    # Strikethrough: ~~text~~
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)
    # Links: [text](url)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    # Blockquotes: > text (at line start)
    text = re.sub(
        r"(?m)^&gt;\s?(.+)$", r"<blockquote>\1</blockquote>", text
    )
    # Merge adjacent blockquotes
    text = text.replace("</blockquote>\n<blockquote>", "\n")
    # Headers: ## text → bold (Telegram has no header tags)
    text = re.sub(r"(?m)^#{1,6}\s+(.+)$", r"<b>\1</b>", text)
    # Unordered list markers: - item or * item → • item
    text = re.sub(r"(?m)^[\-\*]\s+", "• ", text)

    # Step 4: Restore code blocks and inline code.
    for i, block in enumerate(code_blocks):
        text = text.replace(f"\x00CODEBLOCK{i}\x00", block)
    for i, code in enumerate(inline_codes):
        text = text.replace(f"\x00INLINE{i}\x00", code)

    return text


class _TelegramClientError(Exception):
    """Non-retryable Telegram API error (4xx except 429)."""


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

        Raises:
            ValueError: If the message text is empty.
            ConnectionError: If all retry attempts fail.
        """
        if not message or not message.strip():
            raise ValueError("Cannot send empty message to Telegram")

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

        # Determine parse mode: default to HTML for rich formatting.
        # Callers can override via metadata["parse_mode"] or disable
        # formatting entirely with metadata["parse_mode"] = "".
        parse_mode = "HTML"
        if metadata and "parse_mode" in metadata:
            parse_mode = metadata["parse_mode"]

        # Convert Markdown → Telegram HTML unless caller opted out or
        # chose a different parse mode.
        if parse_mode == "HTML":
            try:
                message = _markdown_to_telegram_html(message)
            except Exception:
                # Fallback: send as plain text rather than failing.
                self._logger.warning("telegram.html_conversion_failed")
                parse_mode = ""

        payload: dict[str, Any] = {"chat_id": recipient_id, "text": message}
        if parse_mode:
            payload["parse_mode"] = parse_mode

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
                        # If a 400 came back while using parse_mode,
                        # Telegram likely rejected malformed markup.
                        # Retry once as plain text.
                        if (
                            response.status == 400
                            and "parse_mode" in payload
                            and not getattr(self, "_plain_text_retry", False)
                        ):
                            self._logger.warning(
                                "telegram.html_rejected_fallback_plain",
                                recipient_id=recipient_id,
                            )
                            payload.pop("parse_mode")
                            # Strip HTML tags for the plain-text retry.
                            payload["text"] = re.sub(r"<[^>]+>", "", payload["text"])
                            continue  # retry immediately without parse_mode

                        # 4xx errors (except 429) are not retryable — raise
                        # a non-OSError to escape the retry loop immediately.
                        if response.status != 429 and response.status < 500:
                            raise _TelegramClientError(
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
            except _TelegramClientError:
                raise  # Non-retryable 4xx — propagate immediately
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
