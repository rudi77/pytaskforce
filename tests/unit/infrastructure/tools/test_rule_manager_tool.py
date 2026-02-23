"""Tests for RuleManagerTool.

Covers tool metadata properties, parameter validation, all execute actions
(add, list, remove, get), error handling for missing rule engine,
unknown actions, and rule engine failures.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from taskforce.core.domain.trigger_rule import (
    RuleAction,
    RuleActionType,
    TriggerCondition,
    TriggerRule,
)
from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.tools.native.rule_manager_tool import RuleManagerTool

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_engine() -> AsyncMock:
    """Create a mock rule engine with all required async methods."""
    engine = AsyncMock()
    engine.add_rule = AsyncMock(return_value="rule-abc-123")
    engine.list_rules = AsyncMock(return_value=[])
    engine.remove_rule = AsyncMock(return_value=True)
    engine.get_rule = AsyncMock(return_value=None)
    return engine


@pytest.fixture
def tool(mock_engine: AsyncMock) -> RuleManagerTool:
    return RuleManagerTool(rule_engine=mock_engine)


# ---------------------------------------------------------------------------
# Metadata / Properties
# ---------------------------------------------------------------------------


class TestRuleManagerToolProperties:
    """Tests for RuleManagerTool metadata and static properties."""

    def test_name(self, tool: RuleManagerTool) -> None:
        assert tool.name == "rule_manager"

    def test_description_mentions_rules(self, tool: RuleManagerTool) -> None:
        assert "rule" in tool.description.lower()

    def test_description_mentions_events(self, tool: RuleManagerTool) -> None:
        assert "event" in tool.description.lower()

    def test_description_mentions_actions(self, tool: RuleManagerTool) -> None:
        desc = tool.description.lower()
        assert "add" in desc
        assert "list" in desc
        assert "remove" in desc

    def test_parameters_schema_is_object(self, tool: RuleManagerTool) -> None:
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "action" in schema["properties"]
        assert "action" in schema["required"]

    def test_parameters_schema_action_enum(self, tool: RuleManagerTool) -> None:
        action_prop = tool.parameters_schema["properties"]["action"]
        assert set(action_prop["enum"]) == {"add", "list", "remove", "get"}

    def test_parameters_schema_action_type_enum(self, tool: RuleManagerTool) -> None:
        at_prop = tool.parameters_schema["properties"]["action_type"]
        assert set(at_prop["enum"]) == {"notify", "execute_mission", "log_memory"}

    def test_parameters_schema_has_expected_keys(self, tool: RuleManagerTool) -> None:
        props = tool.parameters_schema["properties"]
        expected = {
            "action", "rule_id", "name", "description", "trigger_source",
            "trigger_event_type", "trigger_filters", "action_type",
            "action_params", "action_template", "priority",
        }
        assert expected == set(props.keys())

    def test_requires_approval(self, tool: RuleManagerTool) -> None:
        assert tool.requires_approval is True

    def test_approval_risk_level(self, tool: RuleManagerTool) -> None:
        assert tool.approval_risk_level == ApprovalRiskLevel.MEDIUM

    def test_supports_parallelism(self, tool: RuleManagerTool) -> None:
        assert tool.supports_parallelism is False

    def test_get_approval_preview(self, tool: RuleManagerTool) -> None:
        preview = tool.get_approval_preview(action="add", name="calendar_reminder")
        assert "rule_manager" in preview
        assert "add" in preview
        assert "calendar_reminder" in preview

    def test_get_approval_preview_without_name(self, tool: RuleManagerTool) -> None:
        preview = tool.get_approval_preview(action="list")
        assert "list" in preview

    def test_default_rule_engine_is_none(self) -> None:
        tool = RuleManagerTool()
        assert tool._rule_engine is None


# ---------------------------------------------------------------------------
# Validate Params
# ---------------------------------------------------------------------------


class TestRuleManagerToolValidateParams:
    """Tests for RuleManagerTool.validate_params."""

    def test_valid_add(self, tool: RuleManagerTool) -> None:
        valid, error = tool.validate_params(
            action="add", name="test_rule", action_type="notify"
        )
        assert valid is True
        assert error is None

    def test_add_missing_name(self, tool: RuleManagerTool) -> None:
        valid, error = tool.validate_params(action="add", action_type="notify")
        assert valid is False
        assert "name" in error

    def test_add_missing_action_type(self, tool: RuleManagerTool) -> None:
        valid, error = tool.validate_params(action="add", name="test_rule")
        assert valid is False
        assert "action_type" in error

    def test_valid_list(self, tool: RuleManagerTool) -> None:
        valid, error = tool.validate_params(action="list")
        assert valid is True
        assert error is None

    def test_valid_remove_with_rule_id(self, tool: RuleManagerTool) -> None:
        valid, error = tool.validate_params(action="remove", rule_id="r1")
        assert valid is True
        assert error is None

    def test_remove_missing_rule_id(self, tool: RuleManagerTool) -> None:
        valid, error = tool.validate_params(action="remove")
        assert valid is False
        assert "rule_id" in error

    def test_valid_get_with_rule_id(self, tool: RuleManagerTool) -> None:
        valid, error = tool.validate_params(action="get", rule_id="r1")
        assert valid is True
        assert error is None

    def test_get_missing_rule_id(self, tool: RuleManagerTool) -> None:
        valid, error = tool.validate_params(action="get")
        assert valid is False
        assert "rule_id" in error

    def test_missing_action(self, tool: RuleManagerTool) -> None:
        valid, error = tool.validate_params()
        assert valid is False
        assert "action" in error


# ---------------------------------------------------------------------------
# Execute - No Rule Engine
# ---------------------------------------------------------------------------


class TestRuleManagerToolNoEngine:
    """Tests for RuleManagerTool when no rule engine is configured."""

    async def test_returns_error_without_engine(self) -> None:
        tool = RuleManagerTool(rule_engine=None)
        result = await tool.execute(action="list")
        assert result["success"] is False
        assert "not configured" in result["error"]

    async def test_add_without_engine(self) -> None:
        tool = RuleManagerTool(rule_engine=None)
        result = await tool.execute(
            action="add", name="test", action_type="notify"
        )
        assert result["success"] is False
        assert "not configured" in result["error"]


# ---------------------------------------------------------------------------
# Execute - Add Rule
# ---------------------------------------------------------------------------


class TestRuleManagerToolAddRule:
    """Tests for adding trigger rules."""

    async def test_add_rule_full_params(
        self, tool: RuleManagerTool, mock_engine: AsyncMock
    ) -> None:
        result = await tool.execute(
            action="add",
            name="calendar_reminder_30min",
            description="Remind 30 minutes before calendar events",
            trigger_source="calendar",
            trigger_event_type="calendar.upcoming",
            trigger_filters={"minutes_until": {"$lte": 30}},
            action_type="notify",
            action_params={"channel": "telegram"},
            action_template="Reminder: {{event.title}} in {{minutes_until}} minutes",
            priority=10,
        )

        assert result["success"] is True
        assert result["rule_id"] == "rule-abc-123"
        assert result["name"] == "calendar_reminder_30min"
        assert "calendar_reminder_30min" in result["message"]

        mock_engine.add_rule.assert_awaited_once()
        rule_arg = mock_engine.add_rule.call_args[0][0]
        assert isinstance(rule_arg, TriggerRule)
        assert rule_arg.name == "calendar_reminder_30min"
        assert rule_arg.description == "Remind 30 minutes before calendar events"
        assert rule_arg.trigger.source == "calendar"
        assert rule_arg.trigger.event_type == "calendar.upcoming"
        assert rule_arg.trigger.filters == {"minutes_until": {"$lte": 30}}
        assert rule_arg.action.action_type == RuleActionType.NOTIFY
        assert rule_arg.action.params == {"channel": "telegram"}
        assert "{{event.title}}" in rule_arg.action.template
        assert rule_arg.priority == 10

    async def test_add_rule_minimal_params(
        self, tool: RuleManagerTool, mock_engine: AsyncMock
    ) -> None:
        """Adding a rule with minimal parameters should use defaults."""
        result = await tool.execute(
            action="add",
            name="simple_rule",
            action_type="notify",
        )

        assert result["success"] is True
        rule_arg = mock_engine.add_rule.call_args[0][0]
        assert rule_arg.name == "simple_rule"
        assert rule_arg.trigger.source == "*"
        assert rule_arg.trigger.event_type == "*"
        assert rule_arg.trigger.filters == {}
        assert rule_arg.action.action_type == RuleActionType.NOTIFY
        assert rule_arg.action.template is None
        assert rule_arg.priority == 0

    async def test_add_rule_execute_mission(
        self, tool: RuleManagerTool, mock_engine: AsyncMock
    ) -> None:
        result = await tool.execute(
            action="add",
            name="email_handler",
            trigger_source="email",
            trigger_event_type="email.received",
            action_type="execute_mission",
            action_params={"mission": "Summarize the email and reply"},
        )

        assert result["success"] is True
        rule_arg = mock_engine.add_rule.call_args[0][0]
        assert rule_arg.action.action_type == RuleActionType.EXECUTE_MISSION
        assert rule_arg.action.params["mission"] == "Summarize the email and reply"

    async def test_add_rule_log_memory(
        self, tool: RuleManagerTool, mock_engine: AsyncMock
    ) -> None:
        result = await tool.execute(
            action="add",
            name="conversation_logger",
            trigger_source="*",
            action_type="log_memory",
            action_params={"memory_kind": "LEARNED_FACT"},
        )

        assert result["success"] is True
        rule_arg = mock_engine.add_rule.call_args[0][0]
        assert rule_arg.action.action_type == RuleActionType.LOG_MEMORY

    async def test_add_rule_without_name_uses_default(
        self, tool: RuleManagerTool, mock_engine: AsyncMock
    ) -> None:
        """The tool code defaults name to 'unnamed' if not provided."""
        result = await tool.execute(
            action="add",
            action_type="notify",
        )

        assert result["success"] is True
        rule_arg = mock_engine.add_rule.call_args[0][0]
        assert rule_arg.name == "unnamed"


# ---------------------------------------------------------------------------
# Execute - List Rules
# ---------------------------------------------------------------------------


class TestRuleManagerToolListRules:
    """Tests for listing trigger rules."""

    async def test_list_empty(self, tool: RuleManagerTool, mock_engine: AsyncMock) -> None:
        mock_engine.list_rules.return_value = []
        result = await tool.execute(action="list")

        assert result["success"] is True
        assert result["count"] == 0
        assert result["rules"] == []

    async def test_list_with_rules(self, tool: RuleManagerTool, mock_engine: AsyncMock) -> None:
        rules = [
            TriggerRule(
                rule_id="r1",
                name="calendar_reminder",
                trigger=TriggerCondition(source="calendar"),
                action=RuleAction(action_type=RuleActionType.NOTIFY),
            ),
            TriggerRule(
                rule_id="r2",
                name="email_handler",
                trigger=TriggerCondition(source="email"),
                action=RuleAction(action_type=RuleActionType.EXECUTE_MISSION),
            ),
        ]
        mock_engine.list_rules.return_value = rules

        result = await tool.execute(action="list")

        assert result["success"] is True
        assert result["count"] == 2
        assert len(result["rules"]) == 2
        assert result["rules"][0]["name"] == "calendar_reminder"
        assert result["rules"][1]["name"] == "email_handler"

    async def test_list_serializes_rule_to_dict(
        self, tool: RuleManagerTool, mock_engine: AsyncMock
    ) -> None:
        """Verify that each rule is serialized via to_dict()."""
        rule = TriggerRule(
            rule_id="r1",
            name="test",
            trigger=TriggerCondition(source="calendar", event_type="calendar.upcoming"),
            action=RuleAction(
                action_type=RuleActionType.NOTIFY,
                params={"channel": "telegram"},
                template="Hello {{name}}",
            ),
            priority=5,
        )
        mock_engine.list_rules.return_value = [rule]

        result = await tool.execute(action="list")

        rule_dict = result["rules"][0]
        assert rule_dict["rule_id"] == "r1"
        assert rule_dict["trigger"]["source"] == "calendar"
        assert rule_dict["trigger"]["event_type"] == "calendar.upcoming"
        assert rule_dict["action"]["action_type"] == "notify"
        assert rule_dict["action"]["params"]["channel"] == "telegram"
        assert rule_dict["action"]["template"] == "Hello {{name}}"
        assert rule_dict["priority"] == 5


# ---------------------------------------------------------------------------
# Execute - Remove Rule
# ---------------------------------------------------------------------------


class TestRuleManagerToolRemoveRule:
    """Tests for removing trigger rules."""

    async def test_remove_existing_rule(
        self, tool: RuleManagerTool, mock_engine: AsyncMock
    ) -> None:
        mock_engine.remove_rule.return_value = True
        result = await tool.execute(action="remove", rule_id="r1")

        assert result["success"] is True
        assert "r1" in result["message"]
        mock_engine.remove_rule.assert_awaited_once_with("r1")

    async def test_remove_nonexistent_rule(
        self, tool: RuleManagerTool, mock_engine: AsyncMock
    ) -> None:
        mock_engine.remove_rule.return_value = False
        result = await tool.execute(action="remove", rule_id="unknown")

        assert result["success"] is False
        assert "not found" in result["error"]


# ---------------------------------------------------------------------------
# Execute - Get Rule
# ---------------------------------------------------------------------------


class TestRuleManagerToolGetRule:
    """Tests for getting details of a specific rule."""

    async def test_get_existing_rule(
        self, tool: RuleManagerTool, mock_engine: AsyncMock
    ) -> None:
        rule = TriggerRule(
            rule_id="r1",
            name="calendar_reminder",
            trigger=TriggerCondition(source="calendar", event_type="calendar.upcoming"),
            action=RuleAction(action_type=RuleActionType.NOTIFY),
        )
        mock_engine.get_rule.return_value = rule

        result = await tool.execute(action="get", rule_id="r1")

        assert result["success"] is True
        assert result["rule"]["rule_id"] == "r1"
        assert result["rule"]["name"] == "calendar_reminder"
        assert result["rule"]["trigger"]["source"] == "calendar"
        mock_engine.get_rule.assert_awaited_once_with("r1")

    async def test_get_nonexistent_rule(
        self, tool: RuleManagerTool, mock_engine: AsyncMock
    ) -> None:
        mock_engine.get_rule.return_value = None

        result = await tool.execute(action="get", rule_id="nope")

        assert result["success"] is False
        assert "not found" in result["error"]


# ---------------------------------------------------------------------------
# Execute - Error Handling
# ---------------------------------------------------------------------------


class TestRuleManagerToolErrorHandling:
    """Tests for error handling in RuleManagerTool.execute."""

    async def test_unknown_action(self, tool: RuleManagerTool) -> None:
        result = await tool.execute(action="enable")

        assert result["success"] is False
        assert "unknown" in result["error"].lower() or "Unknown" in result["error"]

    async def test_engine_add_raises(
        self, tool: RuleManagerTool, mock_engine: AsyncMock
    ) -> None:
        mock_engine.add_rule.side_effect = RuntimeError("Engine crashed")

        result = await tool.execute(
            action="add",
            name="test",
            action_type="notify",
        )

        assert result["success"] is False
        assert "Engine crashed" in str(result.get("error", ""))

    async def test_engine_list_raises(
        self, tool: RuleManagerTool, mock_engine: AsyncMock
    ) -> None:
        mock_engine.list_rules.side_effect = RuntimeError("DB connection failed")

        result = await tool.execute(action="list")

        assert result["success"] is False

    async def test_engine_remove_raises(
        self, tool: RuleManagerTool, mock_engine: AsyncMock
    ) -> None:
        mock_engine.remove_rule.side_effect = RuntimeError("DB error")

        result = await tool.execute(action="remove", rule_id="r1")

        assert result["success"] is False

    async def test_engine_get_raises(
        self, tool: RuleManagerTool, mock_engine: AsyncMock
    ) -> None:
        mock_engine.get_rule.side_effect = RuntimeError("Timeout")

        result = await tool.execute(action="get", rule_id="r1")

        assert result["success"] is False
