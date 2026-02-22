"""Tests for TriggerRule domain models."""


from taskforce.core.domain.trigger_rule import (
    RuleAction,
    RuleActionType,
    TriggerCondition,
    TriggerRule,
)


class TestTriggerCondition:
    """Tests for TriggerCondition dataclass."""

    def test_default_wildcards(self) -> None:
        cond = TriggerCondition()
        assert cond.source == "*"
        assert cond.event_type == "*"
        assert cond.filters == {}

    def test_to_dict(self) -> None:
        cond = TriggerCondition(
            source="calendar",
            event_type="calendar.upcoming",
            filters={"minutes_until": {"$lte": 30}},
        )
        d = cond.to_dict()
        assert d["source"] == "calendar"
        assert d["filters"]["minutes_until"]["$lte"] == 30

    def test_from_dict(self) -> None:
        data = {
            "source": "email",
            "event_type": "email.received",
            "filters": {"subject": {"$contains": "urgent"}},
        }
        cond = TriggerCondition.from_dict(data)
        assert cond.source == "email"
        assert cond.filters["subject"]["$contains"] == "urgent"


class TestRuleAction:
    """Tests for RuleAction dataclass."""

    def test_notify_action(self) -> None:
        action = RuleAction(
            action_type=RuleActionType.NOTIFY,
            params={"channel": "telegram"},
            template="Event: {{event.title}}",
        )
        assert action.action_type == RuleActionType.NOTIFY
        assert action.template == "Event: {{event.title}}"

    def test_to_dict_with_template(self) -> None:
        action = RuleAction(
            action_type=RuleActionType.NOTIFY,
            template="Test {{event.name}}",
        )
        d = action.to_dict()
        assert d["template"] == "Test {{event.name}}"

    def test_to_dict_without_template(self) -> None:
        action = RuleAction(action_type=RuleActionType.LOG_MEMORY)
        d = action.to_dict()
        assert "template" not in d

    def test_from_dict(self) -> None:
        data = {
            "action_type": "execute_mission",
            "params": {"mission": "Do something"},
        }
        action = RuleAction.from_dict(data)
        assert action.action_type == RuleActionType.EXECUTE_MISSION
        assert action.template is None


class TestTriggerRule:
    """Tests for TriggerRule dataclass."""

    def test_create_default(self) -> None:
        rule = TriggerRule()
        assert rule.rule_id
        assert rule.enabled is True
        assert rule.priority == 0

    def test_create_calendar_rule(self) -> None:
        rule = TriggerRule(
            name="calendar_reminder",
            description="Remind about upcoming calendar events",
            trigger=TriggerCondition(
                source="calendar",
                event_type="calendar.upcoming",
                filters={"minutes_until": {"$lte": 30}},
            ),
            action=RuleAction(
                action_type=RuleActionType.NOTIFY,
                params={"channel": "telegram"},
                template="Reminder: {{event.title}} in {{event.minutes_until}} min",
            ),
            priority=10,
        )
        assert rule.name == "calendar_reminder"
        assert rule.trigger.source == "calendar"
        assert rule.action.action_type == RuleActionType.NOTIFY
        assert rule.priority == 10

    def test_roundtrip(self) -> None:
        original = TriggerRule(
            name="test_rule",
            trigger=TriggerCondition(source="test", event_type="test.event"),
            action=RuleAction(
                action_type=RuleActionType.LOG_MEMORY,
                params={"scope": "user"},
            ),
        )
        restored = TriggerRule.from_dict(original.to_dict())
        assert restored.rule_id == original.rule_id
        assert restored.name == original.name
        assert restored.trigger.source == original.trigger.source
        assert restored.action.action_type == original.action.action_type
