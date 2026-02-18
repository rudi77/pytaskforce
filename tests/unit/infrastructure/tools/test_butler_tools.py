"""Tests for butler-specific tools (schedule, reminder, rule_manager)."""

import pytest
from unittest.mock import AsyncMock

from taskforce.core.domain.schedule import ScheduleJob, ScheduleType
from taskforce.core.domain.trigger_rule import TriggerRule
from taskforce.infrastructure.tools.native.schedule_tool import ScheduleTool
from taskforce.infrastructure.tools.native.reminder_tool import ReminderTool
from taskforce.infrastructure.tools.native.rule_manager_tool import RuleManagerTool


class TestScheduleTool:
    """Tests for the ScheduleTool."""

    @pytest.fixture
    def mock_scheduler(self) -> AsyncMock:
        scheduler = AsyncMock()
        scheduler.add_job = AsyncMock(return_value="job123")
        scheduler.list_jobs = AsyncMock(return_value=[])
        scheduler.remove_job = AsyncMock(return_value=True)
        scheduler.pause_job = AsyncMock(return_value=True)
        scheduler.resume_job = AsyncMock(return_value=True)
        scheduler.get_job = AsyncMock(return_value=None)
        return scheduler

    @pytest.fixture
    def tool(self, mock_scheduler: AsyncMock) -> ScheduleTool:
        return ScheduleTool(scheduler=mock_scheduler)

    def test_properties(self, tool: ScheduleTool) -> None:
        assert tool.name == "schedule"
        assert tool.requires_approval is True
        assert "schedule" in tool.description.lower()

    async def test_add_job(self, tool: ScheduleTool) -> None:
        result = await tool.execute(
            action="add",
            name="daily_check",
            schedule_type="cron",
            expression="0 8 * * *",
            action_type="send_notification",
            action_params={"message": "Good morning!"},
        )
        assert result["success"] is True
        assert result["job_id"] == "job123"

    async def test_list_jobs(self, tool: ScheduleTool, mock_scheduler: AsyncMock) -> None:
        mock_scheduler.list_jobs.return_value = [
            ScheduleJob(name="job1"),
            ScheduleJob(name="job2"),
        ]
        result = await tool.execute(action="list")
        assert result["success"] is True
        assert result["count"] == 2

    async def test_remove_job(self, tool: ScheduleTool) -> None:
        result = await tool.execute(action="remove", job_id="job123")
        assert result["success"] is True

    async def test_no_scheduler(self) -> None:
        tool = ScheduleTool(scheduler=None)
        result = await tool.execute(action="list")
        assert result["success"] is False
        assert "not configured" in result["error"]

    def test_validate_params_add(self, tool: ScheduleTool) -> None:
        valid, error = tool.validate_params(action="add", expression="0 8 * * *")
        assert valid is True

        valid, error = tool.validate_params(action="add")
        assert valid is False
        assert "expression" in error

    def test_validate_params_remove(self, tool: ScheduleTool) -> None:
        valid, error = tool.validate_params(action="remove", job_id="abc")
        assert valid is True

        valid, error = tool.validate_params(action="remove")
        assert valid is False
        assert "job_id" in error


class TestReminderTool:
    """Tests for the ReminderTool."""

    @pytest.fixture
    def mock_scheduler(self) -> AsyncMock:
        scheduler = AsyncMock()
        scheduler.add_job = AsyncMock(return_value="reminder123")
        return scheduler

    @pytest.fixture
    def tool(self, mock_scheduler: AsyncMock) -> ReminderTool:
        return ReminderTool(scheduler=mock_scheduler)

    def test_properties(self, tool: ReminderTool) -> None:
        assert tool.name == "reminder"
        assert tool.requires_approval is True

    async def test_create_reminder(self, tool: ReminderTool) -> None:
        result = await tool.execute(
            remind_at="2026-02-18T14:00:00",
            message="Zahnarzttermin!",
            channel="telegram",
            recipient_id="42",
        )
        assert result["success"] is True
        assert result["job_id"] == "reminder123"

    async def test_no_scheduler(self) -> None:
        tool = ReminderTool(scheduler=None)
        result = await tool.execute(remind_at="2026-02-18T14:00:00", message="test")
        assert result["success"] is False

    def test_validate_params(self, tool: ReminderTool) -> None:
        valid, error = tool.validate_params(remind_at="2026-02-18T14:00:00", message="test")
        assert valid is True

        valid, error = tool.validate_params(message="test")
        assert valid is False
        assert "remind_at" in error

        valid, error = tool.validate_params(remind_at="not-a-date", message="test")
        assert valid is False
        assert "ISO 8601" in error


class TestRuleManagerTool:
    """Tests for the RuleManagerTool."""

    @pytest.fixture
    def mock_engine(self) -> AsyncMock:
        engine = AsyncMock()
        engine.add_rule = AsyncMock(return_value="rule123")
        engine.list_rules = AsyncMock(return_value=[])
        engine.remove_rule = AsyncMock(return_value=True)
        engine.get_rule = AsyncMock(return_value=None)
        return engine

    @pytest.fixture
    def tool(self, mock_engine: AsyncMock) -> RuleManagerTool:
        return RuleManagerTool(rule_engine=mock_engine)

    def test_properties(self, tool: RuleManagerTool) -> None:
        assert tool.name == "rule_manager"
        assert tool.requires_approval is True

    async def test_add_rule(self, tool: RuleManagerTool) -> None:
        result = await tool.execute(
            action="add",
            name="test_rule",
            trigger_source="calendar",
            trigger_event_type="calendar.upcoming",
            trigger_filters={"minutes_until": {"$lte": 30}},
            action_type="notify",
            action_params={"channel": "telegram"},
            action_template="Reminder: {{event.title}}",
        )
        assert result["success"] is True
        assert result["rule_id"] == "rule123"

    async def test_list_rules(self, tool: RuleManagerTool, mock_engine: AsyncMock) -> None:
        mock_engine.list_rules.return_value = [TriggerRule(name="r1")]
        result = await tool.execute(action="list")
        assert result["success"] is True
        assert result["count"] == 1

    async def test_remove_rule(self, tool: RuleManagerTool) -> None:
        result = await tool.execute(action="remove", rule_id="rule123")
        assert result["success"] is True

    async def test_no_engine(self) -> None:
        tool = RuleManagerTool(rule_engine=None)
        result = await tool.execute(action="list")
        assert result["success"] is False
        assert "not configured" in result["error"]

    def test_validate_params_add(self, tool: RuleManagerTool) -> None:
        valid, error = tool.validate_params(action="add", name="test", action_type="notify")
        assert valid is True

        valid, error = tool.validate_params(action="add")
        assert valid is False
        assert "name" in error

    def test_validate_params_remove(self, tool: RuleManagerTool) -> None:
        valid, error = tool.validate_params(action="remove", rule_id="abc")
        assert valid is True

        valid, error = tool.validate_params(action="remove")
        assert valid is False
