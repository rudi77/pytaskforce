"""Inbound adapter implementations for normalizing webhook payloads.

Each adapter knows how to extract a canonical message dict from the
raw JSON payload of a specific channel's webhook.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

import structlog


class TelegramInboundAdapter:
    """Normalize Telegram Bot API webhook updates.

    Extracts ``chat.id``, ``text``, and ``from.id`` from the standard
    Telegram ``Update`` object.
    """

    def __init__(self, bot_token: str | None = None) -> None:
        self._bot_token = bot_token
        self._logger = structlog.get_logger()

    @property
    def channel(self) -> str:
        return "telegram"

    def extract_message(self, raw_payload: dict[str, Any]) -> dict[str, Any]:
        """Extract normalized message from a Telegram Update payload.

        Args:
            raw_payload: The raw Telegram Update JSON.

        Returns:
            Dict with: conversation_id, message, sender_id, metadata.

        Raises:
            ValueError: If the payload has no message or text.
        """
        message_obj = raw_payload.get("message")
        if not message_obj:
            raise ValueError("Telegram payload has no 'message' field")

        text = message_obj.get("text", "")
        if not text:
            raise ValueError("Telegram message has no 'text' field")

        chat = message_obj.get("chat", {})
        chat_id = chat.get("id")
        if chat_id is None:
            raise ValueError("Telegram message has no 'chat.id'")

        sender = message_obj.get("from", {})
        sender_id = str(sender.get("id", "")) if sender else None

        return {
            "conversation_id": str(chat_id),
            "message": text,
            "sender_id": sender_id,
            "metadata": {
                "update_id": raw_payload.get("update_id"),
                "chat_type": chat.get("type"),
                "message_id": message_obj.get("message_id"),
            },
        }

    def verify_signature(self, *, raw_body: bytes, headers: dict[str, str]) -> bool:
        """Verify Telegram webhook secret token.

        Telegram sends the secret token in the ``X-Telegram-Bot-Api-Secret-Token``
        header. If no bot_token was configured, verification is skipped.
        """
        if not self._bot_token:
            return True

        expected = headers.get("x-telegram-bot-api-secret-token", "")
        if not expected:
            return True

        secret = hashlib.sha256(self._bot_token.encode()).hexdigest()
        return hmac.compare_digest(secret, expected)


class TeamsInboundAdapter:
    """Normalize Microsoft Teams Bot Framework Activity payloads.

    Extracts ``conversation.id``, ``text``, and ``from.id`` from the
    standard Teams Activity object.
    """

    def __init__(self) -> None:
        self._logger = structlog.get_logger()

    @property
    def channel(self) -> str:
        return "teams"

    def extract_message(self, raw_payload: dict[str, Any]) -> dict[str, Any]:
        """Extract normalized message from a Teams Activity payload.

        Args:
            raw_payload: The raw Teams Activity JSON.

        Returns:
            Dict with: conversation_id, message, sender_id, metadata.

        Raises:
            ValueError: If the payload is missing required fields.
        """
        conversation = raw_payload.get("conversation", {})
        conversation_id = conversation.get("id")
        if not conversation_id:
            raise ValueError("Teams payload missing 'conversation.id'")

        text = raw_payload.get("text", "")
        if not text:
            raise ValueError("Teams Activity has no 'text' field")

        sender = raw_payload.get("from", {})
        sender_id = sender.get("id")

        return {
            "conversation_id": conversation_id,
            "message": text,
            "sender_id": sender_id,
            "metadata": {
                "activity_type": raw_payload.get("type"),
                "activity_id": raw_payload.get("id"),
                "service_url": raw_payload.get("serviceUrl"),
                "conversation_reference": {
                    "conversation": conversation,
                    "bot": raw_payload.get("recipient"),
                    "service_url": raw_payload.get("serviceUrl"),
                },
            },
        }

    def verify_signature(self, *, raw_body: bytes, headers: dict[str, str]) -> bool:
        """Verify Teams Bot Framework JWT token.

        A full implementation would validate the ``Authorization`` header
        JWT against the Bot Framework public keys. For now, returns True.
        """
        self._logger.info("teams.signature_verification_not_implemented")
        return True
