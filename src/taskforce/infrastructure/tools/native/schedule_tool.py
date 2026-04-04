"""Schedule tool for managing timed jobs.

Allows the agent to create, list, pause, resume, and remove
scheduled jobs (cron, interval, one-shot).
"""

from __future__ import annotations

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


class ScheduleTool:
    """Tool for managing scheduled jobs within the butler.

    Supports creating cron jobs, interval tasks, and one-shot reminders.
    The scheduler must be injected at construction time.
    """

    def __init__(self, scheduler: Any = None) -> None:
        self._scheduler = scheduler

    @property
    def name(self) -> str:
        return "schedule"

    @property
    def description(self) -> str:
        return (
            "Manage scheduled jobs for the butler. Create, list, pause, resume, "
            "or remove timed jobs. Supports cron expressions (e.g. '0 8 * * *' for "
            "daily at 8am), intervals (e.g. '15m', '1h'), and one-shot times. "
            "Jobs can trigger notifications or agent missions."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "list", "remove", "pause", "resume", "get"],
                    "description": "Schedule action to perform",
                },
                "job_id": {
                    "type": "string",
                    "description": "Job ID (for remove/pause/resume/get)",
                },
                "name": {
                    "type": "string",
                    "description": "Human-readable job name",
                },
                "schedule_type": {
                    "type": "string",
                    "enum": ["cron", "interval", "one_shot"],
                    "description": "Type of schedule",
                },
                "expression": {
                    "type": "string",
                    "description": (
                        "Schedule expression: cron ('0 8 * * *'), "
                        "interval ('15m', '1h', '30s'), "
                        "or ISO datetime for one_shot"
                    ),
                },
                "action_type": {
                    "type": "string",
                    "enum": ["execute_mission", "send_notification", "publish_event"],
                    "description": "What to do when the schedule fires",
                },
                "action_params": {
                    "type": "object",
                    "description": "Parameters for the action (mission text, notification details, etc.)",
                },
            },
            "required": ["action"],
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
        action = kwargs.get("action", "")
        name = kwargs.get("name", "")
        return f"Tool: {self.name}\nOperation: {action}\nJob: {name}"

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Execute a schedule management action."""
        if not self._scheduler:
            return {"success": False, "error": "Scheduler not configured."}

        action = kwargs.get("action")
        try:
            if action == "add":
                return await self._add_job(**kwargs)
            if action == "list":
                return await self._list_jobs()
            if action == "remove":
                return await self._remove_job(kwargs.get("job_id", ""))
            if action == "pause":
                return await self._pause_job(kwargs.get("job_id", ""))
            if action == "resume":
                return await self._resume_job(kwargs.get("job_id", ""))
            if action == "get":
                return await self._get_job(kwargs.get("job_id", ""))
            return {"success": False, "error": f"Unknown action: {action}"}
        except Exception as exc:
            return tool_error_payload(ToolError(f"{self.name} failed: {exc}", tool_name=self.name))

    async def _add_job(self, **kwargs: Any) -> dict[str, Any]:
        """Add a new scheduled job."""
        job = ScheduleJob(
            name=kwargs.get("name", "unnamed"),
            schedule_type=ScheduleType(kwargs.get("schedule_type", "cron")),
            expression=kwargs.get("expression", ""),
            action=ScheduleAction(
                action_type=ScheduleActionType(kwargs.get("action_type", "send_notification")),
                params=kwargs.get("action_params", {}),
            ),
        )
        job_id = await self._scheduler.add_job(job)
        return {
            "success": True,
            "job_id": job_id,
            "name": job.name,
            "message": f"Job '{job.name}' created with ID {job_id}",
        }

    async def _list_jobs(self) -> dict[str, Any]:
        """List all scheduled jobs."""
        jobs = await self._scheduler.list_jobs()
        return {
            "success": True,
            "jobs": [j.to_dict() for j in jobs],
            "count": len(jobs),
        }

    async def _remove_job(self, job_id: str) -> dict[str, Any]:
        """Remove a scheduled job."""
        removed = await self._scheduler.remove_job(job_id)
        if removed:
            return {"success": True, "message": f"Job {job_id} removed"}
        return {"success": False, "error": f"Job {job_id} not found"}

    async def _pause_job(self, job_id: str) -> dict[str, Any]:
        """Pause a scheduled job."""
        paused = await self._scheduler.pause_job(job_id)
        if paused:
            return {"success": True, "message": f"Job {job_id} paused"}
        return {"success": False, "error": f"Job {job_id} not found"}

    async def _resume_job(self, job_id: str) -> dict[str, Any]:
        """Resume a paused job."""
        resumed = await self._scheduler.resume_job(job_id)
        if resumed:
            return {"success": True, "message": f"Job {job_id} resumed"}
        return {"success": False, "error": f"Job {job_id} not found"}

    async def _get_job(self, job_id: str) -> dict[str, Any]:
        """Get details of a specific job."""
        job = await self._scheduler.get_job(job_id)
        if job:
            return {"success": True, "job": job.to_dict()}
        return {"success": False, "error": f"Job {job_id} not found"}

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters."""
        action = kwargs.get("action")
        if not action:
            return False, "Missing required parameter: action"
        if action == "add":
            if not kwargs.get("expression"):
                return False, "Missing required parameter: expression"
        if action in ("remove", "pause", "resume", "get"):
            if not kwargs.get("job_id"):
                return False, "Missing required parameter: job_id"
        return True, None
