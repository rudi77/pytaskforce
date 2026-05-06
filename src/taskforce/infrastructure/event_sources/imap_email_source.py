"""IMAP inbox poller that emits ``EMAIL_RECEIVED`` events.

Uses the synchronous ``imaplib`` from the standard library, executed via
``asyncio.to_thread`` inside the polling loop. Sticking with the stdlib
keeps the framework's optional dependency footprint small (no
``aioimaplib`` install needed for the simple "new mail" case the butler
typically wants).

Authentication: username/password (or app-password). For OAuth2 flows
plug a custom factory that wires the existing ``AuthManager`` instead.

Optional dependency: none — uses the stdlib. The factory still respects
a ``mailbox`` setting and a ``mark_seen`` toggle so the watcher can run
read-only against a shared inbox.
"""

from __future__ import annotations

import asyncio
import email
import imaplib
from collections.abc import Awaitable, Callable
from email.message import Message
from typing import Any

import structlog

from taskforce.core.domain.agent_event import AgentEvent, AgentEventType
from taskforce.infrastructure.event_sources.polling_base import PollingEventSource

logger = structlog.get_logger(__name__)

EventCallback = Callable[[AgentEvent], Awaitable[None]]


class IMAPEmailEventSource(PollingEventSource):
    """Poll an IMAP mailbox for unseen messages and emit ``EMAIL_RECEIVED``.

    Configuration (butler profile YAML)::

        event_sources:
          - type: imap_email
            host: imap.gmail.com
            port: 993
            username: butler@example.com
            password_env: BUTLER_IMAP_PASSWORD   # read at runtime, not stored
            mailbox: INBOX
            mark_seen: true                       # mark messages \\Seen on poll
            poll_interval_minutes: 2

    Set ``mark_seen=false`` to leave the inbox untouched (useful for
    read-only audits or when another client also processes mail).
    """

    def __init__(
        self,
        host: str,
        username: str,
        *,
        password: str | None = None,
        port: int = 993,
        mailbox: str = "INBOX",
        mark_seen: bool = True,
        poll_interval_seconds: float = 120.0,
        use_ssl: bool = True,
        source_name: str = "imap_email",
        event_callback: EventCallback | None = None,
    ) -> None:
        super().__init__(
            source_name=source_name,
            poll_interval_seconds=poll_interval_seconds,
            event_callback=event_callback,
        )
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._mailbox = mailbox
        self._mark_seen = mark_seen
        self._use_ssl = use_ssl

    async def _poll_once(self) -> list[AgentEvent]:
        if not self._password:
            logger.debug(
                "imap_email_source.no_password",
                hint="Set 'password' or 'password_env' in the source config.",
            )
            return []
        try:
            return await asyncio.to_thread(self._poll_sync)
        except Exception as exc:
            logger.warning(
                "imap_email_source.poll_failed",
                host=self._host,
                username=self._username,
                error=str(exc),
            )
            return []

    def _poll_sync(self) -> list[AgentEvent]:
        """Synchronous IMAP poll — runs in a worker thread."""
        client_cls = imaplib.IMAP4_SSL if self._use_ssl else imaplib.IMAP4
        with _imap_connection(client_cls, self._host, self._port) as conn:
            conn.login(self._username, self._password or "")
            select_status, _ = conn.select(self._mailbox, readonly=not self._mark_seen)
            if select_status != "OK":
                logger.warning(
                    "imap_email_source.select_failed",
                    mailbox=self._mailbox,
                    status=select_status,
                )
                return []

            search_status, message_ids = conn.search(None, "UNSEEN")
            if search_status != "OK" or not message_ids or not message_ids[0]:
                return []

            ids = message_ids[0].split()
            events: list[AgentEvent] = []
            for raw_id in ids:
                fetch_status, data = conn.fetch(raw_id, "(RFC822)")
                if fetch_status != "OK" or not data:
                    continue
                payload = self._parse_message(data, raw_id.decode("utf-8", "replace"))
                if payload is None:
                    continue
                events.append(
                    AgentEvent(
                        source=self.source_name,
                        event_type=AgentEventType.EMAIL_RECEIVED,
                        payload=payload,
                        metadata={"host": self._host, "mailbox": self._mailbox},
                    )
                )
                if self._mark_seen:
                    conn.store(raw_id, "+FLAGS", "\\Seen")
            try:
                conn.close()
            except Exception:  # pragma: no cover — best-effort
                pass
            return events

    @staticmethod
    def _parse_message(data: list[Any], raw_id: str) -> dict[str, Any] | None:
        """Extract a friendly payload from an IMAP fetch tuple."""
        for item in data:
            if not isinstance(item, tuple) or len(item) < 2:
                continue
            raw_bytes = item[1]
            if not isinstance(raw_bytes, (bytes, bytearray)):
                continue
            msg: Message = email.message_from_bytes(bytes(raw_bytes))
            return {
                "imap_id": raw_id,
                "subject": str(msg.get("Subject", "")),
                "from": str(msg.get("From", "")),
                "to": str(msg.get("To", "")),
                "date": str(msg.get("Date", "")),
                "message_id": str(msg.get("Message-ID", "")),
                "body": _first_text_part(msg)[:8192],  # cap to keep events small
            }
        return None

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any],
        *,
        event_callback: EventCallback | None = None,
    ) -> IMAPEmailEventSource:
        """Factory used by ``EventSourceRegistry``.

        ``password_env`` is preferred over ``password`` so secrets stay
        out of YAML.
        """
        import os

        password = config.get("password")
        if not password and config.get("password_env"):
            password = os.environ.get(config["password_env"])
        poll_minutes = config.get("poll_interval_minutes", 2)
        return cls(
            host=config["host"],
            username=config["username"],
            password=password,
            port=int(config.get("port", 993)),
            mailbox=config.get("mailbox", "INBOX"),
            mark_seen=bool(config.get("mark_seen", True)),
            poll_interval_seconds=float(poll_minutes) * 60.0,
            use_ssl=bool(config.get("use_ssl", True)),
            source_name=config.get("source_name", "imap_email"),
            event_callback=event_callback,
        )


def _first_text_part(msg: Message) -> str:
    """Return the first text/plain part of a message, decoded best-effort."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if isinstance(payload, (bytes, bytearray)):
                    return payload.decode(
                        part.get_content_charset() or "utf-8",
                        errors="replace",
                    )
        return ""
    payload = msg.get_payload(decode=True)
    if isinstance(payload, (bytes, bytearray)):
        return payload.decode(
            msg.get_content_charset() or "utf-8", errors="replace"
        )
    return str(payload or "")


class _imap_connection:
    """Tiny context-manager wrapper so we always logout/close cleanly."""

    def __init__(self, client_cls: Any, host: str, port: int) -> None:
        self._client_cls = client_cls
        self._host = host
        self._port = port
        self._conn: Any = None

    def __enter__(self) -> Any:
        self._conn = self._client_cls(self._host, self._port)
        return self._conn

    def __exit__(self, *exc_info: Any) -> None:
        if self._conn is None:
            return
        try:
            self._conn.logout()
        except Exception:  # pragma: no cover — best-effort cleanup
            pass
