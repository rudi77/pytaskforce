"""Butler daemon that orchestrates the event-driven agent lifecycle.

The daemon is the top-level process that:
1. Loads butler profile configuration
2. Builds all infrastructure components
3. Starts the ButlerService with event sources, scheduler, and rules
4. Writes periodic status files for the CLI to read
5. Handles graceful shutdown
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import structlog

from taskforce.application.butler_service import ButlerService
from taskforce.core.utils.time import utc_now

logger = structlog.get_logger(__name__)


class ButlerDaemon:
    """Top-level butler daemon process.

    Initializes and manages all butler components based on
    the butler profile YAML configuration.
    """

    def __init__(
        self,
        profile: str = "butler",
        work_dir: str = ".taskforce",
    ) -> None:
        self._profile = profile
        self._work_dir = work_dir
        self._butler: ButlerService | None = None
        self._running = False
        self._status_task: asyncio.Task[None] | None = None
        self._status_path = Path(work_dir) / "butler" / "status.json"

    @property
    def is_running(self) -> bool:
        """Whether the daemon is active."""
        return self._running

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

        # Try to wire up communication gateway
        await self._setup_gateway(config)

        # Try to wire up executor
        await self._setup_executor(config)

        # Set up event sources
        await self._setup_event_sources(config)

        # Load rules from config
        await self._load_rules(config)

        # Start the service
        await self._butler.start()
        self._running = True

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

        if self._butler:
            await self._butler.stop()

        self._running = False

        # Write final status
        await self._write_status()

        logger.info("butler_daemon.stopped")

    def _load_config(self) -> dict[str, Any]:
        """Load butler profile configuration."""
        from taskforce.application.factory import AgentFactory

        factory = AgentFactory()
        config_path = factory.config_dir / f"{self._profile}.yaml"

        if config_path.exists():
            import yaml

            with open(config_path) as f:
                return yaml.safe_load(f) or {}

        logger.warning(
            "butler_daemon.config_not_found",
            profile=self._profile,
            path=str(config_path),
        )
        return {}

    async def _setup_gateway(self, config: dict[str, Any]) -> None:
        """Set up the communication gateway if configured."""
        try:
            from taskforce.application.executor import AgentExecutor
            from taskforce.application.gateway import CommunicationGateway
            from taskforce_extensions.infrastructure.communication.gateway_registry import (
                build_gateway_components,
            )

            components = build_gateway_components(work_dir=self._work_dir)
            if components.outbound_senders:
                executor = AgentExecutor()
                gateway = CommunicationGateway(
                    executor=executor,
                    conversation_store=components.conversation_store,
                    recipient_registry=components.recipient_registry,
                    outbound_senders=components.outbound_senders,
                    inbound_adapters=components.inbound_adapters,
                )
                self._butler.set_gateway(gateway)
                logger.info(
                    "butler_daemon.gateway_configured",
                    channels=list(components.outbound_senders.keys()),
                )
        except Exception as exc:
            logger.warning("butler_daemon.gateway_setup_failed", error=str(exc))

    async def _setup_executor(self, config: dict[str, Any]) -> None:
        """Set up the agent executor."""
        try:
            from taskforce.application.executor import AgentExecutor

            executor = AgentExecutor()
            self._butler.set_executor(executor)
            logger.info("butler_daemon.executor_configured")
        except Exception as exc:
            logger.warning("butler_daemon.executor_setup_failed", error=str(exc))

    async def _setup_event_sources(self, config: dict[str, Any]) -> None:
        """Set up event sources from configuration."""
        sources_config = config.get("event_sources", [])

        for source_cfg in sources_config:
            source_type = source_cfg.get("type", "")

            if source_type == "calendar":
                try:
                    from taskforce.infrastructure.event_sources.calendar_source import (
                        CalendarEventSource,
                    )

                    source = CalendarEventSource(
                        poll_interval_seconds=source_cfg.get("poll_interval_minutes", 5) * 60,
                        lookahead_minutes=source_cfg.get("lookahead_minutes", 60),
                        calendar_id=source_cfg.get("calendar_id", "primary"),
                        credentials_file=source_cfg.get("credentials_file"),
                    )
                    self._butler.add_event_source(source)
                    logger.info("butler_daemon.calendar_source_added")
                except Exception as exc:
                    logger.warning("butler_daemon.calendar_source_failed", error=str(exc))

            elif source_type == "webhook":
                try:
                    from taskforce.infrastructure.event_sources.webhook_source import (
                        WebhookEventSource,
                    )

                    source = WebhookEventSource()
                    self._butler.add_event_source(source)
                    logger.info("butler_daemon.webhook_source_added")
                except Exception as exc:
                    logger.warning("butler_daemon.webhook_source_failed", error=str(exc))

            else:
                logger.warning("butler_daemon.unknown_source_type", source_type=source_type)

    async def _load_rules(self, config: dict[str, Any]) -> None:
        """Load trigger rules from configuration."""
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
        """Periodically write butler status to disk."""
        try:
            while self._running:
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

            self._status_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._status_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(status, indent=2, default=str))
            tmp.rename(self._status_path)
        except Exception as exc:
            logger.warning("butler_daemon.status_write_failed", error=str(exc))
