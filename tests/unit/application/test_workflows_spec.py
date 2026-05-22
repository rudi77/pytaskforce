"""Spec-coverage tests for the workflow runtime — claims that lacked a
focused test: trigger-change job cleanup, resume guards + history, the
resume-and-continue session-id requirement, and cross-tenant webhook routing.

Spec: docs/spec/workflows.md — tests tagged @pytest.mark.spec("workflows.*").
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from taskforce.application.workflow_runtime_service import WorkflowRuntimeService
from taskforce.core.domain.schedule import ScheduleJob
from taskforce.core.domain.workflow_checkpoint import ResumeEvent
from taskforce.core.domain.workflow_definition import WorkflowDefinition, WorkflowStep
from taskforce.infrastructure.runtime.workflow_checkpoint_store import (
    FileWorkflowCheckpointStore,
)
from taskforce.infrastructure.runtime.workflow_definition_store import (
    FileWorkflowDefinitionStore,
)


class _FakeScheduler:
    """In-memory SchedulerProtocol stand-in."""

    def __init__(self) -> None:
        self.jobs: dict[str, ScheduleJob] = {}

    async def add_job(self, job: ScheduleJob) -> str:
        self.jobs[job.job_id] = job
        return job.job_id

    async def remove_job(self, job_id: str) -> bool:
        return self.jobs.pop(job_id, None) is not None


def _step() -> WorkflowStep:
    return WorkflowStep(step_id="a", agent="x", task="A")


# ---------------------------------------------------------------------------
# Schedule trigger lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.spec("workflows.change_trigger_away_from_schedule_removes_job")
@pytest.mark.asyncio
async def test_change_trigger_away_from_schedule_removes_job(tmp_path) -> None:
    """Re-saving a workflow with a non-schedule trigger drops its cron job."""
    scheduler = _FakeScheduler()
    service = WorkflowRuntimeService(
        store=FileWorkflowCheckpointStore(work_dir=str(tmp_path)),
        definition_store=FileWorkflowDefinitionStore(work_dir=str(tmp_path)),
        scheduler=scheduler,
    )

    await service.register_schedule_for(
        WorkflowDefinition(
            workflow_id="wf1",
            name="wf1",
            trigger="schedule",
            trigger_config={"cron": "* * * * *"},
            steps=[_step()],
        )
    )
    assert "workflow__wf1" in scheduler.jobs

    # Trigger flips to manual → the previously-registered job must be removed.
    job_id = await service.register_schedule_for(
        WorkflowDefinition(
            workflow_id="wf1", name="wf1", trigger="manual", steps=[_step()]
        )
    )
    assert job_id is None
    assert "workflow__wf1" not in scheduler.jobs


# ---------------------------------------------------------------------------
# Resume guards + history
# ---------------------------------------------------------------------------


@pytest.mark.spec("workflows.resume_non_waiting_returns_400")
def test_resume_non_waiting_returns_400(tmp_path) -> None:
    """A second resume on an already-resumed checkpoint is rejected."""
    service = WorkflowRuntimeService(FileWorkflowCheckpointStore(work_dir=str(tmp_path)))
    service.create_wait_checkpoint(
        session_id="s1",
        workflow_name="wf",
        node_id="n",
        blocking_reason="r",
        required_inputs={"required": ["f"]},
        state={},
        run_id="run-nw",
    )
    # First resume → status becomes 'resumed'.
    service.resume(ResumeEvent(run_id="run-nw", input_type="f", payload={"f": "v1"}))

    # Second resume on a non-waiting checkpoint → ValueError (route maps to 400).
    with pytest.raises(ValueError):
        service.resume(ResumeEvent(run_id="run-nw", input_type="f", payload={"f": "v2"}))


@pytest.mark.spec("workflows.resume_appends_to_state_history")
def test_resume_appends_to_state_history(tmp_path) -> None:
    """Each resume event is appended to ``state.resume_events`` history."""
    service = WorkflowRuntimeService(FileWorkflowCheckpointStore(work_dir=str(tmp_path)))
    service.create_wait_checkpoint(
        session_id="s1",
        workflow_name="wf",
        node_id="n",
        blocking_reason="r",
        required_inputs={"required": ["f"]},
        state={},
        run_id="run-hist",
    )
    resumed = service.resume(
        ResumeEvent(run_id="run-hist", input_type="f", payload={"f": "answer"})
    )

    history = resumed.state["resume_events"]
    assert isinstance(history, list) and len(history) == 1
    assert history[0]["payload"]["f"] == "answer"
    # The latest event is also surfaced separately.
    assert resumed.state["latest_resume_event"]["payload"]["f"] == "answer"


# ---------------------------------------------------------------------------
# resume-and-continue route
# ---------------------------------------------------------------------------


@pytest.mark.spec("workflows.resume_and_continue_requires_session_id")
def test_resume_and_continue_requires_session_id() -> None:
    """resume-and-continue returns 400 when the checkpoint has no session_id."""
    pytest.importorskip("fastapi")
    from unittest.mock import MagicMock

    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient

    from taskforce.api.dependencies import get_factory, get_workflow_runtime_service
    from taskforce.api.exception_handlers import taskforce_http_exception_handler
    from taskforce.api.routes import workflows as workflows_route

    service = MagicMock()
    service.resume = MagicMock(
        return_value=SimpleNamespace(
            session_id=None, status="resumed", workflow_name="wf", state={}
        )
    )

    app = FastAPI()
    app.add_exception_handler(HTTPException, taskforce_http_exception_handler)
    app.include_router(workflows_route.router, prefix="/api/v1")
    app.dependency_overrides[get_workflow_runtime_service] = lambda: service
    app.dependency_overrides[get_factory] = lambda: MagicMock()

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/v1/workflows/run-x/resume-and-continue",
        json={"input_type": "reply", "payload": {"f": "v"}},
    )
    assert response.status_code == 400
    assert "session_id" in response.json()["message"]


# ---------------------------------------------------------------------------
# Cross-tenant webhook routing
# ---------------------------------------------------------------------------


@pytest.mark.spec("workflows.webhook_cross_tenant_resolver_runs_under_owner")
@pytest.mark.asyncio
async def test_webhook_cross_tenant_resolver_runs_under_owner(monkeypatch) -> None:
    """A webhook path unknown to the current tenant is re-run under its owner."""
    pytest.importorskip("fastapi")
    from unittest.mock import MagicMock

    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient

    from taskforce.api.dependencies import get_executor, get_workflow_runtime_service
    from taskforce.api.exception_handlers import taskforce_http_exception_handler
    from taskforce.application import infrastructure_overrides as overrides
    from taskforce.api.routes import workflows as workflows_route

    overrides.clear_infrastructure_overrides()

    owner_definition = WorkflowDefinition(
        workflow_id="owned-wf",
        name="owned-wf",
        trigger="webhook",
        trigger_config={"path": "hooks/cross"},
        steps=[_step()],
    )

    # Current-tenant service knows nothing about the path → fast path misses.
    current_service = MagicMock()
    current_service.find_webhook_workflow = MagicMock(return_value=None)

    # Owner-tenant service (resolved inside the cross-tenant block) DOES know it.
    owner_service = MagicMock()
    owner_service.find_webhook_workflow = MagicMock(return_value=owner_definition)

    monkeypatch.setattr(
        workflows_route, "get_workflow_runtime_service", lambda: owner_service
    )
    monkeypatch.setattr(workflows_route, "get_executor", lambda: MagicMock())

    async def _fake_steps(workflow_id, svc, ex, session_id):  # noqa: ANN001
        return [{"step": "a", "status": "completed", "workflow_id": workflow_id}]

    monkeypatch.setattr(workflows_route, "_execute_workflow_steps", _fake_steps)

    ran_under: dict[str, str] = {}

    async def _resolver(path: str) -> str | None:
        return "owner-tenant" if "cross" in path else None

    async def _runner(tenant_id, fn):  # noqa: ANN001
        ran_under["tenant"] = tenant_id
        return await fn()

    overrides.set_webhook_workflow_resolver(_resolver)
    overrides.set_tenant_context_runner(_runner)

    try:
        app = FastAPI()
        app.add_exception_handler(HTTPException, taskforce_http_exception_handler)
        app.include_router(workflows_route.router, prefix="/api/v1")
        app.dependency_overrides[get_workflow_runtime_service] = lambda: current_service
        app.dependency_overrides[get_executor] = lambda: MagicMock()

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/api/v1/workflows/webhooks/hooks/cross", json={})
    finally:
        overrides.clear_infrastructure_overrides()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["workflow_id"] == "owned-wf"
    # The execution ran under the resolved owner tenant, not the caller's.
    assert ran_under["tenant"] == "owner-tenant"
