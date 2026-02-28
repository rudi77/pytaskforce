"""
Core Domain Enums

Defines all status values, event types, and action constants
to eliminate magic strings throughout the codebase.
"""

from enum import Enum


class ExecutionStatus(str, Enum):
    """Status of mission/agent execution."""

    COMPLETED = "completed"
    FAILED = "failed"
    PENDING = "pending"
    PAUSED = "paused"


class TaskStatus(str, Enum):
    """Status of individual tasks in a plan."""

    PENDING = "PENDING"
    DONE = "DONE"


class EventType(str, Enum):
    """Types of events emitted during streaming execution."""

    STARTED = "started"
    STEP_START = "step_start"
    LLM_TOKEN = "llm_token"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ASK_USER = "ask_user"
    PLAN_UPDATED = "plan_updated"
    TOKEN_USAGE = "token_usage"
    FINAL_ANSWER = "final_answer"
    COMPLETE = "complete"
    ERROR = "error"
    # Skill-related events
    SKILL_AUTO_ACTIVATED = "skill_auto_activated"
    # Communication gateway events
    NOTIFICATION = "notification"
    # Auto-epic orchestration events
    EPIC_ESCALATION = "epic_escalation"
    # Butler / event-driven events
    BUTLER_EVENT_RECEIVED = "butler_event_received"
    BUTLER_RULE_FIRED = "butler_rule_fired"
    BUTLER_SCHEDULE_TRIGGERED = "butler_schedule_triggered"
    BUTLER_LEARNING_EXTRACTED = "butler_learning_extracted"
    # Memory consolidation events
    CONSOLIDATION_STARTED = "consolidation_started"
    CONSOLIDATION_COMPLETED = "consolidation_completed"
    # Legacy event types (for original Agent)
    THOUGHT = "thought"
    OBSERVATION = "observation"


class LLMStreamEventType(str, Enum):
    """Types of events from LLM streaming responses."""

    TOKEN = "token"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_DELTA = "tool_call_delta"
    TOOL_CALL_END = "tool_call_end"
    DONE = "done"


class PlannerAction(str, Enum):
    """Actions available in the PlannerTool."""

    CREATE_PLAN = "create_plan"
    MARK_DONE = "mark_done"
    READ_PLAN = "read_plan"
    UPDATE_PLAN = "update_plan"


class LLMAction(str, Enum):
    """Actions the LLM can take during execution."""

    TOOL_CALL = "tool_call"
    RESPOND = "respond"
    ASK_USER = "ask_user"


class MessageRole(str, Enum):
    """Roles for messages in conversation history."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class SkillType(str, Enum):
    """Execution type for a skill.

    Determines how a skill is invoked and integrated:
    - CONTEXT: Instructions are injected into the system prompt when the skill
      is activated. Triggered by the activate_skill tool or intent routing.
    - PROMPT: One-shot prompt template with $ARGUMENTS substitution. Invokable
      directly from the chat interface via /skill-name [args].
    - AGENT: Temporarily overrides the agent configuration (profile, tools).
      Invokable directly from the chat interface via /skill-name [args].
    """

    CONTEXT = "context"
    PROMPT = "prompt"
    AGENT = "agent"


class ConsolidationStrategy(str, Enum):
    """Strategies for memory consolidation timing."""

    IMMEDIATE = "immediate"
    BATCH = "batch"
    SCHEDULED = "scheduled"
