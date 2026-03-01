"""Resumable Workflow Domain Models.

This module defines the core domain models for resumable workflows -
programmatic workflows (e.g. LangGraph graphs) that can pause at
human-input points, persist state, and resume when the response arrives.

Channel routing:
  - channel=None  -> ask current session user (CLI chat or HTTP API caller)
  - channel="telegram" -> ask via Telegram (e.g. supplier contact)
  - channel="teams"/"email"/... -> future channels via Communication Gateway
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from taskforce.core.utils.time import utc_now as _utc_now


class WorkflowStatus(str, Enum):
    """Status of a workflow run."""

    RUNNING = "running"
    WAITING_FOR_INPUT = "waiting_for_input"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class HumanInputRequest:
    """Describes what human input is needed to continue a workflow.

    Attributes:
        question: The question to present to the human.
        channel: Target channel (None = current session user via CLI/API).
        recipient_id: Target user on the channel.
        timeout_seconds: Optional auto-escalation timeout.
        metadata: Additional context for the human reviewer.
    """

    question: str
    channel: str | None = None
    recipient_id: str | None = None
    timeout_seconds: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        result: dict[str, Any] = {"question": self.question}
        if self.channel is not None:
            result["channel"] = self.channel
        if self.recipient_id is not None:
            result["recipient_id"] = self.recipient_id
        if self.timeout_seconds is not None:
            result["timeout_seconds"] = self.timeout_seconds
        if self.metadata:
            result["metadata"] = self.metadata
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HumanInputRequest:
        """Deserialize from dictionary."""
        return cls(
            question=str(data.get("question", "")),
            channel=data.get("channel"),
            recipient_id=data.get("recipient_id"),
            timeout_seconds=data.get("timeout_seconds"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True)
class WorkflowRunResult:
    """Result of a workflow start or resume call.

    Attributes:
        status: Current workflow status.
        outputs: Accumulated workflow outputs (step results, final data).
        human_input_request: Present when status is WAITING_FOR_INPUT.
        error: Error message when status is FAILED.
    """

    status: WorkflowStatus
    outputs: dict[str, Any] = field(default_factory=dict)
    human_input_request: HumanInputRequest | None = None
    error: str | None = None


@dataclass
class WorkflowRunRecord:
    """Persisted state of a workflow run.

    Captures everything needed to resume a paused workflow, including
    the engine-specific checkpoint data.

    Attributes:
        run_id: Unique run identifier.
        session_id: Parent agent session.
        workflow_name: Name of the skill/workflow.
        status: Current workflow status.
        engine: Engine identifier (e.g. "langgraph").
        input_data: Original workflow input.
        checkpoint: Engine-specific serialized state for resume.
        human_input_request: Pending human input request, if any.
        created_at: Run creation timestamp.
        updated_at: Last update timestamp.
    """

    run_id: str
    session_id: str
    workflow_name: str
    status: WorkflowStatus
    engine: str
    input_data: dict[str, Any]
    checkpoint: dict[str, Any]
    human_input_request: HumanInputRequest | None = None
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the workflow run record."""
        result: dict[str, Any] = {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "workflow_name": self.workflow_name,
            "status": self.status.value,
            "engine": self.engine,
            "input_data": self.input_data,
            "checkpoint": self.checkpoint,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        if self.human_input_request is not None:
            result["human_input_request"] = self.human_input_request.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowRunRecord:
        """Deserialize a workflow run record."""
        hir_data = data.get("human_input_request")
        hir = HumanInputRequest.from_dict(hir_data) if hir_data else None

        return cls(
            run_id=str(data["run_id"]),
            session_id=str(data["session_id"]),
            workflow_name=str(data.get("workflow_name", "")),
            status=WorkflowStatus(data.get("status", "running")),
            engine=str(data.get("engine", "")),
            input_data=dict(data.get("input_data", {})),
            checkpoint=dict(data.get("checkpoint", {})),
            human_input_request=hir,
            created_at=_parse_timestamp(data.get("created_at")),
            updated_at=_parse_timestamp(data.get("updated_at")),
        )


def _parse_timestamp(raw: str | None) -> datetime:
    """Parse an ISO timestamp string, ensuring timezone awareness."""
    if not raw:
        return _utc_now()
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        from datetime import UTC

        dt = dt.replace(tzinfo=UTC)
    return dt
