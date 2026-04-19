"""Gateway adapters exposing ACP as a Communication Gateway channel.

Lets ACP-delivered missions flow through the existing
:class:`CommunicationGateway` so the session / history / push-notification
logic is shared with Telegram, Teams and REST.
"""

from __future__ import annotations

import hmac
from typing import Any

import structlog

from taskforce.core.domain.acp import AcpPeer
from taskforce.infrastructure.acp.runtime import AcpRuntime

logger = structlog.get_logger(__name__)

CHANNEL = "acp"


class AcpInboundAdapter:
    """Normalises ACP request payloads into the gateway inbound shape."""

    def __init__(self, *, shared_secret: str | None = None) -> None:
        self._shared_secret = shared_secret

    @property
    def channel(self) -> str:
        return CHANNEL

    def extract_message(self, raw_payload: dict[str, Any]) -> dict[str, Any]:
        agent = str(raw_payload.get("agent", ""))
        session_id = raw_payload.get("session_id")
        sender_id = str(raw_payload.get("sender_id") or raw_payload.get("peer") or "acp")
        text = self._collect_text(raw_payload.get("input") or [])
        if not text:
            raise ValueError("ACP payload did not contain any text message parts")
        return {
            "conversation_id": str(session_id or f"{sender_id}:{agent}"),
            "message": text,
            "sender_id": sender_id,
            "metadata": {
                "agent": agent,
                "peer": raw_payload.get("peer"),
                "session_id": session_id,
            },
        }

    def verify_signature(self, *, raw_body: bytes, headers: dict[str, str]) -> bool:
        if self._shared_secret is None:
            return True
        provided = headers.get("x-acp-secret") or headers.get("X-ACP-Secret") or ""
        return hmac.compare_digest(provided, self._shared_secret)

    @staticmethod
    def _collect_text(messages: list[Any]) -> str:
        chunks: list[str] = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            for part in message.get("parts", []) or []:
                if not isinstance(part, dict):
                    continue
                content = part.get("content")
                if isinstance(content, str):
                    chunks.append(content)
        return "\n".join(chunks)


class AcpOutboundSender:
    """Delivers proactive messages to ACP peers.

    ``recipient_id`` is interpreted as the peer name configured in the
    :class:`AcpRuntime` peer registry.
    """

    def __init__(self, runtime: AcpRuntime) -> None:
        self._runtime = runtime

    @property
    def channel(self) -> str:
        return CHANNEL

    async def send(
        self,
        *,
        recipient_id: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        peer = self._resolve(recipient_id)
        session_id = (metadata or {}).get("session_id")
        # ``metadata`` is kept for gateway-side routing (session_id above) but is
        # not forwarded to the ACP SDK, which does not accept a metadata arg.
        await self._runtime.client.run_sync(peer, message, session_id=session_id)

    async def send_file(
        self,
        *,
        recipient_id: str,
        file_path: str,
        caption: str | None = None,
        attachment_type: str = "auto",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        raise NotImplementedError("ACP file attachments are not supported by the current transport")

    def _resolve(self, recipient_id: str) -> AcpPeer:
        peer = self._runtime.peers.get(recipient_id)
        if peer is None:
            raise ValueError(f"Unknown ACP peer: {recipient_id!r}")
        return peer
