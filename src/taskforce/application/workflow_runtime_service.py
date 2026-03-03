"""Application service for resumable workflow checkpoints."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from uuid import uuid4

from taskforce.core.domain.workflow_checkpoint import ResumeEvent, WorkflowCheckpoint
from taskforce.infrastructure.runtime.workflow_checkpoint_store import (
    FileWorkflowCheckpointStore,
    validate_required_inputs,
)


class WorkflowRuntimeService:
    """Create and resume workflow checkpoints."""

    def __init__(self, store: FileWorkflowCheckpointStore):
        self._store = store

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
