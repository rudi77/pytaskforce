"""Tests for RuleEngine."""

import pytest

from taskforce.core.domain.agent_event import AgentEvent, AgentEventType
from taskforce.core.domain.trigger_rule import (
    RuleAction,
    RuleActionType,
    TriggerCondition,
    TriggerRule,
)
from taskforce.application.rule_engine import RuleEngine, _match_filter, _matches_event


class TestMatchFilter:
    """Tests for the _match_filter helper."""

    def test_plain_equality(self) -> None:
        assert _match_filter("hello", "hello") is True
        assert _match_filter("hello", "world") is False

    def test_eq_operator(self) -> None:
        assert _match_filter(42, {"$eq": 42}) is True
        assert _match_filter(42, {"$eq": 43}) is False

    def test_ne_operator(self) -> None:
        assert _match_filter(42, {"$ne": 43}) is True
        assert _match_filter(42, {"$ne": 42}) is False

    def test_gt_gte(self) -> None:
        assert _match_filter(10, {"$gt": 5}) is True
        assert _match_filter(5, {"$gt": 5}) is False
        assert _match_filter(5, {"$gte": 5}) is True

    def test_lt_lte(self) -> None:
        assert _match_filter(5, {"$lt": 10}) is True
        assert _match_filter(10, {"$lt": 10}) is False
        assert _match_filter(10, {"$lte": 10}) is True

    def test_in_operator(self) -> None:
        assert _match_filter("a", {"$in": ["a", "b", "c"]}) is True
        assert _match_filter("d", {"$in": ["a", "b", "c"]}) is False

    def test_contains_operator(self) -> None:
        assert _match_filter("hello world", {"$contains": "world"}) is True
        assert _match_filter("hello world", {"$contains": "xyz"}) is False

    def test_combined_operators(self) -> None:
        assert _match_filter(15, {"$gte": 10, "$lte": 20}) is True
        assert _match_filter(25, {"$gte": 10, "$lte": 20}) is False


class TestMatchesEvent:
    """Tests for the _matches_event helper."""

    def test_wildcard_matches_all(self) -> None:
        rule = TriggerRule(trigger=TriggerCondition(source="*", event_type="*"))
        event = AgentEvent(source="calendar", event_type=AgentEventType.CALENDAR_UPCOMING)
        assert _matches_event(rule, event) is True

    def test_source_mismatch(self) -> None:
        rule = TriggerRule(trigger=TriggerCondition(source="email"))
        event = AgentEvent(source="calendar", event_type=AgentEventType.CALENDAR_UPCOMING)
        assert _matches_event(rule, event) is False

    def test_event_type_mismatch(self) -> None:
        rule = TriggerRule(
            trigger=TriggerCondition(source="calendar", event_type="calendar.ended")
        )
        event = AgentEvent(source="calendar", event_type=AgentEventType.CALENDAR_UPCOMING)
        assert _matches_event(rule, event) is False

    def test_filter_match(self) -> None:
        rule = TriggerRule(
            trigger=TriggerCondition(
                source="calendar",
                event_type="calendar.upcoming",
                filters={"minutes_until": {"$lte": 30}},
            )
        )
        event = AgentEvent(
            source="calendar",
            event_type=AgentEventType.CALENDAR_UPCOMING,
            payload={"minutes_until": 15},
        )
        assert _matches_event(rule, event) is True

    def test_filter_no_match(self) -> None:
        rule = TriggerRule(
            trigger=TriggerCondition(
                source="calendar",
                event_type="calendar.upcoming",
                filters={"minutes_until": {"$lte": 5}},
            )
        )
        event = AgentEvent(
            source="calendar",
            event_type=AgentEventType.CALENDAR_UPCOMING,
            payload={"minutes_until": 30},
        )
        assert _matches_event(rule, event) is False


class TestRuleEngine:
    """Tests for the RuleEngine."""

    @pytest.fixture
    def engine(self, tmp_path) -> RuleEngine:
        return RuleEngine(work_dir=str(tmp_path))

    async def test_add_and_list_rules(self, engine: RuleEngine) -> None:
        rule = TriggerRule(name="test_rule")
        await engine.add_rule(rule)

        rules = await engine.list_rules()
        assert len(rules) == 1
        assert rules[0].name == "test_rule"

    async def test_remove_rule(self, engine: RuleEngine) -> None:
        rule = TriggerRule(name="to_remove")
        await engine.add_rule(rule)

        removed = await engine.remove_rule(rule.rule_id)
        assert removed is True

        removed_again = await engine.remove_rule(rule.rule_id)
        assert removed_again is False

    async def test_get_rule(self, engine: RuleEngine) -> None:
        rule = TriggerRule(name="findable")
        await engine.add_rule(rule)

        found = await engine.get_rule(rule.rule_id)
        assert found is not None
        assert found.name == "findable"

        not_found = await engine.get_rule("nonexistent")
        assert not_found is None

    async def test_evaluate_matching_rule(self, engine: RuleEngine) -> None:
        rule = TriggerRule(
            name="calendar_notify",
            trigger=TriggerCondition(
                source="calendar",
                event_type="calendar.upcoming",
                filters={"minutes_until": {"$lte": 30}},
            ),
            action=RuleAction(
                action_type=RuleActionType.NOTIFY,
                params={"channel": "telegram"},
            ),
        )
        await engine.add_rule(rule)

        event = AgentEvent(
            source="calendar",
            event_type=AgentEventType.CALENDAR_UPCOMING,
            payload={"minutes_until": 15, "title": "Meeting"},
        )

        actions = await engine.evaluate(event)
        assert len(actions) == 1
        assert actions[0].action_type == RuleActionType.NOTIFY

    async def test_evaluate_no_match(self, engine: RuleEngine) -> None:
        rule = TriggerRule(
            trigger=TriggerCondition(source="email"),
            action=RuleAction(action_type=RuleActionType.NOTIFY),
        )
        await engine.add_rule(rule)

        event = AgentEvent(source="calendar", event_type=AgentEventType.CALENDAR_UPCOMING)
        actions = await engine.evaluate(event)
        assert len(actions) == 0

    async def test_evaluate_disabled_rule(self, engine: RuleEngine) -> None:
        rule = TriggerRule(
            trigger=TriggerCondition(source="*"),
            action=RuleAction(action_type=RuleActionType.NOTIFY),
            enabled=False,
        )
        await engine.add_rule(rule)

        event = AgentEvent(source="calendar", event_type=AgentEventType.CALENDAR_UPCOMING)
        actions = await engine.evaluate(event)
        assert len(actions) == 0

    async def test_evaluate_priority_order(self, engine: RuleEngine) -> None:
        low = TriggerRule(
            name="low_priority",
            trigger=TriggerCondition(source="*"),
            action=RuleAction(
                action_type=RuleActionType.LOG_MEMORY,
                params={"order": "low"},
            ),
            priority=1,
        )
        high = TriggerRule(
            name="high_priority",
            trigger=TriggerCondition(source="*"),
            action=RuleAction(
                action_type=RuleActionType.NOTIFY,
                params={"order": "high"},
            ),
            priority=10,
        )
        await engine.add_rule(low)
        await engine.add_rule(high)

        event = AgentEvent(source="test", event_type=AgentEventType.CUSTOM)
        actions = await engine.evaluate(event)
        assert len(actions) == 2
        assert actions[0].params["order"] == "high"
        assert actions[1].params["order"] == "low"

    async def test_evaluate_with_template(self, engine: RuleEngine) -> None:
        rule = TriggerRule(
            trigger=TriggerCondition(source="calendar"),
            action=RuleAction(
                action_type=RuleActionType.NOTIFY,
                params={"channel": "telegram"},
                template="Reminder: {{event.title}} in {{event.minutes_until}} min",
            ),
        )
        await engine.add_rule(rule)

        event = AgentEvent(
            source="calendar",
            event_type=AgentEventType.CALENDAR_UPCOMING,
            payload={"title": "Standup", "minutes_until": 5},
        )
        actions = await engine.evaluate(event)
        assert len(actions) == 1
        msg = actions[0].params.get("message", "")
        assert "Standup" in msg
        assert "5" in msg

    async def test_persistence(self, tmp_path) -> None:
        """Test that rules survive load/save cycle."""
        engine1 = RuleEngine(work_dir=str(tmp_path))
        rule = TriggerRule(name="persistent_rule")
        await engine1.add_rule(rule)

        engine2 = RuleEngine(work_dir=str(tmp_path))
        await engine2.load()
        rules = await engine2.list_rules()
        assert len(rules) == 1
        assert rules[0].name == "persistent_rule"
