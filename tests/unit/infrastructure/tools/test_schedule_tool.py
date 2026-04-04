"""Tests for ScheduleTool.

Covers tool metadata properties, parameter validation, all execute actions
(add, list, remove, pause, resume, get), error handling for missing scheduler
and unknown actions, and edge cases.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from taskforce.core.domain.schedule import (
    ScheduleActionType,
    ScheduleJob,
    ScheduleType,
)
from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.tools.native.schedule_tool import ScheduleTool

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_scheduler() -> AsyncMock:
    """Create a mock scheduler with all required async methods."""
    scheduler = AsyncMock()
    scheduler.add_job = AsyncMock(return_value="job-abc-123")
    scheduler.list_jobs = AsyncMock(return_value=[])
    scheduler.remove_job = AsyncMock(return_value=True)
    scheduler.pause_job = AsyncMock(return_value=True)
    scheduler.resume_job = AsyncMock(return_value=True)
    scheduler.get_job = AsyncMock(return_value=None)
    return scheduler


@pytest.fixture
def tool(mock_scheduler: AsyncMock) -> ScheduleTool:
    return ScheduleTool(scheduler=mock_scheduler)


# ---------------------------------------------------------------------------
# Metadata / Properties
# ---------------------------------------------------------------------------


class TestScheduleToolProperties:
    """Tests for ScheduleTool metadata and static properties."""

    def test_name(self, tool: ScheduleTool) -> None:
        assert tool.name == "schedule"

    def test_description_mentions_schedule(self, tool: ScheduleTool) -> None:
        assert "schedule" in tool.description.lower()

    def test_description_mentions_cron(self, tool: ScheduleTool) -> None:
        assert "cron" in tool.description.lower()

    def test_description_mentions_interval(self, tool: ScheduleTool) -> None:
        assert "interval" in tool.description.lower()

    def test_parameters_schema_is_object(self, tool: ScheduleTool) -> None:
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "action" in schema["properties"]
        assert "action" in schema["required"]

    def test_parameters_schema_action_enum(self, tool: ScheduleTool) -> None:
        action_prop = tool.parameters_schema["properties"]["action"]
        assert set(action_prop["enum"]) == {"add", "list", "remove", "pause", "resume", "get"}

    def test_parameters_schema_schedule_type_enum(self, tool: ScheduleTool) -> None:
        st_prop = tool.parameters_schema["properties"]["schedule_type"]
        assert set(st_prop["enum"]) == {"cron", "interval", "one_shot"}

    def test_parameters_schema_action_type_enum(self, tool: ScheduleTool) -> None:
        at_prop = tool.parameters_schema["properties"]["action_type"]
        assert set(at_prop["enum"]) == {"execute_mission", "send_notification", "publish_event"}

    def test_parameters_schema_has_expected_keys(self, tool: ScheduleTool) -> None:
        props = tool.parameters_schema["properties"]
        expected = {
            "action", "job_id", "name", "schedule_type",
            "expression", "action_type", "action_params",
        }
        assert expected == set(props.keys())

    def test_requires_approval(self, tool: ScheduleTool) -> None:
        assert tool.requires_approval is True

    def test_approval_risk_level(self, tool: ScheduleTool) -> None:
        assert tool.approval_risk_level == ApprovalRiskLevel.MEDIUM

    def test_supports_parallelism(self, tool: ScheduleTool) -> None:
        assert tool.supports_parallelism is False

    def test_get_approval_preview(self, tool: ScheduleTool) -> None:
        preview = tool.get_approval_preview(action="add", name="daily_briefing")
        assert "schedule" in preview
        assert "add" in preview
        assert "daily_briefing" in preview

    def test_get_approval_preview_without_name(self, tool: ScheduleTool) -> None:
        preview = tool.get_approval_preview(action="list")
        assert "list" in preview


# ---------------------------------------------------------------------------
# Validate Params
# ---------------------------------------------------------------------------


class TestScheduleToolValidateParams:
    """Tests for ScheduleTool.validate_params."""

    def test_valid_add(self, tool: ScheduleTool) -> None:
        valid, error = tool.validate_params(action="add", expression="0 8 * * *")
        assert valid is True
        assert error is None

    def test_add_missing_expression(self, tool: ScheduleTool) -> None:
        valid, error = tool.validate_params(action="add")
        assert valid is False
        assert "expression" in error

    def test_valid_list(self, tool: ScheduleTool) -> None:
        valid, error = tool.validate_params(action="list")
        assert valid is True
        assert error is None

    def test_valid_remove_with_job_id(self, tool: ScheduleTool) -> None:
        valid, error = tool.validate_params(action="remove", job_id="job-abc-123")
        assert valid is True
        assert error is None

    def test_remove_missing_job_id(self, tool: ScheduleTool) -> None:
        valid, error = tool.validate_params(action="remove")
        assert valid is False
        assert "job_id" in error

    def test_pause_missing_job_id(self, tool: ScheduleTool) -> None:
        valid, error = tool.validate_params(action="pause")
        assert valid is False
        assert "job_id" in error

    def test_resume_missing_job_id(self, tool: ScheduleTool) -> None:
        valid, error = tool.validate_params(action="resume")
        assert valid is False
        assert "job_id" in error

    def test_get_missing_job_id(self, tool: ScheduleTool) -> None:
        valid, error = tool.validate_params(action="get")
        assert valid is False
        assert "job_id" in error

    def test_valid_pause_with_job_id(self, tool: ScheduleTool) -> None:
        valid, error = tool.validate_params(action="pause", job_id="j1")
        assert valid is True
        assert error is None

    def test_valid_resume_with_job_id(self, tool: ScheduleTool) -> None:
        valid, error = tool.validate_params(action="resume", job_id="j1")
        assert valid is True
        assert error is None

    def test_valid_get_with_job_id(self, tool: ScheduleTool) -> None:
        valid, error = tool.validate_params(action="get", job_id="j1")
        assert valid is True
        assert error is None

    def test_missing_action(self, tool: ScheduleTool) -> None:
        valid, error = tool.validate_params()
        assert valid is False
        assert "action" in error


# ---------------------------------------------------------------------------
# Execute - No Scheduler
# ---------------------------------------------------------------------------


class TestScheduleToolNoScheduler:
    """Tests for ScheduleTool when no scheduler is configured."""

    async def test_returns_error_without_scheduler(self) -> None:
        tool = ScheduleTool(scheduler=None)
        result = await tool.execute(action="list")
        assert result["success"] is False
        assert "not configured" in result["error"]

    async def test_add_without_scheduler(self) -> None:
        tool = ScheduleTool(scheduler=None)
        result = await tool.execute(action="add", expression="0 8 * * *")
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Execute - Add Job
# ---------------------------------------------------------------------------


class TestScheduleToolAddJob:
    """Tests for adding scheduled jobs."""

    async def test_add_cron_job(self, tool: ScheduleTool, mock_scheduler: AsyncMock) -> None:
        result = await tool.execute(
            action="add",
            name="daily_briefing",
            schedule_type="cron",
            expression="0 8 * * *",
            action_type="send_notification",
            action_params={"message": "Good morning!"},
        )

        assert result["success"] is True
        assert result["job_id"] == "job-abc-123"
        assert result["name"] == "daily_briefing"
        assert "daily_briefing" in result["message"]

        mock_scheduler.add_job.assert_awaited_once()
        job_arg = mock_scheduler.add_job.call_args[0][0]
        assert isinstance(job_arg, ScheduleJob)
        assert job_arg.name == "daily_briefing"
        assert job_arg.schedule_type == ScheduleType.CRON
        assert job_arg.expression == "0 8 * * *"
        assert job_arg.action.action_type == ScheduleActionType.SEND_NOTIFICATION

    async def test_add_interval_job(self, tool: ScheduleTool, mock_scheduler: AsyncMock) -> None:
        result = await tool.execute(
            action="add",
            name="health_check",
            schedule_type="interval",
            expression="15m",
            action_type="execute_mission",
            action_params={"mission": "Check server health"},
        )

        assert result["success"] is True
        job_arg = mock_scheduler.add_job.call_args[0][0]
        assert job_arg.schedule_type == ScheduleType.INTERVAL
        assert job_arg.action.action_type == ScheduleActionType.EXECUTE_MISSION

    async def test_add_one_shot_job(self, tool: ScheduleTool, mock_scheduler: AsyncMock) -> None:
        result = await tool.execute(
            action="add",
            name="deploy_reminder",
            schedule_type="one_shot",
            expression="2026-02-24T15:00:00",
            action_type="send_notification",
            action_params={"message": "Time to deploy!"},
        )

        assert result["success"] is True
        job_arg = mock_scheduler.add_job.call_args[0][0]
        assert job_arg.schedule_type == ScheduleType.ONE_SHOT

    async def test_add_job_defaults(self, tool: ScheduleTool, mock_scheduler: AsyncMock) -> None:
        """Adding a job with minimal params should use defaults."""
        result = await tool.execute(
            action="add",
            expression="0 9 * * 1",
        )

        assert result["success"] is True
        job_arg = mock_scheduler.add_job.call_args[0][0]
        assert job_arg.name == "unnamed"
        assert job_arg.schedule_type == ScheduleType.CRON
        assert job_arg.action.action_type == ScheduleActionType.SEND_NOTIFICATION

    async def test_add_job_with_publish_event_action(
        self, tool: ScheduleTool, mock_scheduler: AsyncMock
    ) -> None:
        result = await tool.execute(
            action="add",
            name="event_publisher",
            schedule_type="cron",
            expression="*/5 * * * *",
            action_type="publish_event",
            action_params={"topic": "heartbeat"},
        )

        assert result["success"] is True
        job_arg = mock_scheduler.add_job.call_args[0][0]
        assert job_arg.action.action_type == ScheduleActionType.PUBLISH_EVENT
        assert job_arg.action.params == {"topic": "heartbeat"}


# ---------------------------------------------------------------------------
# Execute - List Jobs
# ---------------------------------------------------------------------------


class TestScheduleToolListJobs:
    """Tests for listing scheduled jobs."""

    async def test_list_empty(self, tool: ScheduleTool, mock_scheduler: AsyncMock) -> None:
        mock_scheduler.list_jobs.return_value = []
        result = await tool.execute(action="list")

        assert result["success"] is True
        assert result["count"] == 0
        assert result["jobs"] == []

    async def test_list_with_jobs(self, tool: ScheduleTool, mock_scheduler: AsyncMock) -> None:
        jobs = [
            ScheduleJob(job_id="j1", name="morning_briefing", expression="0 8 * * *"),
            ScheduleJob(
                job_id="j2",
                name="health_check",
                schedule_type=ScheduleType.INTERVAL,
                expression="15m",
            ),
        ]
        mock_scheduler.list_jobs.return_value = jobs

        result = await tool.execute(action="list")

        assert result["success"] is True
        assert result["count"] == 2
        assert len(result["jobs"]) == 2
        assert result["jobs"][0]["name"] == "morning_briefing"
        assert result["jobs"][1]["name"] == "health_check"


# ---------------------------------------------------------------------------
# Execute - Remove Job
# ---------------------------------------------------------------------------


class TestScheduleToolRemoveJob:
    """Tests for removing scheduled jobs."""

    async def test_remove_existing_job(
        self, tool: ScheduleTool, mock_scheduler: AsyncMock
    ) -> None:
        mock_scheduler.remove_job.return_value = True
        result = await tool.execute(action="remove", job_id="j1")

        assert result["success"] is True
        assert "j1" in result["message"]
        mock_scheduler.remove_job.assert_awaited_once_with("j1")

    async def test_remove_nonexistent_job(
        self, tool: ScheduleTool, mock_scheduler: AsyncMock
    ) -> None:
        mock_scheduler.remove_job.return_value = False
        result = await tool.execute(action="remove", job_id="unknown")

        assert result["success"] is False
        assert "not found" in result["error"]


# ---------------------------------------------------------------------------
# Execute - Pause Job
# ---------------------------------------------------------------------------


class TestScheduleToolPauseJob:
    """Tests for pausing scheduled jobs."""

    async def test_pause_existing_job(
        self, tool: ScheduleTool, mock_scheduler: AsyncMock
    ) -> None:
        mock_scheduler.pause_job.return_value = True
        result = await tool.execute(action="pause", job_id="j1")

        assert result["success"] is True
        assert "paused" in result["message"]
        mock_scheduler.pause_job.assert_awaited_once_with("j1")

    async def test_pause_nonexistent_job(
        self, tool: ScheduleTool, mock_scheduler: AsyncMock
    ) -> None:
        mock_scheduler.pause_job.return_value = False
        result = await tool.execute(action="pause", job_id="nope")

        assert result["success"] is False
        assert "not found" in result["error"]


# ---------------------------------------------------------------------------
# Execute - Resume Job
# ---------------------------------------------------------------------------


class TestScheduleToolResumeJob:
    """Tests for resuming scheduled jobs."""

    async def test_resume_existing_job(
        self, tool: ScheduleTool, mock_scheduler: AsyncMock
    ) -> None:
        mock_scheduler.resume_job.return_value = True
        result = await tool.execute(action="resume", job_id="j1")

        assert result["success"] is True
        assert "resumed" in result["message"]
        mock_scheduler.resume_job.assert_awaited_once_with("j1")

    async def test_resume_nonexistent_job(
        self, tool: ScheduleTool, mock_scheduler: AsyncMock
    ) -> None:
        mock_scheduler.resume_job.return_value = False
        result = await tool.execute(action="resume", job_id="nope")

        assert result["success"] is False
        assert "not found" in result["error"]


# ---------------------------------------------------------------------------
# Execute - Get Job
# ---------------------------------------------------------------------------


class TestScheduleToolGetJob:
    """Tests for getting details of a specific job."""

    async def test_get_existing_job(
        self, tool: ScheduleTool, mock_scheduler: AsyncMock
    ) -> None:
        job = ScheduleJob(job_id="j1", name="morning_briefing", expression="0 8 * * *")
        mock_scheduler.get_job.return_value = job

        result = await tool.execute(action="get", job_id="j1")

        assert result["success"] is True
        assert result["job"]["name"] == "morning_briefing"
        assert result["job"]["job_id"] == "j1"
        mock_scheduler.get_job.assert_awaited_once_with("j1")

    async def test_get_nonexistent_job(
        self, tool: ScheduleTool, mock_scheduler: AsyncMock
    ) -> None:
        mock_scheduler.get_job.return_value = None

        result = await tool.execute(action="get", job_id="nope")

        assert result["success"] is False
        assert "not found" in result["error"]


# ---------------------------------------------------------------------------
# Execute - Error Handling
# ---------------------------------------------------------------------------


class TestScheduleToolErrorHandling:
    """Tests for error handling in ScheduleTool.execute."""

    async def test_unknown_action(self, tool: ScheduleTool) -> None:
        result = await tool.execute(action="restart")

        assert result["success"] is False
        assert "unknown" in result["error"].lower() or "Unknown" in result["error"]

    async def test_scheduler_add_raises(
        self, tool: ScheduleTool, mock_scheduler: AsyncMock
    ) -> None:
        mock_scheduler.add_job.side_effect = RuntimeError("Scheduler crashed")

        result = await tool.execute(
            action="add",
            name="test",
            expression="0 8 * * *",
        )

        assert result["success"] is False
        assert "Scheduler crashed" in str(result.get("error", ""))

    async def test_scheduler_list_raises(
        self, tool: ScheduleTool, mock_scheduler: AsyncMock
    ) -> None:
        mock_scheduler.list_jobs.side_effect = RuntimeError("DB connection failed")

        result = await tool.execute(action="list")

        assert result["success"] is False

    async def test_scheduler_remove_raises(
        self, tool: ScheduleTool, mock_scheduler: AsyncMock
    ) -> None:
        mock_scheduler.remove_job.side_effect = RuntimeError("DB error")

        result = await tool.execute(action="remove", job_id="j1")

        assert result["success"] is False

    async def test_scheduler_pause_raises(
        self, tool: ScheduleTool, mock_scheduler: AsyncMock
    ) -> None:
        mock_scheduler.pause_job.side_effect = RuntimeError("Timeout")

        result = await tool.execute(action="pause", job_id="j1")

        assert result["success"] is False

    async def test_scheduler_resume_raises(
        self, tool: ScheduleTool, mock_scheduler: AsyncMock
    ) -> None:
        mock_scheduler.resume_job.side_effect = RuntimeError("Timeout")

        result = await tool.execute(action="resume", job_id="j1")

        assert result["success"] is False

    async def test_scheduler_get_raises(
        self, tool: ScheduleTool, mock_scheduler: AsyncMock
    ) -> None:
        mock_scheduler.get_job.side_effect = RuntimeError("Timeout")

        result = await tool.execute(action="get", job_id="j1")

        assert result["success"] is False
