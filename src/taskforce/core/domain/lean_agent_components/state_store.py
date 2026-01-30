"""State persistence helpers for Agent."""

from __future__ import annotations

from typing import Any

from taskforce.core.interfaces.logging import LoggerProtocol
from taskforce.core.interfaces.runtime import AgentRuntimeTrackerProtocol
from taskforce.core.interfaces.state import StateManagerProtocol
from taskforce.core.tools.planner_tool import PlannerTool


class LeanAgentStateStore:
    """Persist Agent state, including planner state."""

    def __init__(
        self,
        *,
        state_manager: StateManagerProtocol,
        logger: LoggerProtocol,
        runtime_tracker: AgentRuntimeTrackerProtocol | None = None,
    ) -> None:
        self._state_manager = state_manager
        self._logger = logger
        self._runtime_tracker = runtime_tracker

    async def save(
        self,
        *,
        session_id: str,
        state: dict[str, Any],
        planner: PlannerTool | None,
    ) -> None:
        """Save state including PlannerTool state when available."""
        if planner:
            state["planner_state"] = planner.get_state()
        await self._state_manager.save_state(session_id, state)
        if self._runtime_tracker:
            await self._runtime_tracker.record_checkpoint(session_id, state)
        self._logger.debug("state_saved", session_id=session_id)
