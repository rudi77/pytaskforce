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


# ---------------------------------------------------------------------------
# ADR-022 §7: schedule-trigger ↔ SchedulerService integration
# ---------------------------------------------------------------------------


import pytest

from taskforce.core.domain.schedule import ScheduleActionType, ScheduleJob


class _FakeScheduler:
    """In-memory SchedulerProtocol stand-in for tests."""

    def __init__(self) -> None:
        self.jobs: dict[str, ScheduleJob] = {}
        self.add_calls: list[ScheduleJob] = []
        self.remove_calls: list[str] = []

    async def add_job(self, job: ScheduleJob) -> str:
        self.add_calls.append(job)
        self.jobs[job.job_id] = job
        return job.job_id

    async def remove_job(self, job_id: str) -> bool:
        self.remove_calls.append(job_id)
        return self.jobs.pop(job_id, None) is not None


@pytest.mark.asyncio
async def test_register_schedule_creates_execute_workflow_job(tmp_path):
    scheduler = _FakeScheduler()
    runtime = WorkflowRuntimeService(
        store=FileWorkflowCheckpointStore(work_dir=str(tmp_path)),
        definition_store=FileWorkflowDefinitionStore(work_dir=str(tmp_path)),
        scheduler=scheduler,
    )
    definition = WorkflowDefinition(
        workflow_id="report",
        name="Daily Report",
        trigger="schedule",
        trigger_config={"cron": "0 8 * * *"},
        steps=[WorkflowStep(step_id="s1", agent="reporter", task="run")],
    )

    job_id = await runtime.register_schedule_for(definition)

    assert job_id == "workflow:report"
    assert len(scheduler.add_calls) == 1
    job = scheduler.add_calls[0]
    assert job.action.action_type == ScheduleActionType.EXECUTE_WORKFLOW
    assert job.action.params["workflow_id"] == "report"
    assert job.expression == "0 8 * * *"


@pytest.mark.asyncio
async def test_register_schedule_replaces_previous_job(tmp_path):
    scheduler = _FakeScheduler()
    runtime = WorkflowRuntimeService(
        store=FileWorkflowCheckpointStore(work_dir=str(tmp_path)),
        definition_store=FileWorkflowDefinitionStore(work_dir=str(tmp_path)),
        scheduler=scheduler,
    )
    definition = WorkflowDefinition(
        workflow_id="report",
        name="Daily",
        trigger="schedule",
        trigger_config={"cron": "0 8 * * *"},
    )
    await runtime.register_schedule_for(definition)
    # Re-register with a different cron — old job must be removed first.
    updated = WorkflowDefinition(
        workflow_id="report",
        name="Daily",
        trigger="schedule",
        trigger_config={"cron": "0 9 * * *"},
    )
    await runtime.register_schedule_for(updated)

    # Two add_job calls (initial + replacement)
    assert len(scheduler.add_calls) == 2
    # Remove was called twice (once defensive in each register call)
    assert scheduler.remove_calls.count("workflow:report") == 2
    # Final stored job has the new expression
    assert scheduler.jobs["workflow:report"].expression == "0 9 * * *"


@pytest.mark.asyncio
async def test_register_schedule_skips_when_trigger_not_schedule(tmp_path):
    scheduler = _FakeScheduler()
    runtime = WorkflowRuntimeService(
        store=FileWorkflowCheckpointStore(work_dir=str(tmp_path)),
        definition_store=FileWorkflowDefinitionStore(work_dir=str(tmp_path)),
        scheduler=scheduler,
    )
    definition = WorkflowDefinition(
        workflow_id="manual-only",
        name="x",
        trigger="manual",
    )
    job_id = await runtime.register_schedule_for(definition)
    assert job_id is None
    assert scheduler.add_calls == []


@pytest.mark.asyncio
async def test_register_schedule_warns_on_missing_cron(tmp_path):
    scheduler = _FakeScheduler()
    runtime = WorkflowRuntimeService(
        store=FileWorkflowCheckpointStore(work_dir=str(tmp_path)),
        definition_store=FileWorkflowDefinitionStore(work_dir=str(tmp_path)),
        scheduler=scheduler,
    )
    definition = WorkflowDefinition(
        workflow_id="incomplete",
        name="x",
        trigger="schedule",
        trigger_config={},  # no cron
    )
    job_id = await runtime.register_schedule_for(definition)
    assert job_id is None
    assert scheduler.add_calls == []


@pytest.mark.asyncio
async def test_unregister_schedule_removes_job(tmp_path):
    scheduler = _FakeScheduler()
    runtime = WorkflowRuntimeService(
        store=FileWorkflowCheckpointStore(work_dir=str(tmp_path)),
        definition_store=FileWorkflowDefinitionStore(work_dir=str(tmp_path)),
        scheduler=scheduler,
    )
    await runtime.register_schedule_for(
        WorkflowDefinition(
            workflow_id="x",
            name="x",
            trigger="schedule",
            trigger_config={"cron": "* * * * *"},
        )
    )
    assert "workflow:x" in scheduler.jobs

    removed = await runtime.unregister_schedule_for("x")
    assert removed is True
    assert "workflow:x" not in scheduler.jobs


@pytest.mark.asyncio
async def test_register_schedule_noop_without_scheduler(tmp_path):
    """When no scheduler is wired the registration is a no-op."""
    runtime = WorkflowRuntimeService(
        store=FileWorkflowCheckpointStore(work_dir=str(tmp_path)),
        definition_store=FileWorkflowDefinitionStore(work_dir=str(tmp_path)),
    )
    definition = WorkflowDefinition(
        workflow_id="x",
        name="x",
        trigger="schedule",
        trigger_config={"cron": "* * * * *"},
    )
    assert await runtime.register_schedule_for(definition) is None
    assert await runtime.unregister_schedule_for("x") is False
