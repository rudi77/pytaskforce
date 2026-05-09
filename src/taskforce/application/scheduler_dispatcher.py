"""Dispatcher that turns scheduler-fired AgentEvents into actual work.

ADR-022 §6 / §7 — G4: when ``SchedulerService`` fires a job it emits
an ``AgentEvent`` (``SCHEDULE_TRIGGERED``) carrying the
``ScheduleAction`` payload. This module supplies the matching default
event-callback for the API process, so jobs created with
``ScheduleActionType.EXECUTE_WORKFLOW`` actually drive a
``WorkflowRuntimeService.run_workflow_id`` call when they fire.

The dispatcher is intentionally tiny: it knows about workflows. Other
action types (``EXECUTE_MISSION``, ``SEND_NOTIFICATION``, ...) already
have their own consumers (the rule engine / butler) and we don't
double-handle them here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def make_scheduler_event_callback(
    workflow_runtime: Any,
    executor: Any,
) -> Callable[[Any], Awaitable[None]]:
    """Build a scheduler ``event_callback`` that runs scheduled workflows.

    Args:
        workflow_runtime: A ``WorkflowRuntimeService`` instance or a
            zero-argument provider returning one. Providers let hosted
            runtimes resolve tenant-scoped stores at dispatch time.
        executor: The ``AgentExecutor`` to drive workflow steps with.

    Returns:
        An async callable suitable for ``SchedulerService(event_callback=...)``.
        The callable returns ``None`` regardless of dispatch outcome so a
        single failing workflow doesn't kill the scheduler's event loop.
    """

    async def _callback(event: Any) -> None:
        try:
            payload = getattr(event, "payload", None) or {}
            action = payload.get("action") or {}
            action_type = (action.get("action_type") or "").lower()
            if action_type != "execute_workflow":
                # Not ours — let other consumers (rule engine, etc.) handle it.
                return

            params = action.get("params") or {}
            workflow_id = params.get("workflow_id")
            if not workflow_id:
                logger.warning(
                    "scheduler_dispatcher.execute_workflow_missing_id",
                    job_id=payload.get("job_id"),
                )
                return

            logger.info(
                "scheduler_dispatcher.execute_workflow_started",
                job_id=payload.get("job_id"),
                workflow_id=workflow_id,
                tenant_id=payload.get("tenant_id"),
            )
            try:
                from taskforce.core.domain.trigger_context import (
                    SCHEDULED_WORKFLOW_ORIGIN,
                    trigger_origin,
                )

                async def _run() -> list[dict[str, Any]]:
                    runtime = workflow_runtime() if callable(workflow_runtime) else workflow_runtime
                    # Tag the execution so the approval gate can
                    # auto-approve workflow-vetted tools (issue #177).
                    with trigger_origin(SCHEDULED_WORKFLOW_ORIGIN):
                        return await runtime.run_workflow_id(workflow_id, executor)

                tenant_id = payload.get("tenant_id")
                if tenant_id:
                    from taskforce.application.infrastructure_overrides import (
                        get_tenant_context_runner,
                    )

                    runner = get_tenant_context_runner()
                    results = (
                        await runner(str(tenant_id), _run) if runner is not None else await _run()
                    )
                else:
                    results = await _run()
            except ValueError as exc:
                logger.warning(
                    "scheduler_dispatcher.execute_workflow_invalid",
                    job_id=payload.get("job_id"),
                    workflow_id=workflow_id,
                    error=str(exc),
                )
                return
            logger.info(
                "scheduler_dispatcher.execute_workflow_completed",
                job_id=payload.get("job_id"),
                workflow_id=workflow_id,
                step_count=len(results),
            )
        except Exception as exc:  # pragma: no cover — defensive
            logger.error(
                "scheduler_dispatcher.callback_failed",
                error=str(exc),
                exc_info=True,
            )

    return _callback
