"""
Run Trace Store
===============

In-memory ring-buffer of streaming events per session. The management UI's
run drilldown reads this to render the ReAct trace (thoughts, tool calls,
tool results, final answer) for a finished or in-flight execution.

Storage is process-local, lossy (oldest sessions get evicted), and
intentionally separate from ``RunRegistry`` so the active-runs panel can
keep its lightweight semantics.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Per-session event cap. Long missions can produce thousands of llm_token
# events; the trace view only needs structural events, so we keep a generous
# but bounded window per session.
_DEFAULT_MAX_EVENTS_PER_SESSION = 2_000

# How many sessions to keep in total (LRU-evict the oldest).
_DEFAULT_MAX_SESSIONS = 50


@dataclass
class TraceEvent:
    timestamp: datetime
    event_type: str
    message: str = ""
    details: dict[str, Any] | None = None
    step: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "message": self.message,
            "details": self.details,
            "step": self.step,
        }


@dataclass
class _SessionTrace:
    session_id: str
    started_at: datetime
    profile: str | None = None
    agent_id: str | None = None
    mission: str = ""
    events: list[TraceEvent] = field(default_factory=list)
    finished: bool = False
    final_status: str | None = None
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost_usd: float = 0.0


class RunTraceStore:
    """LRU-bounded recorder of structural events per session."""

    def __init__(
        self,
        max_sessions: int = _DEFAULT_MAX_SESSIONS,
        max_events_per_session: int = _DEFAULT_MAX_EVENTS_PER_SESSION,
    ) -> None:
        self._sessions: OrderedDict[str, _SessionTrace] = OrderedDict()
        self._lock = threading.Lock()
        self._max_sessions = max_sessions
        self._max_events = max_events_per_session

    def start(
        self,
        session_id: str,
        *,
        mission: str = "",
        profile: str | None = None,
        agent_id: str | None = None,
    ) -> None:
        with self._lock:
            self._sessions[session_id] = _SessionTrace(
                session_id=session_id,
                started_at=datetime.now(UTC),
                profile=profile,
                agent_id=agent_id,
                mission=mission,
            )
            self._sessions.move_to_end(session_id)
            self._evict_locked()

    def record(
        self,
        session_id: str,
        *,
        event_type: str,
        message: str = "",
        details: dict[str, Any] | None = None,
        step: int | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        with self._lock:
            trace = self._sessions.get(session_id)
            if trace is None:
                trace = _SessionTrace(
                    session_id=session_id, started_at=datetime.now(UTC)
                )
                self._sessions[session_id] = trace
            trace.events.append(
                TraceEvent(
                    timestamp=datetime.now(UTC),
                    event_type=event_type,
                    message=message or "",
                    details=details,
                    step=step,
                )
            )
            if len(trace.events) > self._max_events:
                # Drop the oldest events but preserve the first (started)
                # so the trace still has a sensible head.
                excess = len(trace.events) - self._max_events
                trace.events = [trace.events[0]] + trace.events[excess + 1 :]
            trace.total_prompt_tokens += max(0, int(prompt_tokens or 0))
            trace.total_completion_tokens += max(0, int(completion_tokens or 0))
            trace.total_cost_usd += max(0.0, float(cost_usd or 0.0))
            self._sessions.move_to_end(session_id)
            self._evict_locked()

    def finish(self, session_id: str, *, final_status: str | None = None) -> None:
        with self._lock:
            trace = self._sessions.get(session_id)
            if trace is None:
                return
            trace.finished = True
            trace.final_status = final_status
            self._sessions.move_to_end(session_id)

    def get(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            trace = self._sessions.get(session_id)
            if trace is None:
                return None
            return {
                "session_id": trace.session_id,
                "started_at": trace.started_at.isoformat(),
                "profile": trace.profile,
                "agent_id": trace.agent_id,
                "mission": trace.mission,
                "finished": trace.finished,
                "final_status": trace.final_status,
                "total_prompt_tokens": trace.total_prompt_tokens,
                "total_completion_tokens": trace.total_completion_tokens,
                "total_cost_usd": trace.total_cost_usd,
                "events": [event.to_dict() for event in trace.events],
            }

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "session_id": trace.session_id,
                    "started_at": trace.started_at.isoformat(),
                    "profile": trace.profile,
                    "agent_id": trace.agent_id,
                    "mission_preview": trace.mission[:200],
                    "finished": trace.finished,
                    "final_status": trace.final_status,
                    "event_count": len(trace.events),
                    "total_prompt_tokens": trace.total_prompt_tokens,
                    "total_completion_tokens": trace.total_completion_tokens,
                    "total_cost_usd": trace.total_cost_usd,
                }
                for trace in reversed(self._sessions.values())
            ]

    def _evict_locked(self) -> None:
        while len(self._sessions) > self._max_sessions:
            evicted, _ = self._sessions.popitem(last=False)
            logger.debug("run_trace_evicted", session_id=evicted)


_store: RunTraceStore | None = None


def get_run_trace_store() -> RunTraceStore:
    global _store
    if _store is None:
        _store = RunTraceStore()
    return _store


def reset_run_trace_store() -> None:
    global _store
    _store = None
