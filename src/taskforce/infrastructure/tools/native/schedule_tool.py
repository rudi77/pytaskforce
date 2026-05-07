"""Generalised schedule tool (ADR-022 §6).

Lets *any* agent (not just the Butler) register cron / interval /
one-shot jobs at runtime through the framework's
:class:`SchedulerProtocol`. Each created job inherits the current
request's tenant id (via
:func:`taskforce.application.infrastructure_overrides.get_current_tenant_id`),
so a multi-tenant deployment automatically scopes scheduling to the
caller's tenant — no agent code needs to know about tenants.

The tool moved out of ``taskforce_butler`` so the scheduling primitive
lives next to the framework's other native tools, consistent with the
ADR-022 §6 directive that runtime services be available to every
agent.
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
    """Tool for managing scheduled jobs at agent runtime.

    The scheduler must be injected at construction time. The framework's
    ``ToolRegistry`` does this automatically when the tool is resolved
    as part of an agent build.
    """

    def __init__(self, scheduler: Any = None) -> None:
        self._scheduler = scheduler

    @property
    def name(self) -> str:
        return "schedule"

    @property
    def description(self) -> str:
        return (
            "Manage scheduled jobs at agent runtime. Create, list, pause, "
            "resume, get, or remove timed jobs. Supports cron expressions "
            "(e.g. '0 8 * * *' for daily at 8am), intervals (e.g. '15m', "
            "'1h'), and one-shot times. Jobs can trigger notifications, "
            "agent missions, workflows, or events."
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
                    "enum": [
                        "execute_mission",
                        "send_notification",
                        "publish_event",
                        "execute_workflow",
                    ],
                    "description": "What to do when the schedule fires",
                },
                "action_params": {
                    "type": "object",
                    "description": (
                        "Parameters for the action (mission text, notification "
                        "details, workflow_id, etc.)"
                    ),
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
        """Add a new scheduled job, scoped to the current tenant."""
        # Late-import to avoid a hard dependency on the application layer
        # at module import time (tests that don't go through the host
        # entrypoint won't have it wired).
        from taskforce.application.infrastructure_overrides import (
            get_current_tenant_id,
        )

        action_type_str = kwargs.get("action_type", "send_notification")
        action_params: dict[str, Any] = kwargs.get("action_params", {}) or {}

        # Reject `send_notification` jobs without an actual message. The
        # dispatcher would otherwise fall back to "Scheduled notification:
        # <name>" which is never what the user actually wanted (e.g. recurring
        # status updates). Force the agent to either embed real text or use
        # action_type=execute_mission for dynamic content.
        if action_type_str == "send_notification":
            message = action_params.get("message", "")
            if not isinstance(message, str) or not message.strip():
                return tool_error_payload(
                    ToolError(
                        "send_notification schedule requires a non-empty "
                        "action_params.message. For recurring dynamic content "
                        "(e.g. live scores, weather, status checks), use "
                        "action_type=execute_mission instead and put the work "
                        "description in action_params.mission.",
                        tool_name=self.name,
                    )
                )

        tenant_id = get_current_tenant_id()

        job = ScheduleJob(
            name=kwargs.get("name", "unnamed"),
            schedule_type=ScheduleType(kwargs.get("schedule_type", "cron")),
            expression=kwargs.get("expression", ""),
            action=ScheduleAction(
                action_type=ScheduleActionType(action_type_str),
                params=action_params,
            ),
            tenant_id=tenant_id,
            agent_id=str(kwargs.get("agent_id", "default")),
        )
        job_id = await self._scheduler.add_job(job)
        return {
            "success": True,
            "job_id": job_id,
            "name": job.name,
            "tenant_id": tenant_id,
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
