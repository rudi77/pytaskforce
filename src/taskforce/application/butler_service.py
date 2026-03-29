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
        self._agent_service: Any = None  # PersistentAgentService (preferred over executor)
        self._memory_store: Any = None
        self._learning_service: Any = None
        self._dream_service: Any = None

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

    def set_agent_service(self, agent_service: Any) -> None:
        """Inject the PersistentAgentService for queue-based execution.

        When set, events are routed through the central request queue
        instead of calling the executor directly. This prevents race
        conditions between event-triggered and user-initiated requests.
        """
        self._agent_service = agent_service

    def set_memory_store(self, memory_store: Any) -> None:
        """Inject the memory store for learning."""
        self._memory_store = memory_store

    def set_learning_service(self, learning_service: Any) -> None:
        """Inject the learning service for auto-extraction."""
        self._learning_service = learning_service

    def set_dream_service(self, dream_service: Any) -> None:
        """Inject the dream service for generative dreaming cycles."""
        self._dream_service = dream_service
        self._event_router._dream_callback = self._run_dream_cycle

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
        """Handle an incoming event from any source.

        For scheduler events, the job's action is embedded in the event
        payload and dispatched directly — no matching rule is required.
        The event is still forwarded to the event router so that
        additional user-defined rules can fire as well.
        """
        from taskforce.core.domain.agent_event import AgentEventType
        from taskforce.core.domain.schedule import ScheduleActionType

        if event.event_type == AgentEventType.SCHEDULE_TRIGGERED:
            await self._dispatch_schedule_action(event)

        await self._event_router.route(event)

    async def _dispatch_schedule_action(self, event: AgentEvent) -> None:
        """Dispatch the action embedded in a scheduler event directly.

        Scheduled jobs carry their own action definition in
        ``event.payload["action"]``.  This method extracts that action
        and delegates to the appropriate handler so that jobs work even
        when no trigger rules are configured.
        """
        from taskforce.core.domain.schedule import ScheduleActionType

        action_data = event.payload.get("action")
        if not action_data:
            logger.warning(
                "butler_service.schedule_event_missing_action",
                event_id=event.event_id,
            )
            return

        action_type_str = action_data.get("action_type", "")
        params: dict[str, Any] = action_data.get("params", {})
        job_name = event.payload.get("job_name", "")

        try:
            action_type = ScheduleActionType(action_type_str)
        except ValueError:
            logger.warning(
                "butler_service.unknown_schedule_action",
                action_type=action_type_str,
                event_id=event.event_id,
            )
            return

        logger.info(
            "butler_service.dispatching_schedule_action",
            job_name=job_name,
            action_type=action_type_str,
        )

        if action_type == ScheduleActionType.SEND_NOTIFICATION:
            channel = params.get("channel", self._default_channel)
            recipient_id = params.get("recipient_id", self._default_recipient_id)
            message = params.get("message", "")
            if not message:
                message = f"Scheduled notification: {job_name}"
            await self._send_notification(channel, recipient_id, message, params)

        elif action_type == ScheduleActionType.EXECUTE_MISSION:
            mission = params.get("mission", "")
            if not mission:
                mission = (
                    f"Scheduled task '{job_name}' triggered. "
                    f"Execute the task described by its name and report results."
                )
            await self._execute_mission(mission, params)

        elif action_type == ScheduleActionType.RUN_DREAM_CYCLE:
            await self._run_dream_cycle(params)

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
        """Execute an agent mission.

        When a PersistentAgentService is available, the mission is routed
        through the central request queue to prevent race conditions with
        concurrent user requests. Falls back to direct executor call.
        """
        profile = params.get("profile", "butler")
        priority = params.get("priority", 5)  # Scheduled/event tasks default to priority 5

        # Prefer queue-based execution when PersistentAgentService is available.
        if self._agent_service is not None:
            try:
                from taskforce.core.domain.request import AgentRequest

                request = AgentRequest(
                    channel="event",
                    message=mission,
                    metadata={"profile": profile},
                    priority=priority,
                )
                result = await self._agent_service.submit(request)
                logger.info(
                    "butler_service.mission_completed",
                    status=result.status,
                    mission_preview=mission[:100],
                    via="queue",
                )
                return
            except Exception as exc:
                logger.error(
                    "butler_service.queue_mission_failed",
                    mission_preview=mission[:100],
                    error=str(exc),
                )
                return

        # Fallback: direct executor call (no PersistentAgentService wired).
        if not self._executor:
            logger.warning("butler_service.no_executor_configured")
            return

        try:
            result = await self._executor.execute_mission(
                mission=mission,
                profile=profile,
            )
            logger.info(
                "butler_service.mission_completed",
                status=result.status,
                mission_preview=mission[:100],
                via="direct",
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

    async def _run_dream_cycle(self, params: dict[str, Any]) -> None:
        """Run a generative dream cycle."""
        if not self._dream_service:
            logger.warning("butler_service.no_dream_service_configured")
            return

        from taskforce.core.domain.dream import DreamTrigger

        trigger = DreamTrigger(params.get("trigger", "scheduled"))
        try:
            cycle = await self._dream_service.trigger_dream(trigger=trigger)
            logger.info(
                "butler_service.dream_completed",
                dream_id=cycle.dream_id,
                insights=len(cycle.insights),
                memories_created=cycle.memories_created,
            )
        except Exception as exc:
            logger.error("butler_service.dream_failed", error=str(exc))

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
