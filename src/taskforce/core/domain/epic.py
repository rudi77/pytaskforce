"""Domain models for epic-scale orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class EpicTask:
    """Task definition produced by planner agents."""

    task_id: str
    title: str
    description: str
    acceptance_criteria: list[str] = field(default_factory=list)
    source: str = "planner"

    def to_dict(self) -> dict[str, Any]:
        """Serialize task to dict."""
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "acceptance_criteria": list(self.acceptance_criteria),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EpicTask":
        """Create task from payload."""
        return cls(
            task_id=str(payload.get("task_id", "")),
            title=str(payload.get("title", "")),
            description=str(payload.get("description", "")),
            acceptance_criteria=[
                str(item) for item in payload.get("acceptance_criteria", [])
            ],
            source=str(payload.get("source", "planner")),
        )


@dataclass(frozen=True)
class EpicTaskResult:
    """Result returned by a worker agent for a task."""

    task_id: str
    worker_session_id: str
    status: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize result to dict."""
        return {
            "task_id": self.task_id,
            "worker_session_id": self.worker_session_id,
            "status": self.status,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class EpicRunResult:
    """Summary of an epic orchestration run."""

    run_id: str
    started_at: datetime = field(default_factory=_utc_now)
    completed_at: datetime | None = None
    status: str = "running"
    tasks: list[EpicTask] = field(default_factory=list)
    worker_results: list[EpicTaskResult] = field(default_factory=list)
    judge_summary: str | None = None
    round_summaries: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize run result to dict."""
        return {
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status,
            "tasks": [task.to_dict() for task in self.tasks],
            "worker_results": [result.to_dict() for result in self.worker_results],
            "judge_summary": self.judge_summary,
            "round_summaries": list(self.round_summaries),
        }
