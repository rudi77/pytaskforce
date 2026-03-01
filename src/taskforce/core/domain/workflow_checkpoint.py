"""Domain models for resumable human-in-the-loop workflow checkpoints."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class WorkflowCheckpoint:
    """Persisted checkpoint for resumable workflows."""

    run_id: str
    session_id: str
    workflow_name: str
    node_id: str
    status: str
    blocking_reason: str
    required_inputs: dict[str, Any]
    state: dict[str, Any] = field(default_factory=dict)
    question: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Serialize checkpoint to dictionary."""
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "workflow_name": self.workflow_name,
            "node_id": self.node_id,
            "status": self.status,
            "blocking_reason": self.blocking_reason,
            "required_inputs": self.required_inputs,
            "state": self.state,
            "question": self.question,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> WorkflowCheckpoint:
        """Deserialize checkpoint from dictionary."""
        return cls(
            run_id=str(payload["run_id"]),
            session_id=str(payload.get("session_id", "")),
            workflow_name=str(payload.get("workflow_name", "")),
            node_id=str(payload["node_id"]),
            status=str(payload["status"]),
            blocking_reason=str(payload.get("blocking_reason", "unknown")),
            required_inputs=dict(payload.get("required_inputs", {})),
            state=dict(payload.get("state", {})),
            question=payload.get("question"),
            created_at=str(payload.get("created_at", datetime.now(UTC).isoformat())),
            updated_at=str(payload.get("updated_at", datetime.now(UTC).isoformat())),
        )


@dataclass
class ResumeEvent:
    """Inbound event that resumes a waiting workflow."""

    run_id: str
    input_type: str
    payload: dict[str, Any]
    sender_metadata: dict[str, Any] = field(default_factory=dict)
