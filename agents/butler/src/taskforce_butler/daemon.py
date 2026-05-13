"""Butler daemon that orchestrates the event-driven agent lifecycle.

The daemon is the top-level process that:
1. Loads butler profile configuration
2. Builds all infrastructure components
3. Starts the ButlerService with event sources, scheduler, and rules
4. Optionally starts a PersistentAgentService for queue-based execution
5. Writes periodic status files for the CLI to read
6. Handles graceful shutdown
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from taskforce.core.utils.time import utc_now
from taskforce_butler.service import ButlerService

logger = structlog.get_logger(__name__)


class ButlerDaemon:
    """Top-level butler daemon process.

    Initializes and manages all butler components based on
    the butler profile YAML configuration.

    When ``persistent_agent=True`` (default), the daemon creates a
    ``PersistentAgentService`` that processes all mission-execution
    requests through a central ``RequestQueue``, ensuring sequential
    agent execution and persistent conversation state (ADR-016).
    """

    def __init__(
        self,
        profile: str = "butler",
        work_dir: str = ".taskforce",
        persistent_agent: bool = True,
        role: str | None = None,
    ) -> None:
        self._profile = profile
        self._work_dir = work_dir
        self._persistent_agent_enabled = persistent_agent
        self._role_override = role
        self._butler: ButlerService | None = None
        self._agent_service: Any = None  # PersistentAgentService | None
        self._running = False
        self._status_task: asyncio.Task[None] | None = None
        self._status_path = Path(work_dir) / "butler" / "status.json"
        # Proactive layer (Phase 3) — populated by _setup_proactive_layer.
        self._proactive_evaluator: Any = None
        self._proactive_task: asyncio.Task[None] | None = None
        # Watchdog support (issue #156): every status-loop tick refreshes
        # ``_last_heartbeat`` so a supervising ``DaemonSupervisor`` can
        # detect a stalled main loop without poking at internals.
        self._last_heartbeat: datetime = utc_now()

    @property
    def is_running(self) -> bool:
        """Whether the daemon is active."""
        return self._running

    @property
    def agent_service(self) -> Any:
        """The PersistentAgentService, if active."""
        return self._agent_service

    @property
    def last_heartbeat(self) -> datetime:
        """Timestamp of the most recent main-loop heartbeat.

        Refreshed on every iteration of :meth:`_write_status_loop` and
        also at the end of :meth:`start`. Used by ``DaemonSupervisor``
        to detect stalled loops (see issue #156).
        """
        return self._last_heartbeat

    def touch_heartbeat(self) -> None:
        """Refresh the heartbeat timestamp from any internal task."""
        self._last_heartbeat = utc_now()

    async def start(self) -> None:
        """Start the butler daemon with full component initialization."""
        logger.info("butler_daemon.starting", profile=self._profile)

        config = self._load_config()

        # Build butler service
        self._butler = ButlerService(
            work_dir=self._work_dir,
            default_notification_channel=config.get("notifications", {}).get(
                "default_channel", "telegram"
            ),
            default_recipient_id=config.get("notifications", {}).get("default_recipient_id", ""),
            llm_fallback=config.get("agent", {}).get("llm_fallback", False),
        )

        # Build shared AuthManager for Google/Microsoft tools
        auth_manager = self._build_auth_manager(config)

        # Try to wire up communication gateway
        await self._setup_gateway(config, auth_manager=auth_manager)

        # Try to wire up executor (and optionally PersistentAgentService)
        await self._setup_executor(config, auth_manager=auth_manager)

        # Set up event sources
        await self._setup_event_sources(config)

        # Load rules from config
        await self._load_rules(config)

        # Start the butler service
        await self._butler.start()

        # Start the persistent agent service if wired
        if self._agent_service:
            await self._agent_service.start()
            # Publish to the API layer so /api/v1/missions can list and
            # cancel queued/in-flight missions when the daemon embeds the
            # REST API in the same process.
            try:
                from taskforce.api.dependencies import set_persistent_agent_service

                set_persistent_agent_service(self._agent_service)
            except Exception:  # pragma: no cover — API package optional
                pass
            logger.info("butler_daemon.persistent_agent_started")

        # Wire the proactive layer (standing goals + heartbeat) when
        # configured. Failure is non-fatal — the rest of the daemon
        # stays useful even without proactive evaluation.
        await self._setup_proactive_layer(config)

        self._running = True
        self._last_heartbeat = utc_now()

        # Start periodic status writer
        self._status_task = asyncio.create_task(self._write_status_loop(), name="butler-status")

        logger.info("butler_daemon.started", profile=self._profile)

    async def stop(self) -> None:
        """Gracefully stop the butler daemon."""
        logger.info("butler_daemon.stopping")

        if self._status_task:
            self._status_task.cancel()
            try:
                await self._status_task
            except asyncio.CancelledError:
                pass

        if self._proactive_task is not None:
            self._proactive_task.cancel()
            try:
                await self._proactive_task
            except asyncio.CancelledError:
                pass
            self._proactive_task = None
            try:
                from taskforce.api.dependencies import (
                    set_goal_evaluator,
                    set_standing_goal_store,
                )

                set_goal_evaluator(None)
                set_standing_goal_store(None)
            except Exception:  # pragma: no cover
                pass

        # Stop persistent agent service first (drains queue).
        if self._agent_service:
            try:
                from taskforce.api.dependencies import set_persistent_agent_service

                set_persistent_agent_service(None)
            except Exception:  # pragma: no cover — API package optional
                pass
            await self._agent_service.stop()

        # Drop active event sources from the API registry so the events
        # route returns 404 instead of forwarding to a stopped source.
        try:
            from taskforce.api.dependencies import (
                list_active_event_sources,
                unregister_active_event_source,
            )

            for name in list(list_active_event_sources()):
                unregister_active_event_source(name)
        except Exception:  # pragma: no cover
            pass

        if self._butler:
            await self._butler.stop()

        self._running = False

        # Write final status
        await self._write_status()

        logger.info("butler_daemon.stopped")

    def _load_config(self) -> dict[str, Any]:
        """Load butler profile configuration and apply role overlay if set."""
        from taskforce.application.factory import AgentFactory
        from taskforce.application.profile_loader import ProfileLoader

        factory = AgentFactory()
        profile_loader = ProfileLoader(factory.config_dir)
        try:
            config = profile_loader.load(self._profile)
        except FileNotFoundError as exc:
            logger.warning(
                "butler_daemon.config_not_found",
                profile=self._profile,
                error=str(exc),
            )
            config = {}

        # Resolve and apply butler role overlay
        role_name = self._role_override or config.get("role")
        if role_name:
            from taskforce_butler.role_loader import ButlerRoleLoader

            role_loader = ButlerRoleLoader(
                config_dir=factory.config_dir,
                project_dir=Path(self._work_dir),
            )
            try:
                role = role_loader.load(role_name)
                config = role_loader.merge_into_config(config, role)
                logger.info(
                    "butler_daemon.role_applied",
                    role=role_name,
                )
            except FileNotFoundError:
                logger.error(
                    "butler_daemon.role_not_found",
                    role=role_name,
                )

        return config

    def _build_auth_manager(self, config: dict[str, Any]) -> Any:
        """Build the centralized AuthManager for OAuth2 token lifecycle.

        Returns the AuthManager instance, or None if the auth extra is
        not installed (cryptography package missing).
        """
        try:
            from taskforce.application.auth_manager import AuthManager
            from taskforce.infrastructure.auth.encrypted_token_store import EncryptedTokenStore
            from taskforce.infrastructure.auth.oauth2_device_flow import OAuth2DeviceFlow

            token_store = EncryptedTokenStore()

            # Provider configs from butler profile or sensible defaults.
            auth_cfg = config.get("auth", {})
            provider_configs = auth_cfg.get("providers", {})

            auth_flows: dict[str, Any] = {"oauth2_device": OAuth2DeviceFlow()}

            # Optionally include auth code flow.
            try:
                from taskforce.infrastructure.auth.oauth2_auth_code_flow import (
                    OAuth2AuthCodeFlow,
                )

                auth_flows["oauth2_auth_code"] = OAuth2AuthCodeFlow()
            except ImportError:
                pass

            manager = AuthManager(
                token_store=token_store,
                auth_flows=auth_flows,
                provider_configs=provider_configs,
            )
            logger.info("butler_daemon.auth_manager_configured")
            return manager

        except ImportError as exc:
            logger.warning(
                "butler_daemon.auth_manager_unavailable",
                error=str(exc),
                hint="cryptography ships in the core install — run 'uv sync' to repair the venv",
            )
            return None

    async def _setup_gateway(self, config: dict[str, Any], *, auth_manager: Any = None) -> None:
        """Set up the communication gateway if configured."""
        if self._butler is None:
            return

        try:
            from taskforce.application.executor import AgentExecutor
            from taskforce.application.factory import AgentFactory
            from taskforce.application.gateway import CommunicationGateway
            from taskforce.application.infrastructure_builder import InfrastructureBuilder

            components = InfrastructureBuilder().build_gateway_components(work_dir=self._work_dir)
            if components.outbound_senders:
                factory = AgentFactory()
                factory.set_scheduler(self._butler.scheduler)
                if auth_manager:
                    factory.set_auth_manager(auth_manager)
                executor = AgentExecutor(factory=factory)
                gateway = CommunicationGateway(
                    executor=executor,
                    conversation_store=components.conversation_store,
                    recipient_registry=components.recipient_registry,
                    outbound_senders=components.outbound_senders,
                    max_conversation_history=30,
                )
                self._butler.set_gateway(gateway)

                # Give auth_manager access to gateway for sending
                # verification links via Telegram/Teams during re-auth.
                if auth_manager:
                    auth_manager._gateway = gateway

                logger.info(
                    "butler_daemon.gateway_configured",
                    channels=list(components.outbound_senders.keys()),
                )
        except Exception as exc:
            logger.warning("butler_daemon.gateway_setup_failed", error=str(exc))

    async def _setup_executor(self, config: dict[str, Any], *, auth_manager: Any = None) -> None:
        """Set up the agent executor and optionally the PersistentAgentService."""
        if self._butler is None:
            return

        try:
            from taskforce.application.executor import AgentExecutor
            from taskforce.application.factory import AgentFactory

            factory = AgentFactory()
            factory.set_scheduler(self._butler.scheduler)
            if auth_manager:
                factory.set_auth_manager(auth_manager)
            executor = AgentExecutor(factory=factory)
            self._butler.set_executor(executor)
            logger.info("butler_daemon.executor_configured")

            # Wire PersistentAgentService when enabled.
            if self._persistent_agent_enabled:
                self._agent_service = self._build_persistent_agent_service(executor, config)
                if self._agent_service:
                    self._butler.set_agent_service(self._agent_service)
                    logger.info("butler_daemon.persistent_agent_configured")
        except Exception as exc:
            logger.warning("butler_daemon.executor_setup_failed", error=str(exc))

    def _build_persistent_agent_service(
        self,
        executor: Any,
        config: dict[str, Any],
    ) -> Any:
        """Build PersistentAgentService with ConversationManager and AgentState."""
        try:
            from taskforce.application.conversation_manager import ConversationManager
            from taskforce.application.persistent_agent_service import (
                PersistentAgentService,
            )
            from taskforce.infrastructure.persistence.file_agent_state import (
                FileAgentState,
            )
            from taskforce.infrastructure.persistence.file_conversation_store import (
                FileConversationStore,
            )

            agent_state = FileAgentState(work_dir=self._work_dir)
            conv_store = FileConversationStore(work_dir=self._work_dir)
            conv_manager = ConversationManager(conv_store)

            queue_cfg = config.get("request_queue", {})
            return PersistentAgentService(
                executor=executor,
                agent_state=agent_state,
                conversation_manager=conv_manager,
                queue_max_size=queue_cfg.get("max_size", 100),
                drain_timeout=queue_cfg.get("drain_timeout", 30.0),
            )
        except Exception as exc:
            logger.warning("butler_daemon.persistent_agent_build_failed", error=str(exc))
            return None

    async def _setup_event_sources(self, config: dict[str, Any]) -> None:
        """Set up event sources from configuration via the EventSourceRegistry.

        The previous if/elif chain has been replaced by a single
        ``registry.create(type, config)`` call so adding a new source
        type only needs an entry in
        ``taskforce.infrastructure.event_sources.__init__`` (or any
        agent package that calls ``register_event_source`` at import
        time). Started sources are also published to the API layer's
        active-source registry so the generic
        ``POST /api/v1/events/{source_name}`` route can reach them.
        """
        if self._butler is None:
            return

        # Triggers framework-side auto-registration.
        import taskforce.infrastructure.event_sources  # noqa: F401
        from taskforce.application.event_source_registry import (
            get_event_source_registry,
        )

        registry = get_event_source_registry()
        sources_config = config.get("event_sources", [])

        for source_cfg in sources_config:
            source_type = source_cfg.get("type", "")
            if not source_type:
                logger.warning("butler_daemon.event_source_missing_type", config=source_cfg)
                continue
            if not registry.is_registered(source_type):
                logger.warning(
                    "butler_daemon.unknown_source_type",
                    source_type=source_type,
                    known=registry.list(),
                )
                continue

            cfg = {k: v for k, v in source_cfg.items() if k != "type"}
            try:
                source = registry.create(source_type, cfg)
            except Exception as exc:
                logger.warning(
                    "butler_daemon.event_source_build_failed",
                    source_type=source_type,
                    error=str(exc),
                )
                continue

            self._butler.add_event_source(source)
            logger.info(
                "butler_daemon.event_source_added",
                source_type=source_type,
                source_name=getattr(source, "source_name", source_type),
            )

            # Publish webhook-capable sources to the API layer so the
            # generic events route can dispatch HTTP deliveries to them.
            try:
                from taskforce.api.dependencies import register_active_event_source
                from taskforce.core.interfaces.event_source import (
                    WebhookCapableEventSource,
                )

                if isinstance(source, WebhookCapableEventSource):
                    register_active_event_source(source.source_name, source)
            except Exception:  # pragma: no cover — API package optional
                pass

    async def _setup_proactive_layer(self, config: dict[str, Any]) -> None:
        """Wire StandingGoalStore + GoalEvaluatorService + heartbeat task.

        Behaviour is opt-in via the ``proactive`` block in the butler
        profile YAML — when missing the daemon stays purely reactive
        (matching the pre-Phase-3 behaviour). When present the daemon:

        * Loads or creates a ``FileStandingGoalStore`` under the work dir.
        * Builds a ``GoalEvaluatorService`` whose ``submit`` callback
          enqueues missions on the persistent agent (or directly via the
          executor when no queue is wired).
        * Publishes both store + evaluator to the API layer so the REST
          CRUD and ``evaluate-now`` endpoints work.
        * Starts a background heartbeat task that calls
          ``evaluate_due_goals`` every ``heartbeat_minutes``.
        """
        proactive_cfg = config.get("proactive") or {}
        if not proactive_cfg.get("enabled", False):
            return

        try:
            from taskforce.application.goal_evaluator_service import (
                GoalDecision,
                GoalEvaluatorService,
            )
            from taskforce.infrastructure.persistence.file_standing_goal_store import (
                FileStandingGoalStore,
            )
        except Exception as exc:  # pragma: no cover — import-only failures
            logger.warning("butler_daemon.proactive_import_failed", error=str(exc))
            return

        store = FileStandingGoalStore(work_dir=self._work_dir)

        async def _submit(request: Any) -> Any:
            if self._agent_service is not None:
                return await self._agent_service.submit(request)
            # Fallback path when no PersistentAgentService is wired —
            # run the executor directly so single-agent setups still
            # benefit from proactive behaviour.
            from taskforce.application.executor import AgentExecutor

            executor = AgentExecutor()
            return await executor.execute_mission(
                mission=request.message,
                profile=self._profile,
                session_id=request.session_id or request.request_id,
            )

        async def _decide(goal: Any, now: Any) -> Any:
            # Default: always act. The mission sent to the queue is the
            # goal's own evaluation prompt (with ``$NOW`` substitution),
            # leaving the act-or-not decision to the agent itself —
            # which has the full conversation+memory context. Adopters
            # who want a separate cheap decision LLM can replace this
            # callback before ``daemon.start()`` returns.
            mission = goal.evaluation_prompt.replace("$NOW", now.isoformat())
            mission = mission.replace(
                "$LAST_EVALUATED_AT",
                goal.last_evaluated_at.isoformat() if goal.last_evaluated_at else "never",
            )
            return GoalDecision(act=True, mission=mission, rationale="due-by-cron")

        evaluator = GoalEvaluatorService(
            store=store,
            submit=_submit,
            decide=_decide,
        )

        # Publish both to the API layer.
        try:
            from taskforce.api.dependencies import (
                set_goal_evaluator,
                set_standing_goal_store,
            )

            set_standing_goal_store(store)
            set_goal_evaluator(evaluator)
        except Exception:  # pragma: no cover — API optional
            pass

        # Seed initial goals from YAML (idempotent — duplicates skipped).
        for raw in proactive_cfg.get("standing_goals", []) or []:
            try:
                from taskforce.core.domain.standing_goal import StandingGoal

                goal = StandingGoal.from_dict(raw)
                existing = await store.get(goal.goal_id)
                if existing is None:
                    await store.add(goal)
            except Exception as exc:
                logger.warning(
                    "butler_daemon.standing_goal_seed_failed",
                    error=str(exc),
                )

        heartbeat_minutes = float(proactive_cfg.get("heartbeat_minutes", 15.0))
        self._proactive_evaluator = evaluator
        self._proactive_task = asyncio.create_task(
            self._heartbeat_loop(evaluator, heartbeat_minutes),
            name="butler-proactive-heartbeat",
        )
        logger.info(
            "butler_daemon.proactive_layer_started",
            heartbeat_minutes=heartbeat_minutes,
            goals=len(await store.list()),
        )

    async def _heartbeat_loop(self, evaluator: Any, heartbeat_minutes: float) -> None:
        """Periodically evaluate every due standing goal.

        The loop sleeps after each tick so heartbeat frequency is the
        upper bound on goal-evaluation latency. Uses ``asyncio.sleep``
        and respects cancellation cleanly.
        """
        interval = max(1.0, heartbeat_minutes * 60.0)
        try:
            while self._running or not self._proactive_task.cancelled():
                try:
                    await evaluator.evaluate_due_goals()
                except Exception:
                    logger.exception("butler_daemon.proactive_tick_failed")
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass

    async def _load_rules(self, config: dict[str, Any]) -> None:
        """Load trigger rules from configuration."""
        if self._butler is None:
            return

        rules_config = config.get("rules", [])
        for rule_cfg in rules_config:
            try:
                await self._butler.add_rule_from_config(rule_cfg)
            except Exception as exc:
                logger.warning(
                    "butler_daemon.rule_load_failed",
                    rule_name=rule_cfg.get("name", "?"),
                    error=str(exc),
                )

    async def _write_status_loop(self) -> None:
        """Periodically write butler status to disk.

        Each iteration also refreshes :attr:`last_heartbeat` so a
        supervising ``DaemonSupervisor`` can detect when the asyncio
        event loop itself has stalled (see issue #156).
        """
        try:
            while self._running:
                self._last_heartbeat = utc_now()
                await self._write_status()
                await asyncio.sleep(30)
        except asyncio.CancelledError:
            pass

    async def _write_status(self) -> None:
        """Write current status to a JSON file."""
        if not self._butler:
            return

        try:
            status = await self._butler.get_status()
            status["updated_at"] = utc_now().isoformat()
            status["profile"] = self._profile
            if self._role_override:
                status["role"] = self._role_override

            # Include persistent agent status when available.
            if self._agent_service:
                agent_status = await self._agent_service.status()
                status["persistent_agent"] = {
                    "running": agent_status.running,
                    "queue_size": agent_status.queue_size,
                    "active_conversations": agent_status.active_conversations,
                    "last_activity": (
                        agent_status.last_activity.isoformat()
                        if agent_status.last_activity
                        else None
                    ),
                }

            self._status_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._status_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(status, indent=2, default=str), encoding="utf-8")
            tmp.rename(self._status_path)
        except Exception as exc:
            logger.warning("butler_daemon.status_write_failed", error=str(exc))
