"""Application service for resumable workflow checkpoints."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from uuid import uuid4

from taskforce.core.domain.workflow_checkpoint import ResumeEvent, WorkflowCheckpoint
from taskforce.core.domain.workflow_definition import WorkflowDefinition, WorkflowStep
from taskforce.infrastructure.runtime.workflow_checkpoint_store import (
    FileWorkflowCheckpointStore,
    validate_required_inputs,
)
from taskforce.infrastructure.runtime.workflow_definition_store import (
    FileWorkflowDefinitionStore,
)


class WorkflowRuntimeService:
    """Create and resume workflow checkpoints."""

    def __init__(
        self,
        store: FileWorkflowCheckpointStore,
        definition_store: FileWorkflowDefinitionStore | None = None,
    ) -> None:
        self._store = store
        self._definition_store = definition_store

    def save_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        """Persist a first-class workflow definition."""
        if self._definition_store is None:
            raise RuntimeError("Workflow definitions are not configured")
        return self._definition_store.save(definition)

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
