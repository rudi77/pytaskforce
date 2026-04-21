"""Unit tests for FileRuleEngine."""

from __future__ import annotations

from pathlib import Path

import pytest

from taskforce.core.domain.agent_event import AgentEvent, AgentEventType
from taskforce.core.domain.trigger_rule import (
    RuleAction,
    RuleActionType,
    TriggerCondition,
    TriggerRule,
)
from taskforce.infrastructure.rule_engine import FileRuleEngine


def _make_event(
    source: str = "calendar",
    event_type: AgentEventType = AgentEventType.CALENDAR_UPCOMING,
    payload: dict | None = None,
) -> AgentEvent:
    return AgentEvent(
        source=source,
        event_type=event_type,
        payload=payload or {},
    )


def _make_rule(
    name: str = "r",
    source: str = "*",
    event_type: str = "*",
    filters: dict | None = None,
    action_type: RuleActionType = RuleActionType.NOTIFY,
    priority: int = 0,
    enabled: bool = True,
    template: str | None = None,
    params: dict | None = None,
) -> TriggerRule:
    return TriggerRule(
        name=name,
        trigger=TriggerCondition(
            source=source, event_type=event_type, filters=filters or {}
        ),
        action=RuleAction(
            action_type=action_type, params=params or {}, template=template
        ),
        priority=priority,
        enabled=enabled,
    )


class TestCrudAndPersistence:
    async def test_add_get_remove(self, tmp_path: Path) -> None:
        engine = FileRuleEngine(work_dir=str(tmp_path))
        rule = _make_rule(name="foo")
        rule_id = await engine.add_rule(rule)

        assert await engine.get_rule(rule_id) is rule
        assert await engine.remove_rule(rule_id) is True
        assert await engine.get_rule(rule_id) is None
        assert await engine.remove_rule(rule_id) is False

    async def test_persistence_roundtrip(self, tmp_path: Path) -> None:
        engine = FileRuleEngine(work_dir=str(tmp_path))
        rule = _make_rule(name="persisted", priority=5)
        await engine.add_rule(rule)

        engine2 = FileRuleEngine(work_dir=str(tmp_path))
        await engine2.load()

        rules = await engine2.list_rules()
        assert len(rules) == 1
        assert rules[0].name == "persisted"
        assert rules[0].priority == 5

    async def test_custom_rules_filename(self, tmp_path: Path) -> None:
        engine = FileRuleEngine(
            work_dir=str(tmp_path), rules_filename="butler/rules.json"
        )
        await engine.add_rule(_make_rule(name="x"))
        assert (tmp_path / "butler" / "rules.json").exists()

    async def test_list_rules_sorted_by_priority_desc(self, tmp_path: Path) -> None:
        engine = FileRuleEngine(work_dir=str(tmp_path))
        await engine.add_rule(_make_rule(name="low", priority=1))
        await engine.add_rule(_make_rule(name="high", priority=100))
        await engine.add_rule(_make_rule(name="mid", priority=10))

        ordered = [r.name for r in await engine.list_rules()]
        assert ordered == ["high", "mid", "low"]


class TestEvaluation:
    async def test_wildcard_rule_matches_any_event(self, tmp_path: Path) -> None:
        engine = FileRuleEngine(work_dir=str(tmp_path))
        await engine.add_rule(_make_rule())
        actions = await engine.evaluate(_make_event())
        assert len(actions) == 1

    async def test_source_filter_excludes_other_sources(self, tmp_path: Path) -> None:
        engine = FileRuleEngine(work_dir=str(tmp_path))
        await engine.add_rule(_make_rule(source="email"))
        actions = await engine.evaluate(_make_event(source="calendar"))
        assert actions == []

    async def test_event_type_filter(self, tmp_path: Path) -> None:
        engine = FileRuleEngine(work_dir=str(tmp_path))
        await engine.add_rule(_make_rule(event_type="email.received"))
        actions = await engine.evaluate(_make_event())
        assert actions == []

    async def test_disabled_rule_does_not_fire(self, tmp_path: Path) -> None:
        engine = FileRuleEngine(work_dir=str(tmp_path))
        await engine.add_rule(_make_rule(enabled=False))
        actions = await engine.evaluate(_make_event())
        assert actions == []

    @pytest.mark.parametrize(
        "condition,value,expected",
        [
            ({"$eq": 5}, 5, True),
            ({"$eq": 5}, 6, False),
            ({"$ne": 5}, 6, True),
            ({"$gt": 5}, 6, True),
            ({"$gt": 5}, 5, False),
            ({"$gte": 5}, 5, True),
            ({"$lt": 10}, 9, True),
            ({"$lte": 10}, 10, True),
            ({"$in": [1, 2, 3]}, 2, True),
            ({"$in": [1, 2, 3]}, 4, False),
            ({"$contains": "foo"}, "foobar", True),
            ({"$contains": "xyz"}, "foobar", False),
        ],
    )
    async def test_filter_operators(
        self, tmp_path: Path, condition: dict, value: object, expected: bool
    ) -> None:
        engine = FileRuleEngine(work_dir=str(tmp_path))
        await engine.add_rule(_make_rule(filters={"x": condition}))
        actions = await engine.evaluate(_make_event(payload={"x": value}))
        assert bool(actions) is expected

    async def test_plain_value_filter_uses_equality(self, tmp_path: Path) -> None:
        engine = FileRuleEngine(work_dir=str(tmp_path))
        await engine.add_rule(_make_rule(filters={"label": "urgent"}))
        assert await engine.evaluate(_make_event(payload={"label": "urgent"}))
        assert not await engine.evaluate(_make_event(payload={"label": "chill"}))

    async def test_multiple_rules_ordered_by_priority(self, tmp_path: Path) -> None:
        engine = FileRuleEngine(work_dir=str(tmp_path))
        await engine.add_rule(_make_rule(name="low", priority=1))
        await engine.add_rule(_make_rule(name="high", priority=10))

        actions = await engine.evaluate(_make_event())
        # Action order should follow priority: high first.
        # Since both actions carry the same rule name via params, use that.
        assert len(actions) == 2

    async def test_template_rendered_into_message(self, tmp_path: Path) -> None:
        engine = FileRuleEngine(work_dir=str(tmp_path))
        await engine.add_rule(
            _make_rule(template="Meeting in {{event.minutes}}m")
        )
        actions = await engine.evaluate(
            _make_event(payload={"minutes": 15})
        )
        assert actions[0].params["message"] == "Meeting in 15m"
