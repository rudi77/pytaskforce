"""Tests for core domain models: StreamEvent, TokenUsage, PendingQuestion, ExecutionResult."""

from datetime import datetime

from taskforce.core.domain.enums import EventType, ExecutionStatus
from taskforce.core.domain.models import (
    ExecutionResult,
    PendingQuestion,
    StreamEvent,
    TokenUsage,
)


class TestStreamEvent:
    """Tests for StreamEvent dataclass."""

    def test_create_with_enum_event_type(self) -> None:
        event = StreamEvent(event_type=EventType.STEP_START, data={"step": 1})
        assert event.event_type == EventType.STEP_START
        assert event.data == {"step": 1}
        assert isinstance(event.timestamp, datetime)

    def test_create_with_string_event_type(self) -> None:
        event = StreamEvent(event_type="custom_event", data={})
        assert event.event_type == "custom_event"

    def test_to_dict_with_enum_event_type(self) -> None:
        event = StreamEvent(event_type=EventType.TOOL_CALL, data={"tool": "python"})
        d = event.to_dict()
        assert d["event_type"] == "tool_call"
        assert d["data"] == {"tool": "python"}
        assert "timestamp" in d
        # Timestamp should be ISO format string
        datetime.fromisoformat(d["timestamp"])

    def test_to_dict_with_string_event_type(self) -> None:
        event = StreamEvent(event_type="my_event", data={"key": "value"})
        d = event.to_dict()
        assert d["event_type"] == "my_event"

    def test_to_dict_preserves_all_data(self) -> None:
        data = {"nested": {"key": [1, 2, 3]}, "flag": True}
        event = StreamEvent(event_type=EventType.LLM_TOKEN, data=data)
        d = event.to_dict()
        assert d["data"]["nested"]["key"] == [1, 2, 3]
        assert d["data"]["flag"] is True

    def test_timestamp_auto_generated(self) -> None:
        before = datetime.now()
        event = StreamEvent(event_type=EventType.COMPLETE, data={})
        after = datetime.now()
        assert before <= event.timestamp <= after

    def test_empty_data(self) -> None:
        event = StreamEvent(event_type=EventType.ERROR, data={})
        assert event.data == {}
        d = event.to_dict()
        assert d["data"] == {}

    def test_all_event_types_serialize(self) -> None:
        """Every EventType enum member should serialize correctly."""
        for et in EventType:
            event = StreamEvent(event_type=et, data={})
            d = event.to_dict()
            assert d["event_type"] == et.value


class TestTokenUsage:
    """Tests for TokenUsage dataclass."""

    def test_defaults(self) -> None:
        usage = TokenUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0

    def test_create_with_values(self) -> None:
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150

    def test_to_dict(self) -> None:
        usage = TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        d = usage.to_dict()
        assert d == {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        }

    def test_from_dict(self) -> None:
        data = {"prompt_tokens": 500, "completion_tokens": 200, "total_tokens": 700}
        usage = TokenUsage.from_dict(data)
        assert usage.prompt_tokens == 500
        assert usage.completion_tokens == 200
        assert usage.total_tokens == 700

    def test_from_dict_with_missing_keys(self) -> None:
        usage = TokenUsage.from_dict({})
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0

    def test_from_dict_partial_keys(self) -> None:
        usage = TokenUsage.from_dict({"prompt_tokens": 42})
        assert usage.prompt_tokens == 42
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0

    def test_roundtrip(self) -> None:
        original = TokenUsage(prompt_tokens=123, completion_tokens=456, total_tokens=579)
        restored = TokenUsage.from_dict(original.to_dict())
        assert restored.prompt_tokens == original.prompt_tokens
        assert restored.completion_tokens == original.completion_tokens
        assert restored.total_tokens == original.total_tokens


class TestPendingQuestion:
    """Tests for PendingQuestion dataclass."""

    def test_create_minimal(self) -> None:
        q = PendingQuestion(question="What file?")
        assert q.question == "What file?"
        assert q.context == ""
        assert q.tool_call_id == ""

    def test_create_full(self) -> None:
        q = PendingQuestion(
            question="Which branch?",
            context="We need to select a git branch",
            tool_call_id="call_abc123",
        )
        assert q.question == "Which branch?"
        assert q.context == "We need to select a git branch"
        assert q.tool_call_id == "call_abc123"

    def test_to_dict(self) -> None:
        q = PendingQuestion(question="Choose option", context="ctx", tool_call_id="tc1")
        d = q.to_dict()
        assert d == {
            "question": "Choose option",
            "context": "ctx",
            "tool_call_id": "tc1",
        }

    def test_from_dict(self) -> None:
        data = {"question": "Pick one", "context": "info", "tool_call_id": "id1"}
        q = PendingQuestion.from_dict(data)
        assert q.question == "Pick one"
        assert q.context == "info"
        assert q.tool_call_id == "id1"

    def test_from_dict_with_missing_keys(self) -> None:
        q = PendingQuestion.from_dict({})
        assert q.question == ""
        assert q.context == ""
        assert q.tool_call_id == ""

    def test_roundtrip(self) -> None:
        original = PendingQuestion(
            question="How many?", context="counting", tool_call_id="tc99"
        )
        restored = PendingQuestion.from_dict(original.to_dict())
        assert restored.question == original.question
        assert restored.context == original.context
        assert restored.tool_call_id == original.tool_call_id


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_create_minimal(self) -> None:
        result = ExecutionResult(
            session_id="sess-1",
            status=ExecutionStatus.COMPLETED,
            final_message="Done",
        )
        assert result.session_id == "sess-1"
        assert result.status == ExecutionStatus.COMPLETED
        assert result.final_message == "Done"
        assert result.execution_history == []
        assert result.todolist_id is None
        assert result.pending_question is None
        assert isinstance(result.token_usage, TokenUsage)

    def test_create_with_string_status(self) -> None:
        result = ExecutionResult(
            session_id="sess-2",
            status="completed",
            final_message="OK",
        )
        assert result.status == "completed"

    def test_status_value_with_enum(self) -> None:
        result = ExecutionResult(
            session_id="s1",
            status=ExecutionStatus.FAILED,
            final_message="Error",
        )
        assert result.status_value == "failed"

    def test_status_value_with_string(self) -> None:
        result = ExecutionResult(
            session_id="s1",
            status="paused",
            final_message="Waiting",
        )
        assert result.status_value == "paused"

    def test_to_dict_basic(self) -> None:
        result = ExecutionResult(
            session_id="sess-3",
            status=ExecutionStatus.COMPLETED,
            final_message="All done",
            execution_history=[{"step": 1, "action": "read"}],
            todolist_id="todo-1",
        )
        d = result.to_dict()
        assert d["session_id"] == "sess-3"
        assert d["status"] == "completed"
        assert d["final_message"] == "All done"
        assert d["execution_history"] == [{"step": 1, "action": "read"}]
        assert d["todolist_id"] == "todo-1"
        assert d["pending_question"] is None
        assert d["token_usage"] == {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    def test_to_dict_with_pending_question_object(self) -> None:
        pq = PendingQuestion(question="Confirm?", context="deploy", tool_call_id="c1")
        result = ExecutionResult(
            session_id="s1",
            status=ExecutionStatus.PAUSED,
            final_message="Waiting for input",
            pending_question=pq,
        )
        d = result.to_dict()
        assert d["pending_question"] == {
            "question": "Confirm?",
            "context": "deploy",
            "tool_call_id": "c1",
        }

    def test_to_dict_with_pending_question_dict(self) -> None:
        result = ExecutionResult(
            session_id="s2",
            status=ExecutionStatus.PAUSED,
            final_message="Paused",
            pending_question={"question": "Yes/No?", "context": "", "tool_call_id": ""},
        )
        d = result.to_dict()
        assert d["pending_question"] == {"question": "Yes/No?", "context": "", "tool_call_id": ""}

    def test_to_dict_with_token_usage_object(self) -> None:
        result = ExecutionResult(
            session_id="s1",
            status=ExecutionStatus.COMPLETED,
            final_message="Done",
            token_usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )
        d = result.to_dict()
        assert d["token_usage"]["prompt_tokens"] == 10
        assert d["token_usage"]["total_tokens"] == 15

    def test_to_dict_with_token_usage_dict(self) -> None:
        result = ExecutionResult(
            session_id="s1",
            status=ExecutionStatus.COMPLETED,
            final_message="Done",
            token_usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        )
        d = result.to_dict()
        assert d["token_usage"]["prompt_tokens"] == 100

    def test_to_dict_with_string_status(self) -> None:
        result = ExecutionResult(
            session_id="s1",
            status="failed",
            final_message="Oops",
        )
        d = result.to_dict()
        assert d["status"] == "failed"

    def test_all_statuses(self) -> None:
        """Test all ExecutionStatus values work correctly."""
        for status in ExecutionStatus:
            result = ExecutionResult(
                session_id="test",
                status=status,
                final_message=f"Status: {status.value}",
            )
            assert result.status_value == status.value

    def test_execution_history_default_is_independent(self) -> None:
        """Verify default execution_history lists are independent between instances."""
        r1 = ExecutionResult(session_id="a", status="ok", final_message="x")
        r2 = ExecutionResult(session_id="b", status="ok", final_message="y")
        r1.execution_history.append({"step": 1})
        assert r2.execution_history == []
