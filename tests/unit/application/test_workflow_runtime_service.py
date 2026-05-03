"""Unit tests for WorkflowRuntimeService."""

from taskforce.application.workflow_runtime_service import WorkflowRuntimeService
from taskforce.core.domain.workflow_checkpoint import ResumeEvent
from taskforce.core.domain.workflow_definition import WorkflowDefinition, WorkflowStep
from taskforce.infrastructure.runtime.workflow_checkpoint_store import FileWorkflowCheckpointStore
from taskforce.infrastructure.runtime.workflow_definition_store import FileWorkflowDefinitionStore


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
    assert (
        resumed.state["latest_resume_event"]["payload"]["supplier_reply"] == "USt-ID nachgereicht"
    )


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


def test_workflow_definition_crud(tmp_path):
    checkpoint_store = FileWorkflowCheckpointStore(work_dir=str(tmp_path))
    definition_store = FileWorkflowDefinitionStore(work_dir=str(tmp_path))
    service = WorkflowRuntimeService(checkpoint_store, definition_store=definition_store)

    definition = WorkflowDefinition(
        workflow_id="invoice-review",
        name="Invoice Review",
        steps=[
            WorkflowStep(
                step_id="extract",
                agent="document_extraction",
                task="Extract invoice fields",
            )
        ],
    )

    service.save_definition(definition)

    loaded = service.get_definition("invoice-review")
    assert loaded == definition
    assert service.list_definitions() == [definition]
    assert service.delete_definition("invoice-review") is True
    assert service.get_definition("invoice-review") is None


def test_workflow_definition_steps_are_dependency_ordered(tmp_path):
    checkpoint_store = FileWorkflowCheckpointStore(work_dir=str(tmp_path))
    definition_store = FileWorkflowDefinitionStore(work_dir=str(tmp_path))
    service = WorkflowRuntimeService(checkpoint_store, definition_store=definition_store)
    service.save_definition(
        WorkflowDefinition(
            workflow_id="pipeline",
            name="Pipeline",
            steps=[
                WorkflowStep(
                    step_id="publish", agent="doc_writer", task="Publish", depends_on=["draft"]
                ),
                WorkflowStep(step_id="draft", agent="doc_writer", task="Draft"),
            ],
        )
    )

    ordered = service.ordered_steps("pipeline")

    assert [step.step_id for step in ordered] == ["draft", "publish"]


def test_workflow_definition_rejects_dependency_cycles(tmp_path):
    checkpoint_store = FileWorkflowCheckpointStore(work_dir=str(tmp_path))
    definition_store = FileWorkflowDefinitionStore(work_dir=str(tmp_path))
    service = WorkflowRuntimeService(checkpoint_store, definition_store=definition_store)
    service.save_definition(
        WorkflowDefinition(
            workflow_id="cycle",
            name="Cycle",
            steps=[
                WorkflowStep(step_id="a", agent="x", task="A", depends_on=["b"]),
                WorkflowStep(step_id="b", agent="x", task="B", depends_on=["a"]),
            ],
        )
    )

    try:
        service.ordered_steps("cycle")
        raise AssertionError("Expected ValueError")
    except ValueError as exc:
        assert "dependency cycle" in str(exc)
