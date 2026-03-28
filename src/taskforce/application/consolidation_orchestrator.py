"""Consolidation Orchestrator - Extracted from AgentExecutor.

Manages the lifecycle of experience tracking and memory consolidation
after agent execution. Handles lazy initialization of components,
throttling of expensive LLM consolidation, and lightweight memory
decay/reinforcement.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import structlog

from taskforce.core.domain.agent import Agent
from taskforce.core.domain.enums import ExecutionStatus

logger = structlog.get_logger(__name__)


class ConsolidationOrchestrator:
    """Orchestrates experience tracking and memory consolidation.

    Manages throttling state for both LLM-based (expensive) and
    lightweight (cheap) consolidation cycles.
    """

    def __init__(
        self,
        experience_tracker: Any | None = None,
        consolidation_service: Any | None = None,
    ) -> None:
        self._experience_tracker = experience_tracker
        self._consolidation_service = consolidation_service
        self._initialized = experience_tracker is not None
        self._logger = logger.bind(component="consolidation_orchestrator")
        # Throttle: LLM consolidation.
        self._last_llm_consolidation: datetime | None = None
        self._requests_since_consolidation: int = 0
        self._consolidation_interval_minutes: int = 5
        self._consolidation_interval_requests: int = 10
        # Throttle: lightweight association building.
        self._requests_since_associations: int = 0
        self._association_interval_requests: int = 10

    @property
    def experience_tracker(self) -> Any | None:
        """The current experience tracker (may be None)."""
        return self._experience_tracker

    @property
    def consolidation_service(self) -> Any | None:
        """The current consolidation service (may be None)."""
        return self._consolidation_service

    def ensure_components(
        self,
        profile: str,
        config: dict[str, Any] | None = None,
        profile_loader: Any | None = None,
    ) -> None:
        """Lazy-initialize consolidation components from profile config.

        Only runs once. If ``experience_tracker`` was already injected
        via ``__init__``, this is a no-op.

        Args:
            profile: Profile name to load consolidation config from.
            config: Optional pre-loaded config dict.
            profile_loader: Optional profile loader for loading config by name.
        """
        if self._initialized:
            return
        self._initialized = True

        try:
            from taskforce.application.consolidation_service import (
                build_consolidation_components,
            )

            if config is None and profile_loader is not None:
                config = profile_loader.load(profile)
            if config is None:
                return

            consol_config = config.get("consolidation", {})
            if not consol_config.get("enabled", False) and not consol_config.get(
                "auto_capture", True
            ):
                return

            from taskforce.application.infrastructure_builder import (
                InfrastructureBuilder,
            )

            llm_provider = InfrastructureBuilder().build_llm_provider(config)
            tracker, service = build_consolidation_components(config, llm_provider)
            if tracker is not None:
                self._experience_tracker = tracker
            if service is not None:
                self._consolidation_service = service
        except Exception:
            self._logger.debug(
                "consolidation.init_skipped",
                reason="failed to build components",
                profile=profile,
            )

    def start_session(
        self, session_id: str, mission: str, profile: str
    ) -> None:
        """Start experience tracking for a session."""
        if self._experience_tracker is not None:
            self._experience_tracker.start_session(session_id, mission, profile)

    def observe(self, event: Any) -> None:
        """Observe a stream event for experience tracking."""
        if self._experience_tracker is not None:
            self._experience_tracker.observe(event)

    async def post_execution(
        self,
        session_id: str,
        agent: Agent | None,
        mission: str,
        execution_failed: bool,
    ) -> None:
        """Run post-execution consolidation hooks.

        Handles both LLM-based and lightweight consolidation in background tasks.
        """
        # Finalize experience tracking.
        if self._experience_tracker is not None:
            status = (
                ExecutionStatus.FAILED.value
                if execution_failed
                else ExecutionStatus.COMPLETED.value
            )
            experience = await self._experience_tracker.end_session(status)
            if experience and self._consolidation_service is not None:
                self._requests_since_consolidation += 1
                if self._should_run_llm_consolidation():
                    self._last_llm_consolidation = datetime.now()
                    self._requests_since_consolidation = 0
                    asyncio.create_task(
                        self._consolidation_service.post_execution_hook(
                            session_id, experience
                        ),
                        name="consolidation-llm",
                    )

        # Lightweight (no-LLM) memory consolidation.
        if agent and not execution_failed:
            self._requests_since_associations += 1
            run_associations = (
                self._requests_since_associations
                >= self._association_interval_requests
            )
            if run_associations:
                self._requests_since_associations = 0
            asyncio.create_task(
                self._run_lightweight_consolidation(
                    agent, mission, build_associations=run_associations
                ),
                name="consolidation-lightweight",
            )

    def _should_run_llm_consolidation(self) -> bool:
        """Check whether enough time or requests have passed."""
        if self._last_llm_consolidation is None:
            return True
        elapsed = (
            datetime.now() - self._last_llm_consolidation
        ).total_seconds()
        if elapsed >= self._consolidation_interval_minutes * 60:
            return True
        if (
            self._requests_since_consolidation
            >= self._consolidation_interval_requests
        ):
            return True
        return False

    async def _run_lightweight_consolidation(
        self,
        agent: Agent,
        mission: str,
        *,
        build_associations: bool = False,
    ) -> None:
        """Run lightweight memory consolidation after a successful session.

        Failures are logged but never propagated.
        """
        memory_store = getattr(agent, "_memory_store", None)
        if not memory_store:
            return

        try:
            from taskforce.infrastructure.memory.lightweight_consolidation import (
                run_lightweight_consolidation,
            )

            keywords = {w.lower() for w in mission.split() if len(w) > 2}
            embedder = None
            if build_associations:
                embedder = getattr(memory_store, "_embedder", None)

            result = await run_lightweight_consolidation(
                store=memory_store,
                session_keywords=keywords if keywords else None,
                embedding_provider=embedder,
                build_associations=build_associations,
            )
            self._logger.debug(
                "lightweight_consolidation.done",
                archived=result.archived,
                strengthened=result.strengthened,
                associations=result.associations_created,
                duration_ms=result.duration_ms,
            )
        except Exception:
            self._logger.debug(
                "lightweight_consolidation.skipped",
                reason="error during consolidation",
            )
