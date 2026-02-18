"""Reminder tool for creating one-shot reminders.

A convenience wrapper around the schedule tool for creating
simple time-based reminders that send a notification.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from taskforce.core.domain.errors import ToolError, tool_error_payload
from taskforce.core.domain.schedule import (
    ScheduleAction,
    ScheduleActionType,
    ScheduleJob,
    ScheduleType,
)
from taskforce.core.interfaces.tools import ApprovalRiskLevel

logger = structlog.get_logger(__name__)


class ReminderTool:
    """Tool for creating one-shot reminders.

    Creates a one-shot scheduled job that sends a notification
    at the specified time.
    """

    def __init__(self, scheduler: Any = None) -> None:
        self._scheduler = scheduler

    @property
    def name(self) -> str:
        return "reminder"

    @property
    def description(self) -> str:
        return (
            "Create a one-shot reminder that will send a notification at a specific time. "
            "Provide the reminder time as ISO 8601 datetime and the message to send. "
            "Optionally specify the notification channel (defaults to telegram)."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "remind_at": {
                    "type": "string",
                    "description": "ISO 8601 datetime for the reminder (e.g. '2026-02-18T14:00:00')",
                },
                "message": {
                    "type": "string",
                    "description": "Reminder message to send",
                },
                "channel": {
                    "type": "string",
                    "description": "Notification channel (default: telegram)",
                },
                "recipient_id": {
                    "type": "string",
                    "description": "Recipient ID for the notification",
                },
            },
            "required": ["remind_at", "message"],
        }

    @property
    def requires_approval(self) -> bool:
        return True

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.MEDIUM

    @property
    def supports_parallelism(self) -> bool:
        return False

    def get_approval_preview(self, **kwargs: Any) -> str:
        remind_at = kwargs.get("remind_at", "")
        message = kwargs.get("message", "")
        return f"Tool: {self.name}\nRemind at: {remind_at}\nMessage: {message[:100]}"

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Create a one-shot reminder."""
        if not self._scheduler:
            return {"success": False, "error": "Scheduler not configured."}

        try:
            remind_at = kwargs["remind_at"]
            message = kwargs["message"]
            channel = kwargs.get("channel", "telegram")
            recipient_id = kwargs.get("recipient_id", "")

            job = ScheduleJob(
                name=f"reminder_{remind_at}",
                schedule_type=ScheduleType.ONE_SHOT,
                expression=remind_at,
                action=ScheduleAction(
                    action_type=ScheduleActionType.SEND_NOTIFICATION,
                    params={
                        "channel": channel,
                        "recipient_id": recipient_id,
                        "message": message,
                    },
                ),
            )

            job_id = await self._scheduler.add_job(job)
            return {
                "success": True,
                "job_id": job_id,
                "remind_at": remind_at,
                "message": f"Reminder set for {remind_at}: {message[:100]}",
            }
        except Exception as exc:
            return tool_error_payload(ToolError(f"{self.name} failed: {exc}", tool_name=self.name))

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters."""
        if not kwargs.get("remind_at"):
            return False, "Missing required parameter: remind_at"
        if not kwargs.get("message"):
            return False, "Missing required parameter: message"
        try:
            datetime.fromisoformat(kwargs["remind_at"])
        except ValueError:
            return False, "remind_at must be a valid ISO 8601 datetime"
        return True, None
