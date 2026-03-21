"""Non-invasive observer that captures agent execution experiences.

The ``ExperienceTracker`` attaches to the ``StreamEvent`` flow in the
executor and builds a ``SessionExperience`` record without affecting
the agent's execution in any way.  The ``observe()`` method is
intentionally synchronous and lightweight; persistence happens only
at ``end_session()``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from taskforce.core.domain.enums import EventType
from taskforce.core.domain.experience import (
    ExperienceEvent,
    SessionExperience,
    ToolCallExperience,
    truncate_output,
)
from taskforce.core.domain.models import StreamEvent
from taskforce.core.interfaces.experience import ExperienceStoreProtocol

logger = structlog.get_logger(__name__)


class ExperienceTracker:
    """Observes agent StreamEvents and assembles a SessionExperience.

    Usage::

        tracker = ExperienceTracker(store)
        tracker.start_session("sess-1", "Analyze data", "dev")
        for event in agent_stream:
            tracker.observe(event)
        experience = await tracker.end_session("completed")

    Args:
        store: Persistence backend for saving completed experiences.
    """

    def __init__(self, store: ExperienceStoreProtocol) -> None:
        self._store = store
        self._current: SessionExperience | None = None
        self._pending_tool_calls: dict[str, dict[str, Any]] = {}
        self._step = 0

    def start_session(
        self,
        session_id: str,
        mission: str,
        profile: str,
    ) -> None:
        """Initialize tracking for a new agent session.

        Args:
            session_id: Unique session identifier.
            mission: The mission being executed.
            profile: Profile name used.
        """
        self._current = SessionExperience(
            session_id=session_id,
            profile=profile,
            mission=mission,
            started_at=datetime.now(UTC),
        )
        self._pending_tool_calls = {}
        self._step = 0

    def observe(self, event: StreamEvent) -> None:
        """Process a single stream event (sync, lightweight).

        This method MUST remain synchronous and avoid I/O to keep the
        streaming loop fast.  Heavy processing is deferred to
        ``end_session()``.

        Args:
            event: The stream event from agent execution.
        """
        if self._current is None:
            return

        event_type = (
            event.event_type.value
            if isinstance(event.event_type, EventType)
            else str(event.event_type)
        )

        if event_type == EventType.STEP_START.value:
            self._handle_step_start(event)
        elif event_type == EventType.TOOL_CALL.value:
            self._handle_tool_call(event)
        elif event_type == EventType.TOOL_RESULT.value:
            self._handle_tool_result(event)
        elif event_type == EventType.PLAN_UPDATED.value:
            self._handle_plan_updated(event)
        elif event_type == EventType.ASK_USER.value:
            self._handle_ask_user(event)
        elif event_type == EventType.TOKEN_USAGE.value:
            self._handle_token_usage(event)
        elif event_type == EventType.FINAL_ANSWER.value:
            self._handle_final_answer(event)
        elif event_type == EventType.ERROR.value:
            self._handle_error(event)

        # Store a lightweight event summary for all event types
        self._current.events.append(
            ExperienceEvent(
                timestamp=event.timestamp,
                event_type=event_type,
                data=self._summarize_event_data(event.data),
                step=self._step,
            )
        )

    async def end_session(self, status: str = "completed") -> SessionExperience | None:
        """Finalize and persist the current session experience.

        Args:
            status: Final execution status (e.g. ``completed``, ``failed``).

        Returns:
            The completed ``SessionExperience``, or ``None`` if no session
            was active.
        """
        if self._current is None:
            return None

        experience = self._current
        experience.ended_at = datetime.now(UTC)
        experience.metadata["status"] = status
        self._current = None
        self._pending_tool_calls = {}

        try:
            await self._store.save_experience(experience)
            logger.info(
                "experience.saved",
                session_id=experience.session_id,
                tool_calls=len(experience.tool_calls),
                steps=experience.total_steps,
                tokens=experience.total_tokens,
            )
        except Exception:
            logger.exception(
                "experience.save_failed",
                session_id=experience.session_id,
            )

        return experience

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _handle_step_start(self, event: StreamEvent) -> None:
        self._step = event.data.get("step", self._step + 1)
        self._current.total_steps = max(self._current.total_steps, self._step)

    def _handle_tool_call(self, event: StreamEvent) -> None:
        tool_name = event.data.get("tool", event.data.get("tool_name", "unknown"))
        call_id = event.data.get("tool_call_id", "")
        arguments = event.data.get("arguments", event.data.get("params", {}))

        self._pending_tool_calls[call_id] = {
            "tool_name": tool_name,
            "arguments": arguments,
            "started_at": datetime.now(UTC),
        }

    def _handle_tool_result(self, event: StreamEvent) -> None:
        call_id = event.data.get("tool_call_id", "")
        pending = self._pending_tool_calls.pop(call_id, None)

        tool_name = (
            pending["tool_name"]
            if pending
            else event.data.get("tool", event.data.get("tool_name", "unknown"))
        )
        arguments = pending["arguments"] if pending else {}

        duration_ms = 0
        if pending and "started_at" in pending:
            delta = datetime.now(UTC) - pending["started_at"]
            duration_ms = int(delta.total_seconds() * 1000)

        raw_output = str(event.data.get("result", event.data.get("output", "")))
        success = event.data.get("success", True)
        error = event.data.get("error")

        self._current.tool_calls.append(
            ToolCallExperience(
                tool_name=tool_name,
                arguments=arguments,
                success=bool(success),
                output_summary=truncate_output(raw_output),
                duration_ms=duration_ms,
                error=str(error) if error else None,
            )
        )

    def _handle_plan_updated(self, event: StreamEvent) -> None:
        self._current.plan_updates.append(
            {
                "step": self._step,
                "action": event.data.get("action", ""),
                "summary": truncate_output(str(event.data.get("plan", ""))),
            }
        )

    def _handle_ask_user(self, event: StreamEvent) -> None:
        self._current.user_interactions.append(
            {
                "step": self._step,
                "question": event.data.get("question", ""),
            }
        )

    def _handle_token_usage(self, event: StreamEvent) -> None:
        self._current.total_tokens += event.data.get("total_tokens", 0)

    def _handle_final_answer(self, event: StreamEvent) -> None:
        answer = event.data.get("answer", event.data.get("content", ""))
        self._current.final_answer = truncate_output(str(answer))

    def _handle_error(self, event: StreamEvent) -> None:
        error_msg = event.data.get("error", event.data.get("message", "unknown error"))
        self._current.errors.append(str(error_msg))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _summarize_event_data(data: dict[str, Any]) -> dict[str, Any]:
        """Create a lightweight summary of event data.

        Keeps only essential keys and truncates large values to avoid
        bloating the experience record.
        """
        summary: dict[str, Any] = {}
        keep_keys = {"tool", "tool_name", "step", "action", "status", "error", "success"}
        for key in keep_keys:
            if key in data:
                value = data[key]
                if isinstance(value, str) and len(value) > 200:
                    value = value[:200] + "..."
                summary[key] = value
        return summary
