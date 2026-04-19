"""Progress Update Builder - Extracted from AgentExecutor.

Pure data transformations for converting agent execution events
into ProgressUpdate objects for CLI/API consumers.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from taskforce.application.executor import ProgressUpdate
from taskforce.core.domain.enums import EventType, ExecutionStatus
from taskforce.core.domain.models import ExecutionResult, StreamEvent


def build_started_update(
    mission: str,
    session_id: str,
    profile: str,
    agent_id: str | None,
    plugin_path: str | None,
) -> ProgressUpdate:
    """Build the initial STARTED progress update."""
    return ProgressUpdate(
        timestamp=datetime.now(),
        event_type=EventType.STARTED,
        message=f"Starting mission: {mission[:80]}",
        details={
            "session_id": session_id,
            "profile": profile,
            "agent_id": agent_id,
            "plugin_path": plugin_path,
        },
    )


def stream_event_to_progress_update(event: StreamEvent) -> ProgressUpdate:
    """Convert StreamEvent to ProgressUpdate for API consumers.

    Maps Agent StreamEvent types to human-readable messages
    for CLI and API streaming consumers.
    """
    message_map = {
        EventType.STEP_START.value: lambda d: f"Step {d.get('step', '?')} starting...",
        EventType.LLM_TOKEN.value: lambda d: d.get("content", ""),
        EventType.TOOL_CALL.value: lambda d: f"Calling: {d.get('tool', 'unknown')}",
        EventType.TOOL_RESULT.value: lambda d: (
            f"{'OK' if d.get('success') else 'FAIL'} "
            f"{d.get('tool', 'unknown')}: {str(d.get('output', ''))[:50]}"
        ),
        EventType.ASK_USER.value: lambda d: (
            f"Question: {d.get('question', 'User input required')}"
        ),
        EventType.PLAN_UPDATED.value: lambda d: (f"Plan updated ({d.get('action', 'unknown')})"),
        EventType.TOKEN_USAGE.value: lambda d: f"Tokens: {d.get('total_tokens', 0)}",
        EventType.FINAL_ANSWER.value: lambda d: d.get("content", ""),
        EventType.COMPLETE.value: lambda d: (
            f"Execution completed. Status: {d.get('status', 'unknown')}"
        ),
        EventType.ERROR.value: lambda d: f"Error: {d.get('message', 'unknown')}",
        EventType.INTERRUPTED.value: lambda d: (
            f"Execution paused ({d.get('reason', 'user_requested')})."
        ),
    }

    event_type_value = (
        event.event_type.value if isinstance(event.event_type, EventType) else event.event_type
    )
    message_fn = message_map.get(event_type_value, lambda d: str(d))

    return ProgressUpdate(
        timestamp=event.timestamp,
        event_type=event.event_type,
        message=message_fn(event.data),
        details=event.data,
    )


def build_completion_update(result: ExecutionResult) -> ProgressUpdate:
    """Build the final COMPLETE progress update from an execution result."""
    status_value = result.status_value if hasattr(result, "status_value") else result.status
    return ProgressUpdate(
        timestamp=datetime.now(),
        event_type=EventType.COMPLETE,
        message=result.final_message,
        details={
            "status": status_value,
            "session_id": result.session_id,
            "todolist_id": result.todolist_id,
        },
    )


async def yield_history_updates(
    result: ExecutionResult,
) -> AsyncIterator[ProgressUpdate]:
    """Yield ProgressUpdate events from a completed execution result.

    Converts execution_history entries into streaming-compatible
    progress updates, followed by token usage and a final COMPLETE event.
    """
    for event in result.execution_history:
        update = _history_entry_to_update(event)
        if update is not None:
            yield update

    usage = result.token_usage
    usage_dict = usage.to_dict() if hasattr(usage, "to_dict") else usage
    if usage_dict and usage_dict.get("total_tokens", 0) > 0:
        yield ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.TOKEN_USAGE,
            message=f"Tokens: {usage_dict.get('total_tokens', 0)}",
            details=usage_dict,
        )

    yield build_completion_update(result)


def _history_entry_to_update(event: Any) -> ProgressUpdate | None:
    """Convert a single execution history entry to a ProgressUpdate."""
    event_type_str, step, data = _parse_history_event(event)

    if event_type_str == "thought":
        rationale = data.get("rationale", "") if isinstance(data, dict) else ""
        return ProgressUpdate(
            timestamp=datetime.now(),
            event_type="thought",
            message=f"Step {step}: {rationale[:80]}",
            details=data,
        )

    if event_type_str == "observation":
        return _build_observation_update(step, data)

    return None


def _parse_history_event(event: Any) -> tuple[str, str | int, dict[str, Any]]:
    """Parse a history event into its type, step, and data components."""
    if isinstance(event, dict):
        event_type_str = event.get("type", "unknown")
        step = event.get("step", "?")
        data: dict[str, Any] = event.get("data", {})
    else:
        et = event.event_type
        event_type_str = et.value if isinstance(et, EventType) else str(et)
        step = "?"
        data = event.data
    return event_type_str, step, data


def _build_observation_update(step: str | int, data: dict[str, Any]) -> ProgressUpdate:
    """Build a ProgressUpdate for an observation event."""
    success = data.get("success", False) if isinstance(data, dict) else False
    obs_status = ExecutionStatus.COMPLETED.value if success else ExecutionStatus.FAILED.value
    return ProgressUpdate(
        timestamp=datetime.now(),
        event_type="observation",
        message=f"Step {step}: {obs_status}",
        details=data,
    )
