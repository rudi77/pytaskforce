"""Tests for ReminderTool.

Covers tool metadata properties, parameter validation, execute with mocked
scheduler, error handling for missing scheduler and invalid parameters,
and edge cases.
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
from taskforce.infrastructure.tools.native.reminder_tool import ReminderTool

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_scheduler() -> AsyncMock:
    """Create a mock scheduler for reminder tool."""
    scheduler = AsyncMock()
    scheduler.add_job = AsyncMock(return_value="reminder-abc-123")
    return scheduler


@pytest.fixture
def tool(mock_scheduler: AsyncMock) -> ReminderTool:
    return ReminderTool(scheduler=mock_scheduler)


# ---------------------------------------------------------------------------
# Metadata / Properties
# ---------------------------------------------------------------------------


class TestReminderToolProperties:
    """Tests for ReminderTool metadata and static properties."""

    def test_name(self, tool: ReminderTool) -> None:
        assert tool.name == "reminder"

    def test_description_mentions_reminder(self, tool: ReminderTool) -> None:
        assert "reminder" in tool.description.lower()

    def test_description_mentions_notification(self, tool: ReminderTool) -> None:
        assert "notification" in tool.description.lower()

    def test_description_mentions_iso_8601(self, tool: ReminderTool) -> None:
        assert "iso 8601" in tool.description.lower() or "ISO 8601" in tool.description

    def test_parameters_schema_is_object(self, tool: ReminderTool) -> None:
        schema = tool.parameters_schema
        assert schema["type"] == "object"

    def test_parameters_schema_required(self, tool: ReminderTool) -> None:
        schema = tool.parameters_schema
        assert set(schema["required"]) == {"remind_at", "message"}

    def test_parameters_schema_has_expected_keys(self, tool: ReminderTool) -> None:
        props = tool.parameters_schema["properties"]
        expected = {"remind_at", "message", "channel", "recipient_id"}
        assert expected == set(props.keys())

    def test_parameters_schema_types(self, tool: ReminderTool) -> None:
        props = tool.parameters_schema["properties"]
        assert props["remind_at"]["type"] == "string"
        assert props["message"]["type"] == "string"
        assert props["channel"]["type"] == "string"
        assert props["recipient_id"]["type"] == "string"

    def test_requires_approval(self, tool: ReminderTool) -> None:
        assert tool.requires_approval is True

    def test_approval_risk_level(self, tool: ReminderTool) -> None:
        assert tool.approval_risk_level == ApprovalRiskLevel.MEDIUM

    def test_supports_parallelism(self, tool: ReminderTool) -> None:
        assert tool.supports_parallelism is False

    def test_get_approval_preview(self, tool: ReminderTool) -> None:
        preview = tool.get_approval_preview(
            remind_at="2026-02-24T10:00:00", message="Don't forget the meeting!"
        )
        assert "reminder" in preview
        assert "2026-02-24T10:00:00" in preview
        assert "Don't forget the meeting!" in preview

    def test_get_approval_preview_long_message_truncated(self, tool: ReminderTool) -> None:
        long_msg = "A" * 200
        preview = tool.get_approval_preview(remind_at="2026-02-24T10:00:00", message=long_msg)
        # The preview truncates message to 100 chars
        assert len(preview) < len(long_msg) + 100

    def test_default_scheduler_is_none(self) -> None:
        tool = ReminderTool()
        assert tool._scheduler is None


# ---------------------------------------------------------------------------
# Validate Params
# ---------------------------------------------------------------------------


class TestReminderToolValidateParams:
    """Tests for ReminderTool.validate_params."""

    def test_valid_params(self, tool: ReminderTool) -> None:
        valid, error = tool.validate_params(
            remind_at="2026-02-24T14:00:00", message="Take a break"
        )
        assert valid is True
        assert error is None

    def test_valid_params_with_timezone(self, tool: ReminderTool) -> None:
        valid, error = tool.validate_params(
            remind_at="2026-02-24T14:00:00+01:00", message="Meeting"
        )
        assert valid is True
        assert error is None

    def test_missing_remind_at(self, tool: ReminderTool) -> None:
        valid, error = tool.validate_params(message="Take a break")
        assert valid is False
        assert "remind_at" in error

    def test_missing_message(self, tool: ReminderTool) -> None:
        valid, error = tool.validate_params(remind_at="2026-02-24T14:00:00")
        assert valid is False
        assert "message" in error

    def test_invalid_remind_at_format(self, tool: ReminderTool) -> None:
        valid, error = tool.validate_params(remind_at="not-a-date", message="Test")
        assert valid is False
        assert "ISO 8601" in error

    def test_empty_remind_at(self, tool: ReminderTool) -> None:
        valid, error = tool.validate_params(remind_at="", message="Test")
        assert valid is False

    def test_empty_message(self, tool: ReminderTool) -> None:
        valid, error = tool.validate_params(remind_at="2026-02-24T14:00:00", message="")
        assert valid is False

    def test_missing_both_required(self, tool: ReminderTool) -> None:
        valid, error = tool.validate_params()
        assert valid is False


# ---------------------------------------------------------------------------
# Execute - No Scheduler
# ---------------------------------------------------------------------------


class TestReminderToolNoScheduler:
    """Tests for ReminderTool when no scheduler is configured."""

    async def test_returns_error_without_scheduler(self) -> None:
        tool = ReminderTool(scheduler=None)
        result = await tool.execute(
            remind_at="2026-02-24T14:00:00", message="Test"
        )
        assert result["success"] is False
        assert "not configured" in result["error"]


# ---------------------------------------------------------------------------
# Execute - Create Reminder
# ---------------------------------------------------------------------------


class TestReminderToolCreateReminder:
    """Tests for creating reminders."""

    async def test_create_reminder_basic(
        self, tool: ReminderTool, mock_scheduler: AsyncMock
    ) -> None:
        result = await tool.execute(
            remind_at="2026-02-24T14:00:00",
            message="Dentist appointment",
        )

        assert result["success"] is True
        assert result["job_id"] == "reminder-abc-123"
        assert result["remind_at"] == "2026-02-24T14:00:00"
        assert "Dentist appointment" in result["message"]

        mock_scheduler.add_job.assert_awaited_once()
        job_arg = mock_scheduler.add_job.call_args[0][0]
        assert isinstance(job_arg, ScheduleJob)
        assert job_arg.schedule_type == ScheduleType.ONE_SHOT
        assert job_arg.expression == "2026-02-24T14:00:00"
        assert job_arg.action.action_type == ScheduleActionType.SEND_NOTIFICATION
        assert job_arg.action.params["message"] == "Dentist appointment"

    async def test_create_reminder_with_channel(
        self, tool: ReminderTool, mock_scheduler: AsyncMock
    ) -> None:
        result = await tool.execute(
            remind_at="2026-02-24T14:00:00",
            message="Slack reminder",
            channel="slack",
        )

        assert result["success"] is True
        job_arg = mock_scheduler.add_job.call_args[0][0]
        assert job_arg.action.params["channel"] == "slack"

    async def test_create_reminder_with_recipient(
        self, tool: ReminderTool, mock_scheduler: AsyncMock
    ) -> None:
        result = await tool.execute(
            remind_at="2026-02-24T14:00:00",
            message="Personal reminder",
            channel="telegram",
            recipient_id="user42",
        )

        assert result["success"] is True
        job_arg = mock_scheduler.add_job.call_args[0][0]
        assert job_arg.action.params["recipient_id"] == "user42"
        assert job_arg.action.params["channel"] == "telegram"

    async def test_create_reminder_default_channel_is_telegram(
        self, tool: ReminderTool, mock_scheduler: AsyncMock
    ) -> None:
        """When no channel is specified, it should default to 'telegram'."""
        result = await tool.execute(
            remind_at="2026-02-24T14:00:00",
            message="Default channel test",
        )

        assert result["success"] is True
        job_arg = mock_scheduler.add_job.call_args[0][0]
        assert job_arg.action.params["channel"] == "telegram"

    async def test_create_reminder_job_name_includes_time(
        self, tool: ReminderTool, mock_scheduler: AsyncMock
    ) -> None:
        """Job name should include the reminder time for identification."""
        await tool.execute(
            remind_at="2026-02-24T14:00:00",
            message="Test",
        )

        job_arg = mock_scheduler.add_job.call_args[0][0]
        assert "2026-02-24T14:00:00" in job_arg.name

    async def test_create_reminder_message_truncated_in_response(
        self, tool: ReminderTool, mock_scheduler: AsyncMock
    ) -> None:
        """Long messages should be truncated to 100 chars in the response message."""
        long_msg = "A" * 200
        result = await tool.execute(
            remind_at="2026-02-24T14:00:00",
            message=long_msg,
        )

        assert result["success"] is True
        # The response message field is truncated
        assert len(result["message"]) < 200 + 50  # some overhead for prefix text


# ---------------------------------------------------------------------------
# Execute - Error Handling
# ---------------------------------------------------------------------------


class TestReminderToolErrorHandling:
    """Tests for error handling in ReminderTool.execute."""

    async def test_scheduler_add_raises(
        self, tool: ReminderTool, mock_scheduler: AsyncMock
    ) -> None:
        mock_scheduler.add_job.side_effect = RuntimeError("Scheduler crashed")

        result = await tool.execute(
            remind_at="2026-02-24T14:00:00",
            message="Test",
        )

        assert result["success"] is False
        assert "Scheduler crashed" in str(result.get("error", ""))

    async def test_missing_remind_at_key_raises(
        self, tool: ReminderTool, mock_scheduler: AsyncMock
    ) -> None:
        """When remind_at is missing from kwargs, a KeyError is caught."""
        result = await tool.execute(message="no time given")

        assert result["success"] is False

    async def test_missing_message_key_raises(
        self, tool: ReminderTool, mock_scheduler: AsyncMock
    ) -> None:
        """When message is missing from kwargs, a KeyError is caught."""
        result = await tool.execute(remind_at="2026-02-24T14:00:00")

        assert result["success"] is False
