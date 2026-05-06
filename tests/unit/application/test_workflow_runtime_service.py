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


def test_save_definition_rejects_dependency_cycles(tmp_path):
    checkpoint_store = FileWorkflowCheckpointStore(work_dir=str(tmp_path))
    definition_store = FileWorkflowDefinitionStore(work_dir=str(tmp_path))
    service = WorkflowRuntimeService(checkpoint_store, definition_store=definition_store)

    cycle = WorkflowDefinition(
        workflow_id="cycle",
        name="Cycle",
        steps=[
            WorkflowStep(step_id="a", agent="x", task="A", depends_on=["b"]),
            WorkflowStep(step_id="b", agent="x", task="B", depends_on=["a"]),
        ],
    )

    try:
        service.save_definition(cycle)
        raise AssertionError("Expected ValueError")
    except ValueError as exc:
        assert "dependency cycle" in str(exc)
    # The definition must NOT have been written to disk.
    assert service.get_definition("cycle") is None


def test_save_definition_rejects_dangling_depends_on(tmp_path):
    checkpoint_store = FileWorkflowCheckpointStore(work_dir=str(tmp_path))
    definition_store = FileWorkflowDefinitionStore(work_dir=str(tmp_path))
    service = WorkflowRuntimeService(checkpoint_store, definition_store=definition_store)

    bad = WorkflowDefinition(
        workflow_id="dangling",
        name="Dangling",
        steps=[
            WorkflowStep(step_id="a", agent="x", task="A", depends_on=["does-not-exist"]),
        ],
    )

    try:
        service.save_definition(bad)
        raise AssertionError("Expected ValueError")
    except ValueError as exc:
        assert "missing steps" in str(exc)
    assert service.get_definition("dangling") is None


def test_save_definition_rejects_empty_steps(tmp_path):
    checkpoint_store = FileWorkflowCheckpointStore(work_dir=str(tmp_path))
    definition_store = FileWorkflowDefinitionStore(work_dir=str(tmp_path))
    service = WorkflowRuntimeService(checkpoint_store, definition_store=definition_store)

    empty = WorkflowDefinition(workflow_id="nada", name="No steps", steps=[])

    try:
        service.save_definition(empty)
        raise AssertionError("Expected ValueError")
    except ValueError as exc:
        assert "at least one step" in str(exc)
    assert service.get_definition("nada") is None


def test_save_definition_rejects_malformed_cron(tmp_path):
    checkpoint_store = FileWorkflowCheckpointStore(work_dir=str(tmp_path))
    definition_store = FileWorkflowDefinitionStore(work_dir=str(tmp_path))
    service = WorkflowRuntimeService(checkpoint_store, definition_store=definition_store)

    bad_cron = WorkflowDefinition(
        workflow_id="bad-cron",
        name="Bad Cron",
        trigger="schedule",
        trigger_config={"cron": "this is not cron"},
        steps=[WorkflowStep(step_id="a", agent="x", task="A")],
    )

    try:
        service.save_definition(bad_cron)
        raise AssertionError("Expected ValueError")
    except ValueError as exc:
        assert "cron" in str(exc).lower()
    assert service.get_definition("bad-cron") is None


def test_save_definition_accepts_valid_cron(tmp_path):
    checkpoint_store = FileWorkflowCheckpointStore(work_dir=str(tmp_path))
    definition_store = FileWorkflowDefinitionStore(work_dir=str(tmp_path))
    service = WorkflowRuntimeService(checkpoint_store, definition_store=definition_store)

    good = WorkflowDefinition(
        workflow_id="good-cron",
        name="Good Cron",
        trigger="schedule",
        trigger_config={"cron": "0 8 * * *"},
        steps=[WorkflowStep(step_id="a", agent="x", task="A")],
    )

    service.save_definition(good)
    assert service.get_definition("good-cron") == good


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

    assert job_id == "workflow__report"
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
            steps=[WorkflowStep(step_id="a", agent="x", task="A")],
        )
    await runtime.register_schedule_for(definition)
    # Re-register with a different cron — old job must be removed first.
    updated = WorkflowDefinition(
            workflow_id="report",
        name="Daily",
        trigger="schedule",
        trigger_config={"cron": "0 9 * * *"},
            steps=[WorkflowStep(step_id="a", agent="x", task="A")],
        )
    await runtime.register_schedule_for(updated)

    # Two add_job calls (initial + replacement)
    assert len(scheduler.add_calls) == 2
    # Remove was called twice (once defensive in each register call)
    assert scheduler.remove_calls.count("workflow__report") == 2
    # Final stored job has the new expression
    assert scheduler.jobs["workflow__report"].expression == "0 9 * * *"


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
            steps=[WorkflowStep(step_id="a", agent="x", task="A")],
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
            steps=[WorkflowStep(step_id="a", agent="x", task="A")],
        )
    )
    assert "workflow__x" in scheduler.jobs

    removed = await runtime.unregister_schedule_for("x")
    assert removed is True
    assert "workflow__x" not in scheduler.jobs


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
            steps=[WorkflowStep(step_id="a", agent="x", task="A")],
        )
    assert await runtime.register_schedule_for(definition) is None
    assert await runtime.unregister_schedule_for("x") is False


# ---------------------------------------------------------------------------
# ADR-022 §7: webhook-trigger lookup
# ---------------------------------------------------------------------------


def test_find_webhook_workflow_matches_declared_path(tmp_path):
    runtime = WorkflowRuntimeService(
        store=FileWorkflowCheckpointStore(work_dir=str(tmp_path)),
        definition_store=FileWorkflowDefinitionStore(work_dir=str(tmp_path)),
    )
    runtime.save_definition(
        WorkflowDefinition(
            workflow_id="report",
            name="Daily",
            trigger="webhook",
            trigger_config={"path": "hooks/daily-report"},
            steps=[WorkflowStep(step_id="a", agent="x", task="A")],
        )
    )
    runtime.save_definition(
        WorkflowDefinition(
            workflow_id="manual",
            name="Manual",
            trigger="manual",
            steps=[WorkflowStep(step_id="a", agent="x", task="A")],
        )
    )

    found = runtime.find_webhook_workflow("hooks/daily-report")
    assert found is not None
    assert found.workflow_id == "report"


def test_find_webhook_workflow_normalises_leading_slashes(tmp_path):
    runtime = WorkflowRuntimeService(
        store=FileWorkflowCheckpointStore(work_dir=str(tmp_path)),
        definition_store=FileWorkflowDefinitionStore(work_dir=str(tmp_path)),
    )
    runtime.save_definition(
        WorkflowDefinition(
            workflow_id="r",
            name="x",
            trigger="webhook",
            trigger_config={"path": "/hooks/run"},
            steps=[WorkflowStep(step_id="a", agent="x", task="A")],
        )
    )
    # Request URL-derived path may or may not have a leading slash —
    # either form must resolve to the same definition.
    assert runtime.find_webhook_workflow("hooks/run") is not None
    assert runtime.find_webhook_workflow("/hooks/run") is not None


def test_find_webhook_workflow_returns_none_for_unknown_path(tmp_path):
    runtime = WorkflowRuntimeService(
        store=FileWorkflowCheckpointStore(work_dir=str(tmp_path)),
        definition_store=FileWorkflowDefinitionStore(work_dir=str(tmp_path)),
    )
    runtime.save_definition(
        WorkflowDefinition(
            workflow_id="r",
            name="x",
            trigger="webhook",
            trigger_config={"path": "hooks/run"},
            steps=[WorkflowStep(step_id="a", agent="x", task="A")],
        )
    )
    assert runtime.find_webhook_workflow("hooks/different") is None


def test_find_webhook_workflow_skips_non_webhook_triggers(tmp_path):
    runtime = WorkflowRuntimeService(
        store=FileWorkflowCheckpointStore(work_dir=str(tmp_path)),
        definition_store=FileWorkflowDefinitionStore(work_dir=str(tmp_path)),
    )
    runtime.save_definition(
        WorkflowDefinition(
            workflow_id="m",
            name="Manual same path",
            trigger="manual",
            trigger_config={"path": "hooks/run"},  # ignored — wrong trigger
            steps=[WorkflowStep(step_id="a", agent="x", task="A")],
        )
    )
    assert runtime.find_webhook_workflow("hooks/run") is None


# ---------------------------------------------------------------------------
# G3: save_definition + register_schedule_for auto-wiring contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_then_register_schedule_idempotent_round_trip(tmp_path) -> None:
    """save_definition stays sync, but the runtime service's register_schedule
    helper, used by the API layer, must turn a saved schedule-trigger
    definition into exactly one ScheduleJob."""
    scheduler = _FakeScheduler()
    runtime = WorkflowRuntimeService(
        store=FileWorkflowCheckpointStore(work_dir=str(tmp_path)),
        definition_store=FileWorkflowDefinitionStore(work_dir=str(tmp_path)),
        scheduler=scheduler,
    )
    definition = WorkflowDefinition(
            workflow_id="wf-3",
        name="Daily",
        trigger="schedule",
        trigger_config={"cron": "0 8 * * *"},
            steps=[WorkflowStep(step_id="a", agent="x", task="A")],
        )

    # Simulate the API route's two-step "persist then schedule" flow.
    saved = runtime.save_definition(definition)
    job_id_first = await runtime.register_schedule_for(saved)

    # Re-saving with the same definition must NOT accumulate jobs.
    saved_again = runtime.save_definition(saved)
    job_id_second = await runtime.register_schedule_for(saved_again)

    assert job_id_first == job_id_second == "workflow__wf-3"
    # Two registers (each removes-then-adds → 2 add_calls total)
    assert len(scheduler.add_calls) == 2
    # Final state has exactly one live job
    assert "workflow__wf-3" in scheduler.jobs


@pytest.mark.asyncio
async def test_delete_definition_then_unregister_clears_the_schedule(tmp_path) -> None:
    scheduler = _FakeScheduler()
    runtime = WorkflowRuntimeService(
        store=FileWorkflowCheckpointStore(work_dir=str(tmp_path)),
        definition_store=FileWorkflowDefinitionStore(work_dir=str(tmp_path)),
        scheduler=scheduler,
    )
    definition = WorkflowDefinition(
            workflow_id="wf-4",
        name="x",
        trigger="schedule",
        trigger_config={"cron": "* * * * *"},
            steps=[WorkflowStep(step_id="a", agent="x", task="A")],
        )
    runtime.save_definition(definition)
    await runtime.register_schedule_for(definition)
    assert "workflow__wf-4" in scheduler.jobs

    runtime.delete_definition("wf-4")
    removed = await runtime.unregister_schedule_for("wf-4")

    assert removed is True
    assert "workflow__wf-4" not in scheduler.jobs


# ---------------------------------------------------------------------------
# G6: independent steps run in parallel (fan-out + join)
# ---------------------------------------------------------------------------


import asyncio
import time

from taskforce.application.workflow_runtime_service import _dependency_levels


def test_dependency_levels_groups_by_independence() -> None:
    steps = [
        WorkflowStep(step_id="a", agent="x", task="t"),
        WorkflowStep(step_id="b", agent="x", task="t"),
        WorkflowStep(step_id="c", agent="x", task="t", depends_on=["a", "b"]),
        WorkflowStep(step_id="d", agent="x", task="t", depends_on=["c"]),
    ]
    levels = _dependency_levels(steps)
    assert [s.step_id for s in levels[0]] == ["a", "b"]  # independent fan-out
    assert [s.step_id for s in levels[1]] == ["c"]  # join
    assert [s.step_id for s in levels[2]] == ["d"]


def test_dependency_levels_preserves_definition_order_within_level() -> None:
    steps = [
        WorkflowStep(step_id="z", agent="x", task="t"),
        WorkflowStep(step_id="a", agent="x", task="t"),
    ]
    levels = _dependency_levels(steps)
    assert [s.step_id for s in levels[0]] == ["z", "a"]


def test_dependency_levels_rejects_cycles() -> None:
    steps = [
        WorkflowStep(step_id="a", agent="x", task="t", depends_on=["b"]),
        WorkflowStep(step_id="b", agent="x", task="t", depends_on=["a"]),
    ]
    with pytest.raises(ValueError):
        _dependency_levels(steps)


@pytest.mark.asyncio
async def test_independent_steps_run_in_parallel(tmp_path) -> None:
    """A workflow with two independent slow steps must finish in ~max(step),
    not sum(step) — proving fan-out runs them concurrently."""

    class _SlowExecutor:
        async def execute_mission(self, **kwargs):
            await asyncio.sleep(0.1)
            from taskforce.core.domain.models import ExecutionResult

            return ExecutionResult(
                session_id=kwargs.get("session_id") or "s",
                status="completed",
                final_message="ok",
            )

    runtime = WorkflowRuntimeService(
        store=FileWorkflowCheckpointStore(work_dir=str(tmp_path)),
        definition_store=FileWorkflowDefinitionStore(work_dir=str(tmp_path)),
    )
    runtime.save_definition(
        WorkflowDefinition(
            workflow_id="parallel",
            name="x",
            steps=[
                WorkflowStep(step_id="a", agent="x", task="t"),
                WorkflowStep(step_id="b", agent="x", task="t"),
                WorkflowStep(step_id="c", agent="x", task="t", depends_on=["a", "b"]),
            ],
        )
    )

    started = time.perf_counter()
    results = await runtime.run_workflow_id("parallel", _SlowExecutor())
    elapsed = time.perf_counter() - started

    assert len(results) == 3
    # Sequential would be ~0.3s, parallel-at-level should be ~0.2s.
    # Pick a generous threshold so test isn't flaky on busy CI.
    assert elapsed < 0.25, f"steps did not run in parallel (elapsed={elapsed:.3f}s)"


@pytest.mark.asyncio
async def test_dependency_results_visible_to_join_step(tmp_path) -> None:
    """A step that depends_on its predecessors must see their final_messages."""
    captured: list[str] = []

    class _CapturingExecutor:
        async def execute_mission(self, **kwargs):
            captured.append(kwargs["mission"])
            from taskforce.core.domain.models import ExecutionResult

            return ExecutionResult(
                session_id="s",
                status="completed",
                final_message=f"reply for {kwargs['profile']}",
            )

    runtime = WorkflowRuntimeService(
        store=FileWorkflowCheckpointStore(work_dir=str(tmp_path)),
        definition_store=FileWorkflowDefinitionStore(work_dir=str(tmp_path)),
    )
    runtime.save_definition(
        WorkflowDefinition(
            workflow_id="joiner",
            name="x",
            steps=[
                WorkflowStep(step_id="a", agent="alpha", task="ask alpha"),
                WorkflowStep(step_id="b", agent="beta", task="ask beta"),
                WorkflowStep(step_id="c", agent="gamma", task="merge", depends_on=["a", "b"]),
            ],
        )
    )
    await runtime.run_workflow_id("joiner", _CapturingExecutor())

    join_mission = next(m for m in captured if "merge" in m)
    assert "reply for alpha" in join_mission
    assert "reply for beta" in join_mission


# ---------------------------------------------------------------------------
# G7: ACP-mediated workflow steps
# ---------------------------------------------------------------------------


class _FakeAcpRunHandle:
    def __init__(self, output_text: str, status: str = "completed") -> None:
        self.status = status
        self.result = {"output_text": output_text}


class _FakeAcpRuntime:
    def __init__(self, output_text: str = "remote-reply") -> None:
        self.calls: list[tuple[str, str, str | None]] = []
        self._output_text = output_text
        self._raise: Exception | None = None

    def fail_with(self, exc: Exception) -> None:
        self._raise = exc

    async def call(self, peer_name: str, mission: str, *, session_id: str | None = None):
        self.calls.append((peer_name, mission, session_id))
        if self._raise is not None:
            raise self._raise
        return _FakeAcpRunHandle(self._output_text)


@pytest.mark.asyncio
async def test_step_with_acp_peer_calls_acp_runtime(tmp_path) -> None:
    acp = _FakeAcpRuntime(output_text="answer-from-remote")
    runtime = WorkflowRuntimeService(
        store=FileWorkflowCheckpointStore(work_dir=str(tmp_path)),
        definition_store=FileWorkflowDefinitionStore(work_dir=str(tmp_path)),
        acp_runtime=acp,
    )
    runtime.save_definition(
        WorkflowDefinition(
            workflow_id="acp-wf",
            name="x",
            steps=[
                WorkflowStep(
                    step_id="ask-remote",
                    agent="butler",
                    task="ping",
                    acp_peer="remote-butler",
                ),
            ],
        )
    )

    class _NoopExecutor:
        async def execute_mission(self, **kwargs):  # pragma: no cover — must not be called
            raise AssertionError("acp step must not call local executor")

    results = await runtime.run_workflow_id("acp-wf", _NoopExecutor())

    assert acp.calls == [("remote-butler", "ping", None)]
    assert results[0]["status"] == "completed"
    assert results[0]["final_message"] == "answer-from-remote"
    assert results[0]["acp_peer"] == "remote-butler"


@pytest.mark.asyncio
async def test_acp_step_permission_denied_yields_failed_result(tmp_path) -> None:
    acp = _FakeAcpRuntime()
    acp.fail_with(PermissionError("cross-tenant ACP denied"))
    runtime = WorkflowRuntimeService(
        store=FileWorkflowCheckpointStore(work_dir=str(tmp_path)),
        definition_store=FileWorkflowDefinitionStore(work_dir=str(tmp_path)),
        acp_runtime=acp,
    )
    runtime.save_definition(
        WorkflowDefinition(
            workflow_id="acp-denied",
            name="x",
            steps=[
                WorkflowStep(step_id="s1", agent="butler", task="ping", acp_peer="other-tenant")
            ],
        )
    )

    class _Noop:
        async def execute_mission(self, **kwargs):
            raise AssertionError

    results = await runtime.run_workflow_id("acp-denied", _Noop())
    assert results[0]["status"] == "failed"
    assert "denied" in results[0]["error"].lower()


@pytest.mark.asyncio
async def test_acp_step_fails_closed_when_no_runtime_wired(tmp_path) -> None:
    """An ACP step without an ACP runtime must not silently run locally."""

    class _NoopExecutor:
        async def execute_mission(self, **kwargs):
            raise AssertionError("acp step must not fall back to local execution")

    runtime = WorkflowRuntimeService(
        store=FileWorkflowCheckpointStore(work_dir=str(tmp_path)),
        definition_store=FileWorkflowDefinitionStore(work_dir=str(tmp_path)),
        # No acp_runtime wired
    )
    runtime.save_definition(
        WorkflowDefinition(
            workflow_id="fallback",
            name="x",
            steps=[
                WorkflowStep(
                    step_id="s",
                    agent="local-butler",
                    task="t",
                    acp_peer="remote-but-no-runtime",
                )
            ],
        )
    )

    results = await runtime.run_workflow_id("fallback", _NoopExecutor())
    assert results[0]["status"] == "failed"
    assert "ACP runtime is not configured" in results[0]["error"]


def test_workflow_step_yaml_round_trip_preserves_acp_peer() -> None:
    step = WorkflowStep(step_id="s", agent="a", task="t", acp_peer="peer-x")
    parsed = WorkflowStep.from_dict(step.to_dict())
    assert parsed.acp_peer == "peer-x"


def test_workflow_step_dict_omits_acp_peer_when_unset() -> None:
    step = WorkflowStep(step_id="s", agent="a", task="t")
    payload = step.to_dict()
    assert "acp_peer" not in payload
