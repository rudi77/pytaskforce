"""
Run Registry
============

In-memory registry of executions currently running on this server. The
management UI's Active-Runs panel polls or streams from here.

Records are intentionally lightweight (no agent reference, no execution
context) so cancelling them stays a separate concern owned by
``AgentExecutor.interrupt(session_id)``.
"""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ActiveRun:
    session_id: str
    started_at: datetime
    profile: str | None = None
    agent_id: str | None = None
    conversation_id: str | None = None
    mission_preview: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    last_event: str = ""
    last_event_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["started_at"] = self.started_at.isoformat()
        data["last_event_at"] = self.last_event_at.isoformat()
        data["total_tokens"] = self.prompt_tokens + self.completion_tokens
        return data


class RunRegistry:
    """Process-local registry of in-flight executions."""

    def __init__(self) -> None:
        self._runs: dict[str, ActiveRun] = {}
        self._lock = threading.Lock()
        # Listeners are stored as a list (not a set) so non-hashable
        # closures and lambdas can subscribe safely. The current SSE
        # endpoint polls instead of subscribing, so this stays empty in
        # practice — but the API is published, so make it correct.
        self._listeners: list[Any] = []

    # ------------------------------------------------------------------
    # Mutators
    # ------------------------------------------------------------------

    def register(
        self,
        session_id: str,
        *,
        profile: str | None = None,
        agent_id: str | None = None,
        conversation_id: str | None = None,
        mission: str = "",
    ) -> ActiveRun:
        run = ActiveRun(
            session_id=session_id,
            started_at=datetime.now(UTC),
            profile=profile,
            agent_id=agent_id,
            conversation_id=conversation_id,
            mission_preview=(mission or "")[:200],
            last_event="started",
        )
        with self._lock:
            self._runs[session_id] = run
        logger.debug("run_registered", session_id=session_id, profile=profile)
        self._notify()
        return run

    def update_tokens(
        self,
        session_id: str,
        *,
        prompt_delta: int = 0,
        completion_delta: int = 0,
        cost_delta: float = 0.0,
    ) -> None:
        with self._lock:
            run = self._runs.get(session_id)
            if not run:
                return
            self._runs[session_id] = replace(
                run,
                prompt_tokens=run.prompt_tokens + max(0, int(prompt_delta or 0)),
                completion_tokens=run.completion_tokens + max(0, int(completion_delta or 0)),
                cost_usd=run.cost_usd + max(0.0, float(cost_delta or 0.0)),
                last_event="llm_call",
                last_event_at=datetime.now(UTC),
            )
        self._notify()

    def mark_event(self, session_id: str, event: str) -> None:
        with self._lock:
            run = self._runs.get(session_id)
            if not run:
                return
            self._runs[session_id] = replace(
                run, last_event=event, last_event_at=datetime.now(UTC)
            )
        self._notify()

    def unregister(self, session_id: str) -> None:
        with self._lock:
            self._runs.pop(session_id, None)
        logger.debug("run_unregistered", session_id=session_id)
        self._notify()

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def list_active(self) -> list[ActiveRun]:
        with self._lock:
            return sorted(self._runs.values(), key=lambda r: r.started_at)

    def snapshot_dicts(self) -> list[dict[str, Any]]:
        return [run.to_dict() for run in self.list_active()]

    # ------------------------------------------------------------------
    # Subscriptions (used by the SSE stream endpoint)
    # ------------------------------------------------------------------

    def subscribe(self, listener: Any) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unsubscribe(self, listener: Any) -> None:
        try:
            self._listeners.remove(listener)
        except ValueError:
            pass

    def _notify(self) -> None:
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:  # noqa: BLE001
                logger.debug("run_registry_listener_failed", exc_info=True)


_registry: RunRegistry | None = None


def get_run_registry() -> RunRegistry:
    global _registry
    if _registry is None:
        _registry = RunRegistry()
    return _registry


def reset_run_registry() -> None:
    global _registry
    _registry = None


__all__ = [
    "ActiveRun",
    "RunRegistry",
    "get_run_registry",
    "reset_run_registry",
]
