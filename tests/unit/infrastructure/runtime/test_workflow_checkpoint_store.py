"""Unit tests for FileWorkflowCheckpointStore."""

from taskforce.core.domain.workflow_checkpoint import WorkflowCheckpoint
from taskforce.infrastructure.runtime.workflow_checkpoint_store import (
    FileWorkflowCheckpointStore,
    validate_required_inputs,
)


def test_save_and_get_checkpoint(tmp_path):
    store = FileWorkflowCheckpointStore(work_dir=str(tmp_path))
    checkpoint = WorkflowCheckpoint(
        run_id="run-a",
        session_id="s",
        workflow_name="wf",
        node_id="n1",
        status="waiting_external",
        blocking_reason="missing_data",
        required_inputs={"required": ["answer"]},
    )
    store.save(checkpoint)

    loaded = store.get("run-a")
    assert loaded is not None
    assert loaded.run_id == "run-a"


def test_list_waiting_filters_status(tmp_path):
    store = FileWorkflowCheckpointStore(work_dir=str(tmp_path))
    store.save(
        WorkflowCheckpoint(
            run_id="run-wait",
            session_id="s",
            workflow_name="wf",
            node_id="n1",
            status="waiting_external",
            blocking_reason="missing",
            required_inputs={},
        )
    )
    store.save(
        WorkflowCheckpoint(
            run_id="run-done",
            session_id="s",
            workflow_name="wf",
            node_id="n2",
            status="resumed",
            blocking_reason="ok",
            required_inputs={},
        )
    )

    waiting = store.list_waiting()
    assert len(waiting) == 1
    assert waiting[0].run_id == "run-wait"


def test_validate_required_inputs():
    valid, error = validate_required_inputs({"required": ["a"]}, {"a": 1})
    assert valid is True
    assert error is None

    valid, error = validate_required_inputs({"required": ["a"]}, {})
    assert valid is False
    assert "Missing required" in str(error)
