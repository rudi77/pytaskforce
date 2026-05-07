"""Mission lifecycle hook protocol.

Lets out-of-tree code (typically the enterprise plugin) observe when
a mission starts and finishes, without coupling the framework to any
particular auditing or telemetry implementation.

Hooks are registered via
``taskforce.application.infrastructure_overrides.set_mission_lifecycle_hook``
and called by ``AgentExecutor`` at the boundaries of
``execute_mission_streaming``. Hook calls are best-effort — exceptions
in a hook never break the calling mission.

Hooks receive only the data the framework already produces (mission
text, session_id, profile, agent_id, success, optional error). Hooks
that need tenant/user context read it themselves from the auth
ContextVars (the framework stays tenant-unaware per ADR-022).
"""

from __future__ import annotations

from typing import Protocol


class MissionLifecycleHookProtocol(Protocol):
    """Out-of-tree observer of mission start/end events."""

    async def on_mission_started(
        self,
        *,
        mission: str,
        session_id: str,
        profile: str,
        agent_id: str | None = None,
    ) -> None:
        """Called once per mission, just after the started progress update."""
        ...

    async def on_mission_completed(
        self,
        *,
        mission: str,
        session_id: str,
        profile: str,
        agent_id: str | None = None,
        success: bool,
        error: str | None = None,
        duration_seconds: float | None = None,
    ) -> None:
        """Called once per mission, regardless of outcome.

        ``success=True`` for clean completion, ``False`` for
        cancellation or unhandled exception. ``error`` carries the
        exception's stringified message when available.
        """
        ...
