"""
Core Domain Models

This module defines the core data models used throughout the agent domain.
These models represent the fundamental business entities and execution results.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass
class StreamEvent:
    """
    Event emitted during streaming agent execution.

    StreamEvents enable real-time progress tracking during LeanAgent.execute_stream().
    Each event represents a significant moment in the execution loop.

    Event types:
    - step_start: New loop iteration begins (step N of MAX_STEPS)
    - llm_token: Token chunk from LLM response (real-time content)
    - tool_call: Tool invocation starting (before execution)
    - tool_result: Tool execution completed (after execution)
    - plan_updated: PlannerTool modified the plan
    - final_answer: Agent completed with final response
    - error: Error occurred during execution

    Attributes:
        event_type: The type of event (see above)
        data: Event-specific payload (varies by type)
        timestamp: When the event occurred (auto-generated)
    """

    event_type: Literal[
        "step_start",
        "llm_token",
        "tool_call",
        "tool_result",
        "plan_updated",
        "final_answer",
        "error",
    ]
    data: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary with event_type, data, and ISO-formatted timestamp.
        """
        return {
            "event_type": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }


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
    """

    session_id: str
    status: str
    final_message: str
    execution_history: list[dict[str, Any]] = field(default_factory=list)
    todolist_id: str | None = None
    pending_question: dict[str, Any] | None = None

