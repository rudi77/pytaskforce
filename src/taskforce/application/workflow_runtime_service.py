"""Application service for resumable workflow checkpoints."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog

from taskforce.core.domain.schedule import (
    ScheduleAction,
    ScheduleActionType,
    ScheduleJob,
    ScheduleType,
)
from taskforce.core.domain.workflow_checkpoint import ResumeEvent, WorkflowCheckpoint
from taskforce.core.domain.workflow_definition import (
    WORKFLOW_TRIGGER_SCHEDULE,
    WorkflowDefinition,
    WorkflowStep,
)
from taskforce.core.interfaces.scheduler import SchedulerProtocol
from taskforce.infrastructure.runtime.workflow_checkpoint_store import (
    FileWorkflowCheckpointStore,
    validate_required_inputs,
)
from taskforce.infrastructure.runtime.workflow_definition_store import (
    FileWorkflowDefinitionStore,
)

logger = structlog.get_logger(__name__)


def _schedule_job_id(workflow_id: str) -> str:
    """Deterministic schedule-job id for a workflow's schedule trigger."""
    return f"workflow:{workflow_id}"


class WorkflowRuntimeService:
    """Create and resume workflow checkpoints, and keep schedule triggers in sync.

    When a :class:`SchedulerProtocol` is supplied, workflow definitions
    whose ``trigger == "schedule"`` are mirrored into the scheduler as
    ``ScheduleJob`` rows with ``ScheduleActionType.EXECUTE_WORKFLOW``
    on ``save_definition``. ``delete_definition`` removes the matching
    job. The actual execution-on-fire is the scheduler's
    ``event_callback`` concern (an event handler dispatching on
    ``EXECUTE_WORKFLOW``).
    """

    def __init__(
        self,
        store: FileWorkflowCheckpointStore,
        definition_store: FileWorkflowDefinitionStore | None = None,
        scheduler: SchedulerProtocol | None = None,
    ) -> None:
        self._store = store
        self._definition_store = definition_store
        self._scheduler = scheduler

    def save_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        """Persist a first-class workflow definition.

        Synchronous so existing FastAPI sync handlers stay unchanged.
        Scheduler integration is exposed separately via
        :meth:`register_schedule_for` so a caller with an event loop
        can opt in.
        """
        if self._definition_store is None:
            raise RuntimeError("Workflow definitions are not configured")
        return self._definition_store.save(definition)

    async def register_schedule_for(self, definition: WorkflowDefinition) -> str | None:
        """Mirror a workflow's schedule trigger into the wired scheduler.

        Returns the registered ``job_id`` on success, ``None`` when
        either no scheduler is wired or the definition has no
        schedule trigger / no cron expression. Removes any previous
        scheduled job for the same workflow id first so re-saving a
        definition with a changed cron doesn't accumulate orphans.
        """
        if self._scheduler is None:
            return None
        if definition.trigger != WORKFLOW_TRIGGER_SCHEDULE:
            # Trigger changed away from schedule → clean up if needed.
            await self._scheduler.remove_job(_schedule_job_id(definition.workflow_id))
            return None

        cron = (definition.trigger_config or {}).get("cron")
        if not cron:
            logger.warning(
                "workflow.schedule_trigger.missing_cron",
                workflow_id=definition.workflow_id,
            )
            return None

        job_id = _schedule_job_id(definition.workflow_id)
        # Remove any prior copy first so changing cron expressions is idempotent.
        await self._scheduler.remove_job(job_id)

        job = ScheduleJob(
            job_id=job_id,
            name=f"workflow:{definition.name or definition.workflow_id}",
            schedule_type=ScheduleType.CRON,
            expression=str(cron),
            action=ScheduleAction(
                action_type=ScheduleActionType.EXECUTE_WORKFLOW,
                params={"workflow_id": definition.workflow_id},
            ),
            tenant_id=str((definition.metadata or {}).get("tenant_id", "default")),
            agent_id=str((definition.metadata or {}).get("agent_id", "default")),
        )
        await self._scheduler.add_job(job)
        logger.info(
            "workflow.schedule_trigger.registered",
            workflow_id=definition.workflow_id,
            job_id=job_id,
            cron=cron,
        )
        return job_id

    async def unregister_schedule_for(self, workflow_id: str) -> bool:
        """Remove the scheduled job mirroring a workflow's schedule trigger.

        Returns ``True`` when a job was actually removed. Idempotent —
        calling on a workflow without a schedule trigger is a no-op.
        """
        if self._scheduler is None:
            return False
        return await self._scheduler.remove_job(_schedule_job_id(workflow_id))

    async def run_workflow_id(
        self,
        workflow_id: str,
        executor: Any,
        *,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Run a stored workflow's steps via ``executor``.

        Independent steps in the same dependency level run in parallel
        via ``asyncio.gather`` — true fan-out + join (ADR-022 §7, G6).
        Within a level the relative order in the returned list matches
        the definition's step order.

        Used by the schedule dispatcher (G4) and any other event source
        that knows a workflow_id but not the steps. Raises ``ValueError``
        when the workflow_id is unknown or its dependency graph is
        invalid.
        """
        definition = self.get_definition(workflow_id)
        if definition is None:
            raise ValueError(f"Workflow definition not found: {workflow_id}")
        return await self.run_steps(definition.steps, executor, session_id=session_id)

    async def run_steps(
        self,
        steps: list[WorkflowStep],
        executor: Any,
        *,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Execute ``steps`` level-by-level (parallel within a level).

        The dependency graph is split into Kahn-style "levels" of
        mutually independent steps. Each level is run with
        ``asyncio.gather`` so two independent missions truly overlap.
        Levels are awaited in order so a downstream step always sees
        every dependency's ``final_message`` in its mission text.

        Returned results are flattened to match the topological order
        callers used to see — caller code that expects a flat list of
        per-step dicts is unaffected.
        """
        levels = _dependency_levels(steps)
        results: dict[str, dict[str, Any]] = {}
        ordered: list[dict[str, Any]] = []

        for level in levels:
            outcomes = await asyncio.gather(
                *(
                    self._run_step(step, executor, results, session_id)
                    for step in level
                )
            )
            for step, outcome in zip(level, outcomes):
                results[step.step_id] = outcome
                ordered.append(outcome)
        return ordered

    async def _run_step(
        self,
        step: WorkflowStep,
        executor: Any,
        results: dict[str, dict[str, Any]],
        session_id: str | None,
    ) -> dict[str, Any]:
        """Execute a single step using ``results`` for dependency context."""
        mission = self._mission_for_step(step, results)
        execution = await executor.execute_mission(
            mission=mission,
            profile=step.agent,
            session_id=session_id,
        )
        return {
            "step_id": step.step_id,
            "agent": step.agent,
            "status": getattr(execution, "status", "completed"),
            "final_message": getattr(execution, "final_message", ""),
        }

    @staticmethod
    def _mission_for_step(
        step: WorkflowStep, results: dict[str, dict[str, Any]]
    ) -> str:
        """Compose the mission text fed to a step's agent."""
        if not step.depends_on:
            return step.task
        dependency_lines = [
            f"- {dependency_id}: {results[dependency_id].get('final_message', '')}"
            for dependency_id in step.depends_on
        ]
        return f"{step.task}\n\nDependency results:\n" + "\n".join(dependency_lines)

    def find_chat_workflow(self, name: str) -> WorkflowDefinition | None:
        """Return the chat-triggered workflow whose match name equals ``name``.

        Match is case-insensitive on ``trigger_config.match`` (or the
        workflow_id when no explicit match is configured). Returns
        ``None`` when no chat-triggered workflow matches; the gateway
        treats that as "no @-workflow by that name".
        """
        if self._definition_store is None:
            return None
        normalised = (name or "").strip().lower()
        if not normalised:
            return None
        for definition in self._definition_store.list():
            if definition.trigger != "chat":
                continue
            declared_match = (
                str((definition.trigger_config or {}).get("match", "")).strip().lower()
            )
            workflow_id_match = definition.workflow_id.strip().lower()
            if declared_match == normalised or workflow_id_match == normalised:
                return definition
        return None

    def find_webhook_workflow(self, path: str) -> WorkflowDefinition | None:
        """Return the workflow whose webhook trigger matches ``path``.

        The match is exact against ``trigger_config.path`` after
        stripping the leading slash from both sides — so a definition
        declared as ``path: hooks/run`` and a request URL ending in
        ``/hooks/run`` resolve to each other regardless of how the
        operator wrote them. Returns ``None`` when no definition has a
        matching webhook trigger; callers translate that to 404.
        """
        if self._definition_store is None:
            return None
        normalised = (path or "").strip("/").lower()
        for definition in self._definition_store.list():
            if definition.trigger != "webhook":
                continue
            declared = (
                str((definition.trigger_config or {}).get("path", "")).strip("/").lower()
            )
            if declared and declared == normalised:
                return definition
        return None

    def get_definition(self, workflow_id: str) -> WorkflowDefinition | None:
        """Get a workflow definition by id."""
        if self._definition_store is None:
            return None
        return self._definition_store.get(workflow_id)

    def list_definitions(self) -> list[WorkflowDefinition]:
        """List workflow definitions."""
        if self._definition_store is None:
            return []
        return self._definition_store.list()

    def delete_definition(self, workflow_id: str) -> bool:
        """Delete a workflow definition."""
        if self._definition_store is None:
            return False
        return self._definition_store.delete(workflow_id)

    def ordered_steps(self, workflow_id: str) -> list[WorkflowStep]:
        """Return workflow steps in dependency order."""
        definition = self.get_definition(workflow_id)
        if definition is None:
            raise ValueError(f"Workflow definition not found: {workflow_id}")
        return _order_steps(definition.steps)

    def create_wait_checkpoint(
        self,
        *,
        session_id: str,
        workflow_name: str,
        node_id: str,
        blocking_reason: str,
        required_inputs: dict[str, object],
        state: dict[str, object],
        question: str | None = None,
        run_id: str | None = None,
    ) -> WorkflowCheckpoint:
        """Persist a waiting checkpoint and return it."""
        checkpoint = WorkflowCheckpoint(
            run_id=run_id or uuid4().hex,
            session_id=session_id,
            workflow_name=workflow_name,
            node_id=node_id,
            status="waiting_external",
            blocking_reason=blocking_reason,
            required_inputs=required_inputs,
            state=state,
            question=question,
        )
        self._store.save(checkpoint)
        return checkpoint

    def resume(self, event: ResumeEvent) -> WorkflowCheckpoint:
        """Apply resume event and transition checkpoint to resumed state."""
        checkpoint = self._store.get(event.run_id)
        if checkpoint is None:
            raise ValueError(f"Workflow run not found: {event.run_id}")
        if checkpoint.status != "waiting_external":
            raise ValueError(
                f"Workflow run '{event.run_id}' is not waiting (status={checkpoint.status})"
            )

        valid, error = validate_required_inputs(
            checkpoint.required_inputs,
            event.payload,
        )
        if not valid:
            raise ValueError(error or "Invalid resume payload")

        merged_state = dict(checkpoint.state)
        merged_state["latest_resume_event"] = asdict(event)
        history = list(merged_state.get("resume_events", []))
        history.append(asdict(event))
        merged_state["resume_events"] = history

        checkpoint.state = merged_state
        checkpoint.status = "resumed"
        checkpoint.updated_at = datetime.now(UTC).isoformat()
        self._store.save(checkpoint)
        return checkpoint

    def get(self, run_id: str) -> WorkflowCheckpoint | None:
        """Get checkpoint by run ID."""
        return self._store.get(run_id)


def _order_steps(steps: list[WorkflowStep]) -> list[WorkflowStep]:
    """Topologically order workflow steps and reject missing deps/cycles."""
    by_id = {step.step_id: step for step in steps}
    if len(by_id) != len(steps):
        raise ValueError("Workflow contains duplicate step IDs")
    for step in steps:
        missing = [dep for dep in step.depends_on if dep not in by_id]
        if missing:
            raise ValueError(f"Workflow step '{step.step_id}' depends on missing steps: {missing}")

    ordered: list[WorkflowStep] = []
    temporary: set[str] = set()
    permanent: set[str] = set()

    def visit(step: WorkflowStep) -> None:
        if step.step_id in permanent:
            return
        if step.step_id in temporary:
            raise ValueError(f"Workflow contains a dependency cycle at step '{step.step_id}'")
        temporary.add(step.step_id)
        for dependency_id in step.depends_on:
            visit(by_id[dependency_id])
        temporary.remove(step.step_id)
        permanent.add(step.step_id)
        ordered.append(step)

    for step in steps:
        visit(step)
    return ordered


def _dependency_levels(steps: list[WorkflowStep]) -> list[list[WorkflowStep]]:
    """Group steps into Kahn-style levels of mutual independence.

    Level 0 contains every step with no ``depends_on`` entry. Level
    *n+1* contains steps whose dependencies are all in levels 0..*n*.
    Steps in the same level are guaranteed independent of each other,
    so a runtime can execute them concurrently.

    Reuses :func:`_order_steps` for missing-dep / cycle / duplicate
    detection — invalid inputs raise ``ValueError`` before any level
    is built.
    """
    # Validate duplicates / missing deps / cycles first.
    _order_steps(steps)

    by_id = {step.step_id: step for step in steps}
    remaining_deps: dict[str, set[str]] = {
        step.step_id: set(step.depends_on) for step in steps
    }
    levels: list[list[WorkflowStep]] = []
    placed: set[str] = set()

    while remaining_deps:
        ready_ids = [
            step_id
            for step_id, deps in remaining_deps.items()
            if not deps - placed
        ]
        if not ready_ids:
            # _order_steps already rejects cycles, but be defensive.
            raise ValueError("Workflow contains a dependency cycle")
        # Preserve definition order within a level for reproducible output.
        ready_ids.sort(key=lambda sid: list(by_id).index(sid))
        levels.append([by_id[sid] for sid in ready_ids])
        placed.update(ready_ids)
        for sid in ready_ids:
            remaining_deps.pop(sid, None)
    return levels
