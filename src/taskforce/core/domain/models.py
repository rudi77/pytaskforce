"""
Core Domain Models

This module defines the core data models used throughout the agent domain.
These models represent the fundamental business entities and execution results.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from taskforce.core.domain.enums import EventType, ExecutionStatus


@dataclass(frozen=True)
class UserContext:
    """RAG security filtering context.

    Passed through executor → factory → agent to enable
    document-level security filtering in RAG operations.

    Attributes:
        user_id: User identifier for access control.
        org_id: Organization identifier for tenancy filtering.
        scope: Access scope (e.g., "read", "admin").
    """

    user_id: str | None = None
    org_id: str | None = None
    scope: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for backward compatibility."""
        return {
            "user_id": self.user_id,
            "org_id": self.org_id,
            "scope": self.scope,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "UserContext | None":
        """Create from dictionary, returning None if data is None/empty."""
        if not data:
            return None
        return cls(
            user_id=data.get("user_id"),
            org_id=data.get("org_id"),
            scope=data.get("scope"),
        )


@dataclass
class StreamEvent:
    """
    Event emitted during streaming agent execution.

    StreamEvents enable real-time progress tracking during Agent.execute_stream().
    Each event represents a significant moment in the execution loop.

    Event types:
    - step_start: New loop iteration begins (step N of MAX_STEPS)
    - llm_token: Token chunk from LLM response (real-time content)
    - tool_call: Tool invocation starting (before execution)
    - tool_result: Tool execution completed (after execution)
    - ask_user: Agent requires human input to proceed (execution pauses)
    - plan_updated: PlannerTool modified the plan
    - token_usage: LLM token consumption metrics (prompt_tokens, completion_tokens, total_tokens)
    - final_answer: Agent completed with final response
    - error: Error occurred during execution

    Attributes:
        event_type: The type of event (see EventType enum)
        data: Event-specific payload (varies by type)
        timestamp: When the event occurred (auto-generated)
    """

    event_type: EventType | str  # Allow string for backward compatibility
    data: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary with event_type, data, and ISO-formatted timestamp.
        """
        event_type_value = (
            self.event_type.value
            if isinstance(self.event_type, EventType)
            else self.event_type
        )
        return {
            "event_type": event_type_value,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class TokenUsage:
    """Token usage statistics for LLM calls."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def exceeds_budget(self, limit: int) -> bool:
        """Check whether total token usage exceeds a budget limit.

        Args:
            limit: Maximum allowed total tokens.

        Returns:
            True if ``total_tokens`` exceeds *limit*.
        """
        return self.total_tokens > limit

    def remaining(self, budget: int) -> int:
        """Return the number of tokens remaining within a budget.

        Args:
            budget: Total token budget.

        Returns:
            Non-negative remaining tokens (clamped to 0).
        """
        return max(0, budget - self.total_tokens)

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        """Combine two TokenUsage instances (e.g. across multiple LLM calls)."""
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )

    def to_dict(self) -> dict[str, int]:
        """Convert to dictionary."""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> "TokenUsage":
        """Create from dictionary."""
        return cls(
            prompt_tokens=data.get("prompt_tokens", 0),
            completion_tokens=data.get("completion_tokens", 0),
            total_tokens=data.get("total_tokens", 0),
        )


@dataclass
class PendingQuestion:
    """Question awaiting user response."""

    question: str
    context: str = ""
    tool_call_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "question": self.question,
            "context": self.context,
            "tool_call_id": self.tool_call_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PendingQuestion":
        """Create from dictionary."""
        return cls(
            question=data.get("question", ""),
            context=data.get("context", ""),
            tool_call_id=data.get("tool_call_id", ""),
        )


@dataclass
class ExecutionResult:
    """
    Result of agent execution for a mission.

    Represents the final outcome after the ReAct loop completes or pauses.
    Contains the session identifier, execution status, final message, and
    a history of all thoughts, actions, and observations.

    Attributes:
        session_id: Unique identifier for this execution session
        status: Execution status (completed, failed, pending, paused)
        final_message: Human-readable summary of execution outcome
        execution_history: List of execution events (thoughts, actions, observations)
        todolist_id: ID of the TodoList that was executed (if any)
        pending_question: Question awaiting user response (if status is paused)
        token_usage: Total token usage statistics
    """

    session_id: str
    status: ExecutionStatus | str  # Allow string for backward compatibility
    final_message: str
    execution_history: list[dict[str, Any]] = field(default_factory=list)
    todolist_id: str | None = None
    pending_question: PendingQuestion | dict[str, Any] | None = None
    token_usage: TokenUsage | dict[str, int] = field(
        default_factory=lambda: TokenUsage()
    )

    @property
    def status_value(self) -> str:
        """Get status as string value."""
        if isinstance(self.status, ExecutionStatus):
            return self.status.value
        return self.status

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        pending_q = None
        if self.pending_question:
            if isinstance(self.pending_question, PendingQuestion):
                pending_q = self.pending_question.to_dict()
            else:
                pending_q = self.pending_question

        token_usage_dict = (
            self.token_usage.to_dict()
            if isinstance(self.token_usage, TokenUsage)
            else self.token_usage
        )

        return {
            "session_id": self.session_id,
            "status": self.status_value,
            "final_message": self.final_message,
            "execution_history": self.execution_history,
            "todolist_id": self.todolist_id,
            "pending_question": pending_q,
            "token_usage": token_usage_dict,
        }

