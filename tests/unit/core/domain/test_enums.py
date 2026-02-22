"""Tests for core domain enums."""

import pytest

from taskforce.core.domain.enums import (
    EventType,
    ExecutionStatus,
    LLMAction,
    LLMStreamEventType,
    MessageRole,
    PlannerAction,
    SkillType,
    TaskStatus,
)


class TestExecutionStatus:
    """Tests for ExecutionStatus enum."""

    def test_values(self) -> None:
        assert ExecutionStatus.COMPLETED.value == "completed"
        assert ExecutionStatus.FAILED.value == "failed"
        assert ExecutionStatus.PENDING.value == "pending"
        assert ExecutionStatus.PAUSED.value == "paused"

    def test_is_str_enum(self) -> None:
        """ExecutionStatus members should be usable as strings."""
        assert isinstance(ExecutionStatus.COMPLETED, str)
        assert ExecutionStatus.COMPLETED == "completed"

    def test_member_count(self) -> None:
        assert len(ExecutionStatus) == 4

    def test_lookup_by_value(self) -> None:
        assert ExecutionStatus("completed") == ExecutionStatus.COMPLETED
        assert ExecutionStatus("failed") == ExecutionStatus.FAILED

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            ExecutionStatus("unknown")


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_values(self) -> None:
        assert TaskStatus.PENDING.value == "PENDING"
        assert TaskStatus.DONE.value == "DONE"

    def test_is_str_enum(self) -> None:
        assert isinstance(TaskStatus.PENDING, str)
        assert TaskStatus.PENDING == "PENDING"

    def test_member_count(self) -> None:
        assert len(TaskStatus) == 2


class TestEventType:
    """Tests for EventType enum."""

    def test_core_event_values(self) -> None:
        assert EventType.STARTED.value == "started"
        assert EventType.STEP_START.value == "step_start"
        assert EventType.LLM_TOKEN.value == "llm_token"
        assert EventType.TOOL_CALL.value == "tool_call"
        assert EventType.TOOL_RESULT.value == "tool_result"
        assert EventType.ASK_USER.value == "ask_user"
        assert EventType.PLAN_UPDATED.value == "plan_updated"
        assert EventType.TOKEN_USAGE.value == "token_usage"
        assert EventType.FINAL_ANSWER.value == "final_answer"
        assert EventType.COMPLETE.value == "complete"
        assert EventType.ERROR.value == "error"

    def test_skill_event_values(self) -> None:
        assert EventType.SKILL_AUTO_ACTIVATED.value == "skill_auto_activated"

    def test_communication_event_values(self) -> None:
        assert EventType.NOTIFICATION.value == "notification"

    def test_epic_event_values(self) -> None:
        assert EventType.EPIC_ESCALATION.value == "epic_escalation"

    def test_butler_event_values(self) -> None:
        assert EventType.BUTLER_EVENT_RECEIVED.value == "butler_event_received"
        assert EventType.BUTLER_RULE_FIRED.value == "butler_rule_fired"
        assert EventType.BUTLER_SCHEDULE_TRIGGERED.value == "butler_schedule_triggered"
        assert EventType.BUTLER_LEARNING_EXTRACTED.value == "butler_learning_extracted"

    def test_legacy_event_values(self) -> None:
        assert EventType.THOUGHT.value == "thought"
        assert EventType.OBSERVATION.value == "observation"

    def test_is_str_enum(self) -> None:
        assert isinstance(EventType.STARTED, str)
        assert EventType.STARTED == "started"

    def test_lookup_by_value(self) -> None:
        assert EventType("tool_call") == EventType.TOOL_CALL
        assert EventType("error") == EventType.ERROR


class TestLLMStreamEventType:
    """Tests for LLMStreamEventType enum."""

    def test_values(self) -> None:
        assert LLMStreamEventType.TOKEN.value == "token"
        assert LLMStreamEventType.TOOL_CALL_START.value == "tool_call_start"
        assert LLMStreamEventType.TOOL_CALL_DELTA.value == "tool_call_delta"
        assert LLMStreamEventType.TOOL_CALL_END.value == "tool_call_end"
        assert LLMStreamEventType.DONE.value == "done"

    def test_member_count(self) -> None:
        assert len(LLMStreamEventType) == 5

    def test_is_str_enum(self) -> None:
        assert isinstance(LLMStreamEventType.TOKEN, str)


class TestPlannerAction:
    """Tests for PlannerAction enum."""

    def test_values(self) -> None:
        assert PlannerAction.CREATE_PLAN.value == "create_plan"
        assert PlannerAction.MARK_DONE.value == "mark_done"
        assert PlannerAction.READ_PLAN.value == "read_plan"
        assert PlannerAction.UPDATE_PLAN.value == "update_plan"

    def test_member_count(self) -> None:
        assert len(PlannerAction) == 4


class TestLLMAction:
    """Tests for LLMAction enum."""

    def test_values(self) -> None:
        assert LLMAction.TOOL_CALL.value == "tool_call"
        assert LLMAction.RESPOND.value == "respond"
        assert LLMAction.ASK_USER.value == "ask_user"

    def test_member_count(self) -> None:
        assert len(LLMAction) == 3


class TestMessageRole:
    """Tests for MessageRole enum."""

    def test_values(self) -> None:
        assert MessageRole.USER.value == "user"
        assert MessageRole.ASSISTANT.value == "assistant"
        assert MessageRole.SYSTEM.value == "system"
        assert MessageRole.TOOL.value == "tool"

    def test_member_count(self) -> None:
        assert len(MessageRole) == 4

    def test_is_str_enum(self) -> None:
        assert isinstance(MessageRole.USER, str)
        assert MessageRole.USER == "user"


class TestSkillType:
    """Tests for SkillType enum."""

    def test_values(self) -> None:
        assert SkillType.CONTEXT.value == "context"
        assert SkillType.PROMPT.value == "prompt"
        assert SkillType.AGENT.value == "agent"

    def test_member_count(self) -> None:
        assert len(SkillType) == 3

    def test_is_str_enum(self) -> None:
        assert isinstance(SkillType.CONTEXT, str)
        assert SkillType.CONTEXT == "context"

    def test_lookup_by_value(self) -> None:
        assert SkillType("prompt") == SkillType.PROMPT
        assert SkillType("agent") == SkillType.AGENT
