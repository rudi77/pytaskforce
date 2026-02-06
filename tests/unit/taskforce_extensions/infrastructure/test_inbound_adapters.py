"""Tests for InboundAdapter implementations."""

import pytest

from taskforce_extensions.infrastructure.communication.inbound_adapters import (
    TeamsInboundAdapter,
    TelegramInboundAdapter,
)


class TestTelegramInboundAdapter:
    def test_extract_message_success(self) -> None:
        adapter = TelegramInboundAdapter()
        payload = {
            "update_id": 123,
            "message": {
                "message_id": 456,
                "from": {"id": 789, "first_name": "Test"},
                "chat": {"id": 111, "type": "private"},
                "text": "Hallo Bot!",
            },
        }
        result = adapter.extract_message(payload)
        assert result["conversation_id"] == "111"
        assert result["message"] == "Hallo Bot!"
        assert result["sender_id"] == "789"
        assert result["metadata"]["update_id"] == 123
        assert result["metadata"]["chat_type"] == "private"

    def test_extract_message_no_message(self) -> None:
        adapter = TelegramInboundAdapter()
        with pytest.raises(ValueError, match="no 'message' field"):
            adapter.extract_message({})

    def test_extract_message_no_text(self) -> None:
        adapter = TelegramInboundAdapter()
        with pytest.raises(ValueError, match="no 'text' field"):
            adapter.extract_message({"message": {"chat": {"id": 1}}})

    def test_extract_message_no_chat_id(self) -> None:
        adapter = TelegramInboundAdapter()
        with pytest.raises(ValueError, match="no 'chat.id'"):
            adapter.extract_message({"message": {"text": "hi", "chat": {}}})

    def test_verify_signature_no_token(self) -> None:
        adapter = TelegramInboundAdapter()
        assert adapter.verify_signature(raw_body=b"", headers={})

    def test_channel_name(self) -> None:
        adapter = TelegramInboundAdapter()
        assert adapter.channel == "telegram"


class TestTeamsInboundAdapter:
    def test_extract_message_success(self) -> None:
        adapter = TeamsInboundAdapter()
        payload = {
            "type": "message",
            "id": "activity-1",
            "text": "Hello Teams!",
            "conversation": {"id": "19:abc@thread.v2"},
            "from": {"id": "user-1"},
            "recipient": {"id": "bot-1"},
            "serviceUrl": "https://smba.trafficmanager.net/",
        }
        result = adapter.extract_message(payload)
        assert result["conversation_id"] == "19:abc@thread.v2"
        assert result["message"] == "Hello Teams!"
        assert result["sender_id"] == "user-1"
        assert result["metadata"]["activity_type"] == "message"
        assert "conversation_reference" in result["metadata"]

    def test_extract_message_no_conversation(self) -> None:
        adapter = TeamsInboundAdapter()
        with pytest.raises(ValueError, match="conversation.id"):
            adapter.extract_message({"text": "hi"})

    def test_extract_message_no_text(self) -> None:
        adapter = TeamsInboundAdapter()
        with pytest.raises(ValueError, match="no 'text'"):
            adapter.extract_message({"conversation": {"id": "x"}})

    def test_channel_name(self) -> None:
        adapter = TeamsInboundAdapter()
        assert adapter.channel == "teams"

    def test_verify_signature_always_true(self) -> None:
        adapter = TeamsInboundAdapter()
        assert adapter.verify_signature(raw_body=b"", headers={})
