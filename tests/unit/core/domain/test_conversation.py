"""Tests for the Conversation domain model."""

from datetime import UTC, datetime

from taskforce.core.domain.conversation import Conversation, ConversationStatus


class TestConversation:
    def test_create_with_defaults(self):
        conv = Conversation(channel="telegram")
        assert conv.channel == "telegram"
        assert conv.status == ConversationStatus.ACTIVE
        assert conv.message_count == 0
        assert conv.topic is None
        assert conv.summary is None
        assert conv.archived_at is None
        assert conv.conversation_id  # auto-generated

    def test_touch_updates_activity(self):
        conv = Conversation(channel="cli")
        before = conv.last_activity
        conv.touch()
        assert conv.message_count == 1
        assert conv.last_activity >= before

    def test_archive(self):
        conv = Conversation(channel="cli")
        conv.archive(summary="Test summary")
        assert conv.status == ConversationStatus.ARCHIVED
        assert conv.summary == "Test summary"
        assert conv.archived_at is not None

    def test_archive_without_summary(self):
        conv = Conversation(channel="rest")
        conv.archive()
        assert conv.status == ConversationStatus.ARCHIVED
        assert conv.summary is None


class TestAgentRequest:
    def test_create_with_defaults(self):
        from taskforce.core.domain.request import AgentRequest

        req = AgentRequest(channel="telegram", message="Hello")
        assert req.channel == "telegram"
        assert req.message == "Hello"
        assert req.request_id  # auto-generated
        assert req.conversation_id is None
        assert req.sender_id is None
        assert req.metadata == {}
        assert req.created_at.tzinfo is not None

    def test_frozen(self):
        from taskforce.core.domain.request import AgentRequest

        req = AgentRequest(channel="cli", message="test")
        try:
            req.channel = "rest"  # type: ignore[misc]
            assert False, "Should be frozen"
        except AttributeError:
            pass
