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
            If photos or documents are present, ``metadata["attachment_refs"]``
            contains a list of ``{"file_id", "mime_type", "type"}`` dicts
            that must be downloaded separately.

        Raises:
            ValueError: If the payload has no message, or no text/media.
        """
        message_obj = raw_payload.get("message")
        if not message_obj:
            raise ValueError("Telegram payload has no 'message' field")

        text = (message_obj.get("text") or message_obj.get("caption") or "").strip()
        attachment_refs = self._extract_attachment_refs(message_obj)

        if not text and not attachment_refs:
            raise ValueError("Telegram message has no text or media content")

        if attachment_refs and not text:
            text = "Bitte analysiere diese Datei."

        chat = message_obj.get("chat", {})
        chat_id = chat.get("id")
        if chat_id is None:
            raise ValueError("Telegram message has no 'chat.id'")

        sender = message_obj.get("from", {})
        sender_id = str(sender.get("id", "")) if sender else None

        metadata: dict[str, Any] = {
            "update_id": raw_payload.get("update_id"),
            "chat_type": chat.get("type"),
            "message_id": message_obj.get("message_id"),
        }
        if attachment_refs:
            metadata["attachment_refs"] = attachment_refs

        return {
            "conversation_id": str(chat_id),
            "message": text,
            "sender_id": sender_id,
            "metadata": metadata,
        }

    @staticmethod
    def _extract_attachment_refs(message_obj: dict[str, Any]) -> list[dict[str, str]]:
        """Build lightweight attachment references from a Telegram message.

        These contain only ``file_id``, ``mime_type``, and ``type`` — the
        actual download happens later (in the webhook route handler).
        """
        refs: list[dict[str, str]] = []

        photos = message_obj.get("photo")
        if photos:
            largest = photos[-1]
            file_id = largest.get("file_id", "")
            if file_id:
                refs.append({"file_id": file_id, "mime_type": "image/jpeg", "type": "image"})

        document = message_obj.get("document")
        if document:
            file_id = document.get("file_id", "")
            mime_type = document.get("mime_type", "application/octet-stream")
            file_name = document.get("file_name", "document")
            if file_id:
                doc_type = "image" if mime_type.startswith("image/") else "document"
                refs.append(
                    {
                        "file_id": file_id,
                        "mime_type": mime_type,
                        "type": doc_type,
                        "file_name": file_name,
                    }
                )

        # Voice messages (OGG Opus, typically speech recordings).
        voice = message_obj.get("voice")
        if voice:
            file_id = voice.get("file_id", "")
            if file_id:
                refs.append(
                    {
                        "file_id": file_id,
                        "mime_type": "audio/ogg",
                        "type": "voice",
                        "duration": str(voice.get("duration", 0)),
                    }
                )

        # Audio file messages (MP3 or other formats).
        audio = message_obj.get("audio")
        if audio:
            file_id = audio.get("file_id", "")
            if file_id:
                refs.append(
                    {
                        "file_id": file_id,
                        "mime_type": audio.get("mime_type", "audio/mpeg"),
                        "type": "audio",
                        "file_name": audio.get("file_name", "audio.mp3"),
                    }
                )

        return refs

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
