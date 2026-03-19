"""Tests for TopicSegment and Conversation topic management."""

from datetime import UTC, datetime

from taskforce.core.domain.conversation import Conversation, TopicSegment


class TestTopicSegment:
    """Tests for the TopicSegment dataclass."""

    def test_creation_defaults(self) -> None:
        seg = TopicSegment(label="Test topic")
        assert seg.label == "Test topic"
        assert seg.is_active is True
        assert seg.ended_at is None
        assert seg.source == "user"
        assert seg.priority == 0
        assert seg.message_range == (0, 0)
        assert seg.summary is None

    def test_close(self) -> None:
        seg = TopicSegment(label="Test", message_range=(0, 0))
        seg.close(end_idx=5, summary="Discussed testing")
        assert seg.is_active is False
        assert seg.ended_at is not None
        assert seg.message_range == (0, 5)
        assert seg.summary == "Discussed testing"

    def test_close_without_summary(self) -> None:
        seg = TopicSegment(label="Test", message_range=(3, 3))
        seg.close(end_idx=8)
        assert seg.is_active is False
        assert seg.summary is None
        assert seg.message_range == (3, 8)


class TestConversationTopicManagement:
    """Tests for Conversation topic methods."""

    def test_start_topic(self) -> None:
        conv = Conversation(channel="test")
        seg = conv.start_topic("First topic", message_idx=0)
        assert seg.label == "First topic"
        assert seg.is_active is True
        assert conv.active_topic_id == seg.topic_id
        assert len(conv.topic_segments) == 1

    def test_start_second_topic_closes_first(self) -> None:
        conv = Conversation(channel="test")
        seg1 = conv.start_topic("Topic A", message_idx=0)
        seg2 = conv.start_topic("Topic B", message_idx=5)

        assert seg1.is_active is False
        assert seg1.ended_at is not None
        assert seg2.is_active is True
        assert conv.active_topic_id == seg2.topic_id
        assert len(conv.topic_segments) == 2

    def test_extend_topic(self) -> None:
        conv = Conversation(channel="test")
        conv.start_topic("Topic A", message_idx=0)
        conv.extend_topic(message_idx=3)
        assert conv.active_topic.message_range == (0, 4)

    def test_extend_topic_no_active(self) -> None:
        conv = Conversation(channel="test")
        # Should not raise.
        conv.extend_topic(message_idx=3)

    def test_active_topic_property(self) -> None:
        conv = Conversation(channel="test")
        assert conv.active_topic is None

        seg = conv.start_topic("Active", message_idx=0)
        assert conv.active_topic is seg

    def test_previous_user_topic(self) -> None:
        conv = Conversation(channel="test")
        seg1 = conv.start_topic("User topic", message_idx=0, source="user")
        seg2 = conv.start_topic("Event interrupt", message_idx=5, source="event")

        # seg1 is now closed, seg2 is active.
        previous = conv.previous_user_topic()
        assert previous is not None
        assert previous.topic_id == seg1.topic_id

    def test_previous_user_topic_none(self) -> None:
        conv = Conversation(channel="test")
        assert conv.previous_user_topic() is None

    def test_event_interruption_flow(self) -> None:
        """Simulate: User topic → Event interruption → Resume user topic."""
        conv = Conversation(channel="test")

        # User starts a topic.
        user_seg = conv.start_topic("Budget planning", message_idx=0, source="user")
        conv.extend_topic(4)

        # Event interrupts.
        event_seg = conv.start_topic("Calendar reminder", message_idx=5, source="event")
        assert user_seg.is_active is False
        assert event_seg.is_active is True

        # Event finishes, user resumes.
        resume_seg = conv.start_topic("Budget planning continued", message_idx=7, source="user")
        assert event_seg.is_active is False
        assert resume_seg.is_active is True

        # Previous user topic should be the budget planning.
        prev = conv.previous_user_topic()
        assert prev is not None
        assert prev.label == "Budget planning"
