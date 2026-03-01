"""Tests for resumable workflow domain models."""

from datetime import UTC, datetime

from taskforce.core.domain.workflow import (
    HumanInputRequest,
    WorkflowRunRecord,
    WorkflowRunResult,
    WorkflowStatus,
)


class TestWorkflowStatus:
    """Tests for WorkflowStatus enum."""

    def test_values(self) -> None:
        assert WorkflowStatus.RUNNING == "running"
        assert WorkflowStatus.WAITING_FOR_INPUT == "waiting_for_input"
        assert WorkflowStatus.COMPLETED == "completed"
        assert WorkflowStatus.FAILED == "failed"

    def test_from_string(self) -> None:
        assert WorkflowStatus("running") == WorkflowStatus.RUNNING
        assert WorkflowStatus("waiting_for_input") == WorkflowStatus.WAITING_FOR_INPUT


class TestHumanInputRequest:
    """Tests for HumanInputRequest dataclass."""

    def test_minimal(self) -> None:
        hir = HumanInputRequest(question="What is the account?")
        assert hir.question == "What is the account?"
        assert hir.channel is None
        assert hir.recipient_id is None
        assert hir.timeout_seconds is None
        assert hir.metadata == {}

    def test_channel_targeted(self) -> None:
        hir = HumanInputRequest(
            question="Missing tax number",
            channel="telegram",
            recipient_id="supplier_123",
            timeout_seconds=86400,
            metadata={"invoice_id": "INV-001"},
        )
        assert hir.channel == "telegram"
        assert hir.recipient_id == "supplier_123"
        assert hir.timeout_seconds == 86400
        assert hir.metadata == {"invoice_id": "INV-001"}

    def test_to_dict_minimal(self) -> None:
        hir = HumanInputRequest(question="Question?")
        d = hir.to_dict()
        assert d == {"question": "Question?"}
        assert "channel" not in d

    def test_to_dict_full(self) -> None:
        hir = HumanInputRequest(
            question="Q",
            channel="teams",
            recipient_id="user1",
            timeout_seconds=3600,
            metadata={"key": "value"},
        )
        d = hir.to_dict()
        assert d["channel"] == "teams"
        assert d["recipient_id"] == "user1"
        assert d["timeout_seconds"] == 3600
        assert d["metadata"] == {"key": "value"}

    def test_roundtrip(self) -> None:
        original = HumanInputRequest(
            question="Test?",
            channel="telegram",
            recipient_id="abc",
            timeout_seconds=120,
            metadata={"x": "y"},
        )
        restored = HumanInputRequest.from_dict(original.to_dict())
        assert restored.question == original.question
        assert restored.channel == original.channel
        assert restored.recipient_id == original.recipient_id
        assert restored.timeout_seconds == original.timeout_seconds
        assert restored.metadata == original.metadata


class TestWorkflowRunResult:
    """Tests for WorkflowRunResult dataclass."""

    def test_completed(self) -> None:
        result = WorkflowRunResult(
            status=WorkflowStatus.COMPLETED,
            outputs={"booking_id": "B-001"},
        )
        assert result.status == WorkflowStatus.COMPLETED
        assert result.outputs == {"booking_id": "B-001"}
        assert result.human_input_request is None
        assert result.error is None

    def test_waiting_for_input(self) -> None:
        hir = HumanInputRequest(question="Approve?")
        result = WorkflowRunResult(
            status=WorkflowStatus.WAITING_FOR_INPUT,
            human_input_request=hir,
        )
        assert result.status == WorkflowStatus.WAITING_FOR_INPUT
        assert result.human_input_request is not None
        assert result.human_input_request.question == "Approve?"

    def test_failed(self) -> None:
        result = WorkflowRunResult(
            status=WorkflowStatus.FAILED,
            error="Engine not found",
        )
        assert result.status == WorkflowStatus.FAILED
        assert result.error == "Engine not found"


class TestWorkflowRunRecord:
    """Tests for WorkflowRunRecord persistence model."""

    def test_to_dict_roundtrip(self) -> None:
        now = datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC)
        record = WorkflowRunRecord(
            run_id="run-001",
            session_id="session-001",
            workflow_name="smart-booking-auto",
            status=WorkflowStatus.WAITING_FOR_INPUT,
            engine="langgraph",
            input_data={"file_path": "/tmp/invoice.pdf"},
            checkpoint={"thread_id": "run-001", "step": "compliance"},
            human_input_request=HumanInputRequest(
                question="Missing tax?",
                channel="telegram",
                recipient_id="sup_1",
            ),
            created_at=now,
            updated_at=now,
        )
        d = record.to_dict()
        assert d["run_id"] == "run-001"
        assert d["status"] == "waiting_for_input"
        assert d["engine"] == "langgraph"
        assert d["human_input_request"]["channel"] == "telegram"

        restored = WorkflowRunRecord.from_dict(d)
        assert restored.run_id == record.run_id
        assert restored.session_id == record.session_id
        assert restored.status == WorkflowStatus.WAITING_FOR_INPUT
        assert restored.engine == "langgraph"
        assert restored.human_input_request is not None
        assert restored.human_input_request.channel == "telegram"

    def test_from_dict_without_hir(self) -> None:
        d = {
            "run_id": "run-002",
            "session_id": "s-002",
            "workflow_name": "wf",
            "status": "completed",
            "engine": "custom",
            "input_data": {},
            "checkpoint": {},
        }
        record = WorkflowRunRecord.from_dict(d)
        assert record.status == WorkflowStatus.COMPLETED
        assert record.human_input_request is None

    def test_defaults(self) -> None:
        record = WorkflowRunRecord(
            run_id="r1",
            session_id="s1",
            workflow_name="w1",
            status=WorkflowStatus.RUNNING,
            engine="test",
            input_data={},
            checkpoint={},
        )
        assert record.created_at is not None
        assert record.updated_at is not None
