"""Tests for the framework's generalised ScheduleTool (ADR-022 §6)."""

from __future__ import annotations

import pytest

from taskforce.application.infrastructure_overrides import (
    clear_infrastructure_overrides,
    set_tenant_resolver,
)
from taskforce.core.domain.schedule import ScheduleJob
from taskforce.infrastructure.tools.native.schedule_tool import ScheduleTool


class _FakeScheduler:
    def __init__(self) -> None:
        self.added: list[ScheduleJob] = []
        self.removed: list[str] = []
        self.paused: list[str] = []
        self.resumed: list[str] = []
        self.jobs_by_id: dict[str, ScheduleJob] = {}

    async def add_job(self, job: ScheduleJob) -> str:
        self.added.append(job)
        self.jobs_by_id[job.job_id] = job
        return job.job_id

    async def remove_job(self, job_id: str) -> bool:
        self.removed.append(job_id)
        return self.jobs_by_id.pop(job_id, None) is not None

    async def pause_job(self, job_id: str) -> bool:
        self.paused.append(job_id)
        return job_id in self.jobs_by_id

    async def resume_job(self, job_id: str) -> bool:
        self.resumed.append(job_id)
        return job_id in self.jobs_by_id

    async def get_job(self, job_id: str) -> ScheduleJob | None:
        return self.jobs_by_id.get(job_id)

    async def list_jobs(self) -> list[ScheduleJob]:
        return list(self.jobs_by_id.values())


@pytest.fixture(autouse=True)
def _reset_resolver():
    clear_infrastructure_overrides()
    yield
    clear_infrastructure_overrides()


@pytest.mark.asyncio
async def test_add_inherits_default_tenant() -> None:
    scheduler = _FakeScheduler()
    tool = ScheduleTool(scheduler=scheduler)

    result = await tool.execute(
        action="add",
        name="daily-report",
        schedule_type="cron",
        expression="0 8 * * *",
        action_type="execute_mission",
        action_params={"mission": "send the report"},
    )

    assert result["success"] is True
    assert result["tenant_id"] == "default"
    assert len(scheduler.added) == 1
    assert scheduler.added[0].tenant_id == "default"


@pytest.mark.asyncio
async def test_add_inherits_current_tenant_from_resolver() -> None:
    set_tenant_resolver(lambda: "tenant-acme")
    scheduler = _FakeScheduler()
    tool = ScheduleTool(scheduler=scheduler)

    await tool.execute(
        action="add",
        name="x",
        schedule_type="cron",
        expression="* * * * *",
        action_type="execute_mission",
        action_params={"mission": "do work"},
    )

    assert scheduler.added[0].tenant_id == "tenant-acme"


@pytest.mark.asyncio
async def test_send_notification_without_message_is_rejected() -> None:
    """A send_notification schedule with no message would silently no-op
    when fired (dispatcher fallback to 'Scheduled notification: <name>'
    is never what the user wanted). Force the agent to either provide
    real text or switch to execute_mission for dynamic content."""
    scheduler = _FakeScheduler()
    tool = ScheduleTool(scheduler=scheduler)

    result = await tool.execute(
        action="add",
        name="status-update",
        schedule_type="interval",
        expression="10m",
        action_type="send_notification",
        action_params={},
    )

    assert result["success"] is False
    assert "message" in result["error"].lower()
    assert "execute_mission" in result["error"]
    assert scheduler.added == []


@pytest.mark.asyncio
async def test_send_notification_with_blank_message_is_rejected() -> None:
    scheduler = _FakeScheduler()
    tool = ScheduleTool(scheduler=scheduler)

    result = await tool.execute(
        action="add",
        name="status-update",
        schedule_type="interval",
        expression="10m",
        action_type="send_notification",
        action_params={"message": "   "},
    )

    assert result["success"] is False
    assert scheduler.added == []


@pytest.mark.asyncio
async def test_send_notification_with_message_is_accepted() -> None:
    scheduler = _FakeScheduler()
    tool = ScheduleTool(scheduler=scheduler)

    result = await tool.execute(
        action="add",
        name="pill-reminder",
        schedule_type="cron",
        expression="0 8 * * *",
        action_type="send_notification",
        action_params={"message": "Tabletten nehmen", "recipient_id": "u1"},
    )

    assert result["success"] is True
    assert len(scheduler.added) == 1


@pytest.mark.asyncio
async def test_validation_rejects_missing_expression_on_add() -> None:
    tool = ScheduleTool(scheduler=_FakeScheduler())
    valid, error = tool.validate_params(action="add")
    assert valid is False
    assert "expression" in (error or "")


@pytest.mark.asyncio
async def test_remove_pause_resume_get_validate_job_id() -> None:
    tool = ScheduleTool(scheduler=_FakeScheduler())
    for action in ("remove", "pause", "resume", "get"):
        valid, error = tool.validate_params(action=action)
        assert valid is False
        assert "job_id" in (error or "")


@pytest.mark.asyncio
async def test_no_scheduler_returns_error() -> None:
    tool = ScheduleTool(scheduler=None)
    result = await tool.execute(action="list")
    assert result["success"] is False
    assert "scheduler" in result["error"].lower()


@pytest.mark.asyncio
async def test_supports_execute_workflow_action_type() -> None:
    """ADR-022 §7: schedule jobs can carry execute_workflow as action."""
    scheduler = _FakeScheduler()
    tool = ScheduleTool(scheduler=scheduler)

    result = await tool.execute(
        action="add",
        name="run-report-workflow",
        schedule_type="cron",
        expression="0 9 * * *",
        action_type="execute_workflow",
        action_params={"workflow_id": "daily-report"},
    )

    assert result["success"] is True
    job = scheduler.added[0]
    assert job.action.action_type.value == "execute_workflow"
    assert job.action.params == {"workflow_id": "daily-report"}
