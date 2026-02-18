"""Event router that dispatches agent events through the rule engine.

Connects the message bus to the rule engine and dispatches resulting
actions (notifications, agent missions, memory logging).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from taskforce.application.rule_engine import RuleEngine
from taskforce.core.domain.agent_event import AgentEvent
from taskforce.core.domain.trigger_rule import RuleAction, RuleActionType

logger = structlog.get_logger(__name__)


class EventRouter:
    """Routes AgentEvents through the RuleEngine and dispatches actions.

    For each incoming event:
      1. Evaluate all rules via the RuleEngine
      2. For 'notify' actions -> send notification via callback
      3. For 'execute_mission' actions -> execute agent mission via callback
      4. For 'log_memory' actions -> store in memory via callback
      5. If no rules match and llm_fallback is enabled -> send to agent

    Callbacks are injected to avoid direct dependencies on infrastructure.
    """

    def __init__(
        self,
        rule_engine: RuleEngine,
        notify_callback: Callable[[str, str, str, dict[str, Any]], Awaitable[None]] | None = None,
        execute_callback: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
        memory_callback: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
        llm_fallback: bool = False,
    ) -> None:
        self._rule_engine = rule_engine
        self._notify_callback = notify_callback
        self._execute_callback = execute_callback
        self._memory_callback = memory_callback
        self._llm_fallback = llm_fallback
        self._event_count = 0
        self._action_count = 0

    @property
    def event_count(self) -> int:
        """Number of events processed."""
        return self._event_count

    @property
    def action_count(self) -> int:
        """Number of actions dispatched."""
        return self._action_count

    async def route(self, event: AgentEvent) -> list[RuleAction]:
        """Route an event through the rule engine and dispatch actions.

        Args:
            event: The incoming event to process.

        Returns:
            List of actions that were dispatched.
        """
        self._event_count += 1
        logger.info(
            "event_router.routing",
            event_id=event.event_id,
            source=event.source,
            event_type=event.event_type.value,
        )

        actions = await self._rule_engine.evaluate(event)

        if not actions:
            logger.debug(
                "event_router.no_matching_rules",
                event_id=event.event_id,
                event_type=event.event_type.value,
            )
            if self._llm_fallback and self._execute_callback:
                await self._dispatch_llm_fallback(event)
            return []

        for action in actions:
            await self._dispatch_action(action, event)
            self._action_count += 1

        return actions

    async def _dispatch_action(self, action: RuleAction, event: AgentEvent) -> None:
        """Dispatch a single rule action."""
        try:
            if action.action_type == RuleActionType.NOTIFY:
                await self._dispatch_notify(action, event)
            elif action.action_type == RuleActionType.EXECUTE_MISSION:
                await self._dispatch_execute(action, event)
            elif action.action_type == RuleActionType.LOG_MEMORY:
                await self._dispatch_memory(action, event)
            else:
                logger.warning(
                    "event_router.unknown_action_type",
                    action_type=action.action_type.value,
                )
        except Exception as exc:
            logger.error(
                "event_router.dispatch_failed",
                action_type=action.action_type.value,
                error=str(exc),
            )

    async def _dispatch_notify(self, action: RuleAction, event: AgentEvent) -> None:
        """Dispatch a notification action."""
        if not self._notify_callback:
            logger.warning("event_router.no_notify_callback")
            return

        channel = action.params.get("channel", "telegram")
        recipient_id = action.params.get("recipient_id", "")
        message = action.params.get("message", "")

        if not message:
            message = f"Event: {event.event_type.value} from {event.source}"

        logger.info(
            "event_router.dispatching_notification",
            channel=channel,
            recipient_id=recipient_id,
            message_preview=message[:100],
        )
        await self._notify_callback(channel, recipient_id, message, action.params)

    async def _dispatch_execute(self, action: RuleAction, event: AgentEvent) -> None:
        """Dispatch an execute_mission action."""
        if not self._execute_callback:
            logger.warning("event_router.no_execute_callback")
            return

        mission = action.params.get("mission", "")
        if not mission:
            mission = (
                f"Handle event '{event.event_type.value}' from '{event.source}': "
                f"{event.payload}"
            )

        logger.info(
            "event_router.dispatching_mission",
            mission_preview=mission[:100],
        )
        await self._execute_callback(mission, action.params)

    async def _dispatch_memory(self, action: RuleAction, event: AgentEvent) -> None:
        """Dispatch a memory logging action."""
        if not self._memory_callback:
            logger.warning("event_router.no_memory_callback")
            return

        content = action.params.get("content", "")
        if not content:
            content = (
                f"Event logged: {event.event_type.value} from {event.source} - " f"{event.payload}"
            )

        logger.info("event_router.dispatching_memory_log", content_preview=content[:100])
        await self._memory_callback(content, action.params)

    async def _dispatch_llm_fallback(self, event: AgentEvent) -> None:
        """Send unmatched event to the LLM for intelligent handling."""
        if not self._execute_callback:
            return

        mission = (
            f"An event has occurred that has no matching rules. "
            f"Please decide what to do.\n\n"
            f"Event source: {event.source}\n"
            f"Event type: {event.event_type.value}\n"
            f"Payload: {event.payload}\n"
            f"Metadata: {event.metadata}"
        )

        logger.info(
            "event_router.llm_fallback",
            event_id=event.event_id,
            event_type=event.event_type.value,
        )
        await self._execute_callback(mission, {"llm_fallback": True})
