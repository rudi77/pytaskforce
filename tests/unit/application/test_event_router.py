"""Tests for EventRouter."""

import pytest
from unittest.mock import AsyncMock

from taskforce.core.domain.agent_event import AgentEvent, AgentEventType
from taskforce.core.domain.trigger_rule import (
    RuleAction,
    RuleActionType,
    TriggerCondition,
    TriggerRule,
)
from taskforce.application.event_router import EventRouter
from taskforce.application.rule_engine import RuleEngine


class TestEventRouter:
    """Tests for the EventRouter."""

    @pytest.fixture
    def engine(self, tmp_path) -> RuleEngine:
        return RuleEngine(work_dir=str(tmp_path))

    @pytest.fixture
    def notify_callback(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def execute_callback(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def memory_callback(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def router(
        self,
        engine: RuleEngine,
        notify_callback: AsyncMock,
        execute_callback: AsyncMock,
        memory_callback: AsyncMock,
    ) -> EventRouter:
        return EventRouter(
            rule_engine=engine,
            notify_callback=notify_callback,
            execute_callback=execute_callback,
            memory_callback=memory_callback,
        )

    async def test_route_notify_action(
        self,
        engine: RuleEngine,
        router: EventRouter,
        notify_callback: AsyncMock,
    ) -> None:
        await engine.add_rule(
            TriggerRule(
                trigger=TriggerCondition(source="calendar"),
                action=RuleAction(
                    action_type=RuleActionType.NOTIFY,
                    params={"channel": "telegram", "recipient_id": "42", "message": "Hello!"},
                ),
            )
        )

        event = AgentEvent(source="calendar", event_type=AgentEventType.CALENDAR_UPCOMING)
        actions = await router.route(event)

        assert len(actions) == 1
        notify_callback.assert_called_once_with(
            "telegram", "42", "Hello!", {"channel": "telegram", "recipient_id": "42", "message": "Hello!"}
        )

    async def test_route_execute_action(
        self,
        engine: RuleEngine,
        router: EventRouter,
        execute_callback: AsyncMock,
    ) -> None:
        await engine.add_rule(
            TriggerRule(
                trigger=TriggerCondition(source="*"),
                action=RuleAction(
                    action_type=RuleActionType.EXECUTE_MISSION,
                    params={"mission": "Do the thing"},
                ),
            )
        )

        event = AgentEvent(source="scheduler", event_type=AgentEventType.SCHEDULE_TRIGGERED)
        actions = await router.route(event)

        assert len(actions) == 1
        execute_callback.assert_called_once()
        call_args = execute_callback.call_args[0]
        assert call_args[0] == "Do the thing"

    async def test_route_memory_action(
        self,
        engine: RuleEngine,
        router: EventRouter,
        memory_callback: AsyncMock,
    ) -> None:
        await engine.add_rule(
            TriggerRule(
                trigger=TriggerCondition(source="*"),
                action=RuleAction(
                    action_type=RuleActionType.LOG_MEMORY,
                    params={"content": "Something happened"},
                ),
            )
        )

        event = AgentEvent(source="test", event_type=AgentEventType.CUSTOM)
        await router.route(event)
        memory_callback.assert_called_once()

    async def test_no_matching_rules(
        self,
        engine: RuleEngine,
        router: EventRouter,
        notify_callback: AsyncMock,
    ) -> None:
        await engine.add_rule(
            TriggerRule(
                trigger=TriggerCondition(source="email"),
                action=RuleAction(action_type=RuleActionType.NOTIFY),
            )
        )

        event = AgentEvent(source="calendar", event_type=AgentEventType.CALENDAR_UPCOMING)
        actions = await router.route(event)

        assert len(actions) == 0
        notify_callback.assert_not_called()

    async def test_event_count_tracking(
        self, engine: RuleEngine, router: EventRouter
    ) -> None:
        assert router.event_count == 0
        await router.route(AgentEvent(source="test"))
        assert router.event_count == 1
        await router.route(AgentEvent(source="test"))
        assert router.event_count == 2

    async def test_action_count_tracking(
        self, engine: RuleEngine, router: EventRouter
    ) -> None:
        await engine.add_rule(
            TriggerRule(
                trigger=TriggerCondition(source="*"),
                action=RuleAction(
                    action_type=RuleActionType.NOTIFY,
                    params={"message": "test"},
                ),
            )
        )

        assert router.action_count == 0
        await router.route(AgentEvent(source="test"))
        assert router.action_count == 1

    async def test_llm_fallback_when_no_rules_match(
        self,
        engine: RuleEngine,
        execute_callback: AsyncMock,
    ) -> None:
        router = EventRouter(
            rule_engine=engine,
            execute_callback=execute_callback,
            llm_fallback=True,
        )

        event = AgentEvent(
            source="calendar",
            event_type=AgentEventType.CALENDAR_UPCOMING,
            payload={"title": "Unknown event"},
        )
        actions = await router.route(event)

        assert len(actions) == 0  # No rule-based actions
        execute_callback.assert_called_once()  # But LLM fallback was called
