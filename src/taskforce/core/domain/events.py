"""
Domain Events for Agent Execution

This module defines the core domain events that occur during agent execution.
Events represent immutable facts about what happened during the ReAct loop:
- Thought: Agent's reasoning and action decision
- Action: The specific action to be executed
- Observation: The result of executing an action

These events form the backbone of the ReAct (Reason + Act) execution pattern.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ActionType(str, Enum):
    """Type of action the agent can take.
    
    Minimal Schema (recommended):
    - TOOL_CALL: Execute a tool with parameters
    - RESPOND: Provide final answer to user (replaces finish_step/complete)
    - ASK_USER: Ask user a clarifying question
    
    Legacy types (for backward compatibility):
    - FINISH_STEP: Maps to RESPOND internally
    - COMPLETE: Maps to RESPOND internally
    - REPLAN: Internal replanning logic
    """

    # Minimal schema action types
    TOOL_CALL = "tool_call"
    RESPOND = "respond"      # NEW: Replaces finish_step/complete
    ASK_USER = "ask_user"
    
    # Legacy types (kept for backward compatibility)
    FINISH_STEP = "finish_step"  # -> maps to RESPOND
    COMPLETE = "complete"        # -> maps to RESPOND
    REPLAN = "replan"            # internal logic


@dataclass
class Action:
    """
    An action to be executed by the agent.

    Represents the agent's decision about what to do next in the ReAct loop.
    The action type determines which fields are relevant:
    
    Minimal schema types:
    - tool_call: Requires tool and tool_input
    - respond: Requires summary (final answer to user)
    - ask_user: Requires question and answer_key
    
    Legacy types (backward compatible):
    - complete: Maps to respond, requires summary
    - finish_step: Maps to respond, requires summary
    - replan: Requires replan_reason (internal)

    Attributes:
        type: Type of action (tool_call, respond, ask_user, complete, replan, finish_step)
        tool: Tool name to execute (for tool_call)
        tool_input: Parameters for tool execution (for tool_call)
        question: Question to ask user (for ask_user)
        answer_key: Stable identifier for user answer (for ask_user)
        summary: Final summary message (for respond/complete/finish_step)
        replan_reason: Reason for replanning (for replan)
    """

    type: ActionType
    tool: str | None = None
    tool_input: dict[str, Any] | None = None
    question: str | None = None
    answer_key: str | None = None
    summary: str | None = None
    replan_reason: str | None = None


@dataclass
class Thought:
    """
    Agent's reasoning about the current step.

    Represents the "Reason" part of the ReAct loop. The agent analyzes
    the current state, considers available tools and context, and decides
    what action to take next.

    Minimal schema: Only requires action field from LLM.
    Optional fields (step_ref, rationale, expected_outcome, confidence)
    are populated with defaults if not provided by LLM.

    Attributes:
        step_ref: Reference to TodoItem position being executed (default: 0)
        rationale: Brief explanation of reasoning (optional, default: "")
        action: The action decided upon (REQUIRED)
        expected_outcome: What the agent expects to happen (optional, default: "")
        confidence: Confidence level in this decision (optional, default: 1.0)
    """

    step_ref: int = 0
    rationale: str = ""
    action: Action = None  # type: ignore - set during parsing
    expected_outcome: str = ""
    confidence: float = 1.0


@dataclass
class Observation:
    """
    Result of executing an action.

    Represents the "Act" part of the ReAct loop. After executing an action,
    the agent observes the result and uses it to inform the next thought.

    Attributes:
        success: Whether the action succeeded
        data: Result data from action execution (tool output, user answer, etc.)
        error: Error message if action failed
        requires_user: Whether execution is paused waiting for user input
    """

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    requires_user: bool = False

