"""Unit tests for the TriggerRule domain models."""

from __future__ import annotations

from taskforce.core.domain.trigger_rule import (
    RuleAction,
    RuleActionType,
    TriggerCondition,
    TriggerRule,
)


class TestTriggerCondition:
    def test_defaults_match_everything(self) -> None:
        condition = TriggerCondition()
        assert condition.source == "*"
        assert condition.event_type == "*"
        assert condition.filters == {}

    def test_to_dict_from_dict_roundtrip(self) -> None:
        original = TriggerCondition(
            source="calendar",
            event_type="calendar.upcoming",
            filters={"minutes_until": {"$lte": 30}},
        )
        restored = TriggerCondition.from_dict(original.to_dict())
        assert restored == original

    def test_from_dict_tolerates_missing_fields(self) -> None:
        restored = TriggerCondition.from_dict({})
        assert restored.source == "*"
        assert restored.event_type == "*"
        assert restored.filters == {}


class TestRuleAction:
    def test_template_is_optional(self) -> None:
        action = RuleAction(action_type=RuleActionType.NOTIFY)
        serialized = action.to_dict()
        assert "template" not in serialized

    def test_template_is_preserved_when_set(self) -> None:
        action = RuleAction(
            action_type=RuleActionType.NOTIFY,
            params={"channel": "telegram"},
            template="Hello {{event.source}}",
        )
        restored = RuleAction.from_dict(action.to_dict())
        assert restored == action

    def test_all_action_types_roundtrip(self) -> None:
        for action_type in RuleActionType:
            action = RuleAction(action_type=action_type, params={"key": "value"})
            restored = RuleAction.from_dict(action.to_dict())
            assert restored.action_type == action_type
            assert restored.params == {"key": "value"}


class TestTriggerRule:
    def test_auto_generates_rule_id(self) -> None:
        rule1 = TriggerRule(name="a")
        rule2 = TriggerRule(name="b")
        assert rule1.rule_id != rule2.rule_id
        assert len(rule1.rule_id) > 0

    def test_full_roundtrip(self) -> None:
        original = TriggerRule(
            name="upcoming_meeting",
            description="Notify 30m before meetings",
            trigger=TriggerCondition(
                source="calendar",
                event_type="calendar.upcoming",
                filters={"minutes_until": {"$lte": 30}},
            ),
            action=RuleAction(
                action_type=RuleActionType.NOTIFY,
                params={"channel": "telegram"},
                template="Meeting in {{event.minutes_until}}m",
            ),
            priority=10,
        )
        restored = TriggerRule.from_dict(original.to_dict())
        assert restored.rule_id == original.rule_id
        assert restored.name == original.name
        assert restored.trigger == original.trigger
        assert restored.action == original.action
        assert restored.priority == original.priority
        assert restored.enabled is True

    def test_disabled_rule_roundtrip(self) -> None:
        rule = TriggerRule(name="disabled", enabled=False)
        restored = TriggerRule.from_dict(rule.to_dict())
        assert restored.enabled is False
