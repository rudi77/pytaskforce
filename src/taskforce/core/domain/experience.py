"""Experience domain models for memory consolidation.

Captures agent execution experiences and consolidation results
to support long-term memory formation across sessions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class ConsolidatedMemoryKind(str, Enum):
    """Kinds of consolidated memories.

    Stored in ``MemoryRecord.metadata["consolidation_kind"]``
    rather than in ``MemoryKind`` to avoid polluting the core enum.
    """

    PROCEDURAL = "procedural"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    META_COGNITIVE = "meta_cognitive"


@dataclass
class ExperienceEvent:
    """A single captured event during agent execution.

    Attributes:
        timestamp: When the event occurred.
        event_type: Event type string (from ``EventType`` values).
        data: Event-specific payload (lightweight summary).
        step: Execution step number when the event occurred.
    """

    timestamp: datetime
    event_type: str
    data: dict[str, Any]
    step: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "data": self.data,
            "step": self.step,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExperienceEvent:
        """Deserialize from dictionary."""
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            event_type=data["event_type"],
            data=data.get("data", {}),
            step=data.get("step", 0),
        )


@dataclass
class ToolCallExperience:
    """Structured record of a single tool invocation.

    Attributes:
        tool_name: Name of the tool that was called.
        arguments: Tool call arguments (sanitized).
        success: Whether the tool call succeeded.
        output_summary: Truncated output (max 500 chars).
        duration_ms: Execution duration in milliseconds.
        error: Error message if the call failed.
    """

    tool_name: str
    arguments: dict[str, Any]
    success: bool = True
    output_summary: str = ""
    duration_ms: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        result: dict[str, Any] = {
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "success": self.success,
            "output_summary": self.output_summary,
            "duration_ms": self.duration_ms,
        }
        if self.error:
            result["error"] = self.error
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolCallExperience:
        """Deserialize from dictionary."""
        return cls(
            tool_name=data["tool_name"],
            arguments=data.get("arguments", {}),
            success=data.get("success", True),
            output_summary=data.get("output_summary", ""),
            duration_ms=data.get("duration_ms", 0),
            error=data.get("error"),
        )


_MAX_OUTPUT_SUMMARY = 500


def truncate_output(text: str) -> str:
    """Truncate tool output to a safe summary length.

    Args:
        text: Raw output string.

    Returns:
        Truncated string (max 500 characters).
    """
    if len(text) <= _MAX_OUTPUT_SUMMARY:
        return text
    return text[:_MAX_OUTPUT_SUMMARY] + "..."


@dataclass
class SessionExperience:
    """Complete experience record for one agent session.

    Attributes:
        session_id: Unique session identifier.
        profile: Profile name used for the session.
        mission: The mission/task that was executed.
        started_at: Session start time.
        ended_at: Session end time (set on completion).
        events: Lightweight event summaries captured during execution.
        tool_calls: Structured tool invocation records.
        plan_updates: Plan modification events.
        user_interactions: User question/answer interactions.
        total_tokens: Approximate total token count.
        total_steps: Number of execution steps completed.
        final_answer: The agent's final response (if any).
        errors: Errors encountered during execution.
        metadata: Additional session metadata.
        processed_by: IDs of consolidation runs that processed this experience.
    """

    session_id: str
    profile: str
    mission: str
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    events: list[ExperienceEvent] = field(default_factory=list)
    tool_calls: list[ToolCallExperience] = field(default_factory=list)
    plan_updates: list[dict[str, Any]] = field(default_factory=list)
    user_interactions: list[dict[str, Any]] = field(default_factory=list)
    total_tokens: int = 0
    total_steps: int = 0
    final_answer: str = ""
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    processed_by: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON persistence."""
        return {
            "session_id": self.session_id,
            "profile": self.profile,
            "mission": self.mission,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "events": [e.to_dict() for e in self.events],
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "plan_updates": self.plan_updates,
            "user_interactions": self.user_interactions,
            "total_tokens": self.total_tokens,
            "total_steps": self.total_steps,
            "final_answer": self.final_answer,
            "errors": self.errors,
            "metadata": self.metadata,
            "processed_by": self.processed_by,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionExperience:
        """Deserialize from dictionary."""
        ended_at = data.get("ended_at")
        return cls(
            session_id=data["session_id"],
            profile=data.get("profile", ""),
            mission=data.get("mission", ""),
            started_at=datetime.fromisoformat(data["started_at"]),
            ended_at=datetime.fromisoformat(ended_at) if ended_at else None,
            events=[ExperienceEvent.from_dict(e) for e in data.get("events", [])],
            tool_calls=[ToolCallExperience.from_dict(tc) for tc in data.get("tool_calls", [])],
            plan_updates=data.get("plan_updates", []),
            user_interactions=data.get("user_interactions", []),
            total_tokens=data.get("total_tokens", 0),
            total_steps=data.get("total_steps", 0),
            final_answer=data.get("final_answer", ""),
            errors=data.get("errors", []),
            metadata=data.get("metadata", {}),
            processed_by=data.get("processed_by", []),
        )


@dataclass
class ConsolidationResult:
    """Result of a memory consolidation run.

    Attributes:
        consolidation_id: Unique identifier for this consolidation run.
        strategy: Consolidation strategy used (immediate, batch, scheduled).
        sessions_processed: Number of sessions that were consolidated.
        memories_created: Number of new memory records created.
        memories_updated: Number of existing memories updated.
        memories_retired: Number of outdated memories retired.
        contradictions_resolved: Number of contradictions found and resolved.
        started_at: When consolidation started.
        ended_at: When consolidation completed.
        total_tokens: Total LLM tokens used during consolidation.
        quality_score: Consolidation quality assessment (0.0 - 1.0).
        session_ids: IDs of sessions that were processed.
    """

    consolidation_id: str = field(default_factory=lambda: uuid4().hex)
    strategy: str = "immediate"
    sessions_processed: int = 0
    memories_created: int = 0
    memories_updated: int = 0
    memories_retired: int = 0
    contradictions_resolved: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    total_tokens: int = 0
    quality_score: float = 0.0
    session_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "consolidation_id": self.consolidation_id,
            "strategy": self.strategy,
            "sessions_processed": self.sessions_processed,
            "memories_created": self.memories_created,
            "memories_updated": self.memories_updated,
            "memories_retired": self.memories_retired,
            "contradictions_resolved": self.contradictions_resolved,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "total_tokens": self.total_tokens,
            "quality_score": self.quality_score,
            "session_ids": self.session_ids,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConsolidationResult:
        """Deserialize from dictionary."""
        ended_at = data.get("ended_at")
        return cls(
            consolidation_id=data.get("consolidation_id", uuid4().hex),
            strategy=data.get("strategy", "immediate"),
            sessions_processed=data.get("sessions_processed", 0),
            memories_created=data.get("memories_created", 0),
            memories_updated=data.get("memories_updated", 0),
            memories_retired=data.get("memories_retired", 0),
            contradictions_resolved=data.get("contradictions_resolved", 0),
            started_at=datetime.fromisoformat(data["started_at"]),
            ended_at=datetime.fromisoformat(ended_at) if ended_at else None,
            total_tokens=data.get("total_tokens", 0),
            quality_score=data.get("quality_score", 0.0),
            session_ids=data.get("session_ids", []),
        )
