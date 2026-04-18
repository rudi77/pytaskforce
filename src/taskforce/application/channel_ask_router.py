"""Channel Ask Router - Extracted from AgentExecutor.

Handles channel-targeted ask_user routing via the Communication Gateway.
Ensures ask_user events have complete channel + recipient_id from the source
conversation context, sends questions, and polls for responses.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import structlog

from taskforce.application.executor import ProgressUpdate
from taskforce.core.domain.enums import EventType
from taskforce.core.domain.models import StreamEvent

logger = structlog.get_logger(__name__)


class ChannelAskRouter:
    """Routes channel-targeted ask_user calls via the Communication Gateway.

    Handles the full lifecycle: detect → send → poll → resume.
    """

    def __init__(self, gateway: Any) -> None:
        self._gateway = gateway
        self._logger = logger.bind(component="channel_ask_router")

    @staticmethod
    def is_ask_user(event: StreamEvent) -> bool:
        """Check whether a StreamEvent is any ASK_USER event."""
        return event.event_type == EventType.ASK_USER

    @staticmethod
    def is_plain_ask_user(event: StreamEvent) -> bool:
        """Check whether a StreamEvent is a plain (non-channel) ASK_USER."""
        if not ChannelAskRouter.is_ask_user(event):
            return False
        data = event.data or {}
        return not data.get("channel")

    @staticmethod
    def is_channel_targeted_ask(event: StreamEvent) -> bool:
        """Check whether a StreamEvent is a fully resolved channel-targeted ASK_USER."""
        if not ChannelAskRouter.is_ask_user(event):
            return False
        data = event.data or {}
        return bool(data.get("channel") and data.get("recipient_id"))

    def ensure_channel_complete(
        self,
        event: StreamEvent,
        source_channel: str,
        source_conversation_id: str | None,
    ) -> bool:
        """Ensure an ask_user event has both channel and recipient_id.

        Fills in any missing fields from the source conversation context.
        Handles all cases:
        - Plain ask (no channel, no recipient) → both filled from source
        - Partial ask (channel set, no recipient) → recipient filled from source
        - Complete ask (both set) → no-op

        Returns True if the event was modified, False if already complete.
        """
        if not self.is_ask_user(event):
            return False

        if event.data is None:
            event.data = {}

        modified = False
        if not event.data.get("channel"):
            event.data["channel"] = source_channel
            modified = True
        if not event.data.get("recipient_id"):
            event.data["recipient_id"] = source_conversation_id or ""
            modified = True

        if modified:
            self._logger.info(
                "ask_user.channel_completed",
                channel=event.data["channel"],
                recipient_id=event.data["recipient_id"],
                question=event.data.get("question", "")[:100],
            )

        return modified

    async def route_channel_question(
        self,
        *,
        session_id: str,
        channel: str,
        recipient_id: str,
        question: str,
    ) -> str | None:
        """Send a channel question via the gateway and poll for the response.

        Returns:
            Response text when the recipient answers, or None on timeout.
        """
        sent = await self._gateway.send_channel_question(
            session_id=session_id,
            channel=channel,
            recipient_id=recipient_id,
            question=question,
        )
        if not sent:
            self._logger.error(
                "channel_question.send_failed",
                session_id=session_id,
                channel=channel,
                recipient_id=recipient_id,
            )
            return None

        self._logger.info(
            "channel_question.polling",
            session_id=session_id,
            channel=channel,
            recipient_id=recipient_id,
        )

        poll_interval = 2.0
        max_wait = 600.0
        elapsed = 0.0

        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            response = await self._gateway.poll_channel_response(
                session_id=session_id
            )
            if response is not None:
                await self._gateway.clear_channel_question(
                    session_id=session_id
                )
                self._logger.info(
                    "channel_question.response_received",
                    session_id=session_id,
                    channel=channel,
                    recipient_id=recipient_id,
                )
                return response

        self._logger.warning(
            "channel_question.timeout",
            session_id=session_id,
            channel=channel,
            recipient_id=recipient_id,
            max_wait=max_wait,
        )
        # IMPORTANT: clean up the pending entry on timeout. Otherwise the
        # next inbound message from this recipient — even if it's a
        # completely new intent (e.g. a fresh photo) — gets matched as
        # the answer to this stale question, the photo's attachments are
        # silently lost, and the agent resumes from a bogus context.
        try:
            await self._gateway.clear_channel_question(session_id=session_id)
        except Exception as exc:
            self._logger.warning(
                "channel_question.timeout_cleanup_failed",
                session_id=session_id,
                error=str(exc),
            )
        return None

    @staticmethod
    def build_question_sent_update(event: StreamEvent) -> ProgressUpdate:
        """Build a ProgressUpdate for a channel question that was sent."""
        data = event.data or {}
        channel = data.get("channel", "")
        recipient = data.get("recipient_id", "")
        question = data.get("question", "")
        return ProgressUpdate(
            timestamp=event.timestamp,
            event_type=EventType.ASK_USER,
            message=f"Sending question to {channel}:{recipient}: {question}",
            details={**data, "channel_routed": True},
        )

    @staticmethod
    def build_response_received_update(
        channel_ask: dict[str, Any], response: str
    ) -> ProgressUpdate:
        """Build a ProgressUpdate when a channel response is received."""
        channel = channel_ask.get("channel", "")
        recipient = channel_ask.get("recipient_id", "")
        return ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.ASK_USER,
            message=f"Response received from {channel}:{recipient}: {response}",
            details={
                "channel": channel,
                "recipient_id": recipient,
                "response": response,
                "channel_response_received": True,
            },
        )
