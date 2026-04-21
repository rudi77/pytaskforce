"""Unit tests for the application-layer EventRouter."""

from __future__ import annotations

from typing import Any

from taskforce.application.event_router import EventRouter
from taskforce.core.domain.agent_event import AgentEvent, AgentEventType
from taskforce.core.domain.trigger_rule import (
    RuleAction,
    RuleActionType,
    TriggerCondition,
    TriggerRule,
)


class _StubRuleEngine:
    """Minimal in-memory RuleEngine stub for testing the router in isolation."""

    def __init__(self) -> None:
        self._rules: list[TriggerRule] = []

    async def add_rule(self, rule: TriggerRule) -> str:
        self._rules.append(rule)
        return rule.rule_id

    async def remove_rule(self, rule_id: str) -> bool:
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.rule_id != rule_id]
        return len(self._rules) < before

    async def get_rule(self, rule_id: str) -> TriggerRule | None:
        for r in self._rules:
            if r.rule_id == rule_id:
                return r
        return None

    async def list_rules(self) -> list[TriggerRule]:
        return list(self._rules)

    async def evaluate(self, event: AgentEvent) -> list[RuleAction]:
        matches = []
        for r in self._rules:
            if r.trigger.source in ("*", event.source):
                matches.append(r.action)
        return matches


def _event(source: str = "calendar", payload: dict | None = None) -> AgentEvent:
    return AgentEvent(
        source=source,
        event_type=AgentEventType.CALENDAR_UPCOMING,
        payload=payload or {},
    )


def _rule(
    action_type: RuleActionType = RuleActionType.NOTIFY,
    params: dict | None = None,
) -> TriggerRule:
    return TriggerRule(
        trigger=TriggerCondition(source="*"),
        action=RuleAction(action_type=action_type, params=params or {}),
    )


class TestEventRouterDispatch:
    async def test_notify_callback_invoked(self) -> None:
        engine = _StubRuleEngine()
        notify_args: list[tuple[str, str, str, dict[str, Any]]] = []

        async def on_notify(channel, recipient_id, message, params):
            notify_args.append((channel, recipient_id, message, params))

        router = EventRouter(
            rule_engine=engine,
            notify_callback=on_notify,
            default_channel="telegram",
        )
        await engine.add_rule(
            _rule(params={"recipient_id": "user-1", "message": "Hi!"})
        )

        await router.route(_event())
        assert len(notify_args) == 1
        channel, recipient, message, _ = notify_args[0]
        assert channel == "telegram"
        assert recipient == "user-1"
        assert message == "Hi!"

    async def test_default_channel_defaults_to_empty(self) -> None:
        engine = _StubRuleEngine()
        channels: list[str] = []

        async def on_notify(channel, *args):
            channels.append(channel)

        router = EventRouter(rule_engine=engine, notify_callback=on_notify)
        await engine.add_rule(_rule(params={"message": "x"}))

        await router.route(_event())
        assert channels == [""]

    async def test_execute_callback_invoked(self) -> None:
        engine = _StubRuleEngine()
        missions: list[str] = []

        async def on_execute(mission, _params):
            missions.append(mission)

        router = EventRouter(rule_engine=engine, execute_callback=on_execute)
        await engine.add_rule(
            _rule(
                action_type=RuleActionType.EXECUTE_MISSION,
                params={"mission": "Do the thing"},
            )
        )

        await router.route(_event())
        assert missions == ["Do the thing"]

    async def test_memory_callback_invoked(self) -> None:
        engine = _StubRuleEngine()
        stored: list[str] = []

        async def on_memory(content, _params):
            stored.append(content)

        router = EventRouter(rule_engine=engine, memory_callback=on_memory)
        await engine.add_rule(
            _rule(
                action_type=RuleActionType.LOG_MEMORY,
                params={"content": "important"},
            )
        )

        await router.route(_event())
        assert stored == ["important"]

    async def test_dream_callback_invoked(self) -> None:
        engine = _StubRuleEngine()
        calls: list[dict] = []

        async def on_dream(params):
            calls.append(params)

        router = EventRouter(rule_engine=engine, dream_callback=on_dream)
        await engine.add_rule(_rule(action_type=RuleActionType.RUN_DREAM_CYCLE))

        await router.route(_event())
        assert len(calls) == 1

    async def test_no_rules_match_yields_empty_list(self) -> None:
        engine = _StubRuleEngine()
        router = EventRouter(rule_engine=engine)
        assert await router.route(_event()) == []

    async def test_llm_fallback_triggers_when_enabled(self) -> None:
        engine = _StubRuleEngine()
        missions: list[tuple[str, dict]] = []

        async def on_execute(mission, params):
            missions.append((mission, params))

        router = EventRouter(
            rule_engine=engine,
            execute_callback=on_execute,
            llm_fallback=True,
        )
        await router.route(_event())
        assert len(missions) == 1
        assert missions[0][1] == {"llm_fallback": True}

    async def test_counters_increment(self) -> None:
        engine = _StubRuleEngine()

        async def _noop(*_args):
            pass

        router = EventRouter(rule_engine=engine, notify_callback=_noop)
        await engine.add_rule(_rule(params={"message": "m"}))

        await router.route(_event())
        await router.route(_event())
        assert router.event_count == 2
        assert router.action_count == 2

    async def test_dispatch_failure_does_not_propagate(self) -> None:
        engine = _StubRuleEngine()

        async def on_notify(*_args):
            raise RuntimeError("boom")

        router = EventRouter(rule_engine=engine, notify_callback=on_notify)
        await engine.add_rule(_rule(params={"message": "m"}))

        # Should not raise.
        actions = await router.route(_event())
        assert len(actions) == 1
