"""Butler service orchestrating the event-driven agent lifecycle.

Coordinates the scheduler, event sources, rule engine, event router,
and learning service into a coherent always-on agent experience.
"""

from __future__ import annotations

from typing import Any

import structlog

from taskforce.application.event_router import EventRouter
from taskforce.application.rule_engine import RuleEngine
from taskforce.core.domain.agent_event import AgentEvent
from taskforce.core.domain.gateway import NotificationRequest
from taskforce.core.domain.trigger_rule import (
    RuleAction,
    RuleActionType,
    TriggerCondition,
    TriggerRule,
)
from taskforce.infrastructure.scheduler.scheduler_service import SchedulerService

logger = structlog.get_logger(__name__)


class ButlerService:
    """Orchestrates the butler's event-driven lifecycle.

    Wires together:
    - SchedulerService for time-based triggers
    - Event sources for external event ingestion
    - RuleEngine for event-to-action mapping
    - EventRouter for action dispatch
    - CommunicationGateway for notifications
    - AgentExecutor for mission execution
    """

    def __init__(
        self,
        work_dir: str = ".taskforce",
        default_notification_channel: str = "telegram",
        default_recipient_id: str = "",
        llm_fallback: bool = False,
    ) -> None:
        self._work_dir = work_dir
        self._default_channel = default_notification_channel
        self._default_recipient_id = default_recipient_id

        # Core components
        self._rule_engine = RuleEngine(work_dir=work_dir)
        self._scheduler = SchedulerService(
            work_dir=work_dir,
            event_callback=self._on_event,
        )
        self._event_router = EventRouter(
            rule_engine=self._rule_engine,
            notify_callback=self._send_notification,
            execute_callback=self._execute_mission,
            memory_callback=self._log_memory,
            llm_fallback=llm_fallback,
        )

        # Event sources (added via add_event_source)
        self._event_sources: list[Any] = []

        # External callbacks (injected by butler daemon)
        self._gateway: Any = None
        self._executor: Any = None
        self._memory_store: Any = None
        self._learning_service: Any = None

        self._running = False

    @property
    def rule_engine(self) -> RuleEngine:
        """Access the rule engine for direct rule management."""
        return self._rule_engine

    @property
    def scheduler(self) -> SchedulerService:
        """Access the scheduler for direct job management."""
        return self._scheduler

    @property
    def event_router(self) -> EventRouter:
        """Access the event router for stats and diagnostics."""
        return self._event_router

    @property
    def is_running(self) -> bool:
        """Whether the butler service is active."""
        return self._running

    def set_gateway(self, gateway: Any) -> None:
        """Inject the communication gateway for notifications."""
        self._gateway = gateway

    def set_executor(self, executor: Any) -> None:
        """Inject the agent executor for mission execution."""
        self._executor = executor

    def set_memory_store(self, memory_store: Any) -> None:
        """Inject the memory store for learning."""
        self._memory_store = memory_store

    def set_learning_service(self, learning_service: Any) -> None:
        """Inject the learning service for auto-extraction."""
        self._learning_service = learning_service

    def add_event_source(self, source: Any) -> None:
        """Register an event source.

        The source must implement EventSourceProtocol.
        Its event_callback will be set to self._on_event.
        """
        if hasattr(source, "_event_callback"):
            source._event_callback = self._on_event
        self._event_sources.append(source)

    async def start(self) -> None:
        """Start the butler service and all components."""
        if self._running:
            return

        logger.info("butler_service.starting")

        # Load persisted rules
        await self._rule_engine.load()

        # Start scheduler
        await self._scheduler.start()

        # Start event sources
        for source in self._event_sources:
            await source.start()

        self._running = True
        logger.info(
            "butler_service.started",
            event_sources=len(self._event_sources),
            rules=len(await self._rule_engine.list_rules()),
            jobs=len(await self._scheduler.list_jobs()),
        )

    async def stop(self) -> None:
        """Gracefully stop the butler service."""
        if not self._running:
            return

        logger.info("butler_service.stopping")

        # Stop event sources
        for source in self._event_sources:
            await source.stop()

        # Stop scheduler
        await self._scheduler.stop()

        self._running = False
        logger.info(
            "butler_service.stopped",
            events_processed=self._event_router.event_count,
            actions_dispatched=self._event_router.action_count,
        )

    async def add_rule_from_config(self, config: dict[str, Any]) -> str:
        """Add a rule from a butler profile configuration dict.

        Args:
            config: Rule configuration with keys: name, trigger, action, priority.

        Returns:
            The rule_id of the created rule.
        """
        trigger_cfg = config.get("trigger", {})
        action_cfg = config.get("action", {})

        action_type_str = action_cfg.get("type", "notify")
        action_type = RuleActionType(action_type_str)

        rule = TriggerRule(
            name=config.get("name", "unnamed"),
            description=config.get("description", ""),
            trigger=TriggerCondition(
                source=trigger_cfg.get("source", "*"),
                event_type=trigger_cfg.get("event_type", "*"),
                filters=trigger_cfg.get("filters", {}),
            ),
            action=RuleAction(
                action_type=action_type,
                params=action_cfg.get("params", {}),
                template=action_cfg.get("template"),
            ),
            priority=int(config.get("priority", 0)),
        )

        return await self._rule_engine.add_rule(rule)

    async def _on_event(self, event: AgentEvent) -> None:
        """Handle an incoming event from any source."""
        await self._event_router.route(event)

    async def _send_notification(
        self,
        channel: str,
        recipient_id: str,
        message: str,
        params: dict[str, Any],
    ) -> None:
        """Send a notification via the communication gateway."""
        if not self._gateway:
            logger.warning("butler_service.no_gateway_configured")
            return

        channel = channel or self._default_channel
        recipient_id = recipient_id or self._default_recipient_id

        request = NotificationRequest(
            channel=channel,
            recipient_id=recipient_id,
            message=message,
            metadata=params.get("metadata", {}),
        )
        result = await self._gateway.send_notification(request)
        if not result.success:
            logger.error(
                "butler_service.notification_failed",
                channel=channel,
                recipient_id=recipient_id,
                error=result.error,
            )

    async def _execute_mission(
        self,
        mission: str,
        params: dict[str, Any],
    ) -> None:
        """Execute an agent mission."""
        if not self._executor:
            logger.warning("butler_service.no_executor_configured")
            return

        profile = params.get("profile", "butler")
        try:
            result = await self._executor.execute_mission(
                mission=mission,
                profile=profile,
            )
            logger.info(
                "butler_service.mission_completed",
                status=result.status,
                mission_preview=mission[:100],
            )
        except Exception as exc:
            logger.error(
                "butler_service.mission_failed",
                mission_preview=mission[:100],
                error=str(exc),
            )

    async def _log_memory(
        self,
        content: str,
        params: dict[str, Any],
    ) -> None:
        """Log content to long-term memory."""
        if not self._memory_store:
            logger.warning("butler_service.no_memory_store_configured")
            return

        from taskforce.core.domain.memory import MemoryKind, MemoryRecord, MemoryScope

        record = MemoryRecord(
            scope=MemoryScope(params.get("scope", "user")),
            kind=MemoryKind(params.get("kind", "learned_fact")),
            content=content,
            tags=params.get("tags", []),
        )
        await self._memory_store.add(record)
        logger.info("butler_service.memory_logged", content_preview=content[:100])

    async def get_status(self) -> dict[str, Any]:
        """Get the current butler service status."""
        return {
            "running": self._running,
            "event_sources": [
                {
                    "name": getattr(s, "source_name", "unknown"),
                    "running": getattr(s, "is_running", False),
                }
                for s in self._event_sources
            ],
            "scheduler": {
                "running": self._scheduler.is_running,
                "jobs": len(await self._scheduler.list_jobs()),
            },
            "rules": len(await self._rule_engine.list_rules()),
            "events_processed": self._event_router.event_count,
            "actions_dispatched": self._event_router.action_count,
            "gateway_configured": self._gateway is not None,
            "executor_configured": self._executor is not None,
        }
