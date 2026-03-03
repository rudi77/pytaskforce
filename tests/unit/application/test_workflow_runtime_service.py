"""Unit tests for WorkflowRuntimeService."""

from taskforce.application.workflow_runtime_service import WorkflowRuntimeService
from taskforce.core.domain.workflow_checkpoint import ResumeEvent
from taskforce.infrastructure.runtime.workflow_checkpoint_store import FileWorkflowCheckpointStore


def test_create_wait_checkpoint_and_resume(tmp_path):
    store = FileWorkflowCheckpointStore(work_dir=str(tmp_path))
    service = WorkflowRuntimeService(store)

    checkpoint = service.create_wait_checkpoint(
        session_id="sess-1",
        workflow_name="smart-booking-auto",
        node_id="missing_fields",
        blocking_reason="missing_supplier_data",
        required_inputs={"required": ["supplier_reply"]},
        state={"invoice_id": "inv-1"},
        question="Bitte Feld ergänzen",
        run_id="run-1",
    )

    assert checkpoint.status == "waiting_external"

    resumed = service.resume(
        ResumeEvent(
            run_id="run-1",
            input_type="supplier_reply",
            payload={"supplier_reply": "USt-ID nachgereicht"},
            sender_metadata={"channel": "telegram"},
        )
    )

    assert resumed.status == "resumed"
    assert resumed.state["latest_resume_event"]["payload"]["supplier_reply"] == "USt-ID nachgereicht"


def test_resume_rejects_missing_required_fields(tmp_path):
    store = FileWorkflowCheckpointStore(work_dir=str(tmp_path))
    service = WorkflowRuntimeService(store)

    service.create_wait_checkpoint(
        session_id="sess-1",
        workflow_name="smart-booking-auto",
        node_id="missing_fields",
        blocking_reason="missing_supplier_data",
        required_inputs={"required": ["supplier_reply"]},
        state={},
        run_id="run-2",
    )

    try:
        service.resume(
            ResumeEvent(
                run_id="run-2",
                input_type="supplier_reply",
                payload={},
            )
        )
        raise AssertionError("Expected ValueError")
    except ValueError as exc:
        assert "Missing required" in str(exc)
