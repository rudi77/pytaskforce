"""Domain models for the per-conversation action log (issue #157).

The action log captures tool-call activity for each user turn so that the
Communication Gateway can offer a ``/actions`` slash command and an
optional ``actions_summary: footer`` mode that surface tool transparency
to channel users.

Three small dataclasses model the log:

* :class:`ActionRecord` — a single tool invocation with success state,
  arg summary, optional error message and duration.
* :class:`ActionLog` — the ordered list of records for one user turn.
* :class:`TurnRecorder` — a stateful helper that consumes streaming
  ``ProgressUpdate`` / ``StreamEvent`` events and emits the final
  :class:`ActionLog`. It tolerates missing or out-of-order tool results
  and is safe to drive from a synchronous progress callback.

This module lives in the core domain layer and intentionally has no
dependency on infrastructure or the application layer beyond the
``EventType`` enum.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from taskforce.core.domain.enums import EventType

# Maximum length we keep when stringifying tool args / errors. Keeps the
# stored log compact so a Telegram /actions reply never blows past the
# message-size limit.
_MAX_ARGS_CHARS = 200
_MAX_ERROR_CHARS = 200


@dataclass(frozen=True)
class ActionRecord:
    """A single tool invocation captured during one user turn.

    Attributes:
        tool_name: Short name of the tool (e.g. ``"file_read"``).
        args_summary: Truncated JSON-ish string of the tool's args. The
            recorder caps this to ~200 characters so the on-disk log
            stays small even for noisy callers like ``python``.
        success: ``True`` when the tool returned without an error.
            ``False`` on tool error or when the run terminated before
            a result event arrived.
        error: Optional short error message when ``success`` is False.
        duration_ms: Wall-clock duration between the ``tool_call`` event
            and its matching ``tool_result``. ``None`` when no result
            was observed before the turn ended.
    """

    tool_name: str
    args_summary: str
    success: bool
    error: str | None = None
    duration_ms: int | None = None


@dataclass(frozen=True)
class ActionLog:
    """All tool calls captured during a single user turn.

    Attributes:
        turn_index: Monotonically increasing index per
            (channel, conversation_id) pair. Index ``0`` is the first
            turn observed by the gateway.
        user_message: Original user message that started this turn.
            Truncated to a short preview for display.
        records: Ordered list of :class:`ActionRecord` instances, one
            per tool call observed during the turn.
    """

    turn_index: int
    user_message: str
    records: list[ActionRecord] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Number of tool calls captured."""
        return len(self.records)

    @property
    def success_count(self) -> int:
        """Number of records where ``success`` is True."""
        return sum(1 for r in self.records if r.success)

    @property
    def failure_count(self) -> int:
        """Number of records where ``success`` is False."""
        return sum(1 for r in self.records if not r.success)


def format_action_log(log: ActionLog | None) -> str:
    """Render an :class:`ActionLog` for a Telegram-style chat reply.

    The format is intentionally compact and ASCII-only — markers are
    ``[ok]`` / ``[fail]`` rather than emoji to comply with the project
    rule that emoji are opt-in only. Empty logs return a friendly
    "no actions" message instead of an empty string so that the
    ``/actions`` command always produces a substantive reply.
    """
    if log is None or log.total == 0:
        return "No prior actions in this conversation."

    header = (
        f"Actions for previous turn ({log.total} tools, "
        f"{log.success_count} ok, {log.failure_count} fail):"
    )
    lines: list[str] = [header]
    for idx, record in enumerate(log.records, start=1):
        marker = "[ok]" if record.success else "[fail]"
        line = f"{idx}. {marker} {record.tool_name}"
        if record.args_summary:
            line += f" {record.args_summary}"
        if record.duration_ms is not None:
            line += f" ({record.duration_ms} ms)"
        if not record.success and record.error:
            line += f" — {record.error}"
        lines.append(line)
    return "\n".join(lines)


def format_footer(log: ActionLog | None) -> str:
    """Render a one-line footer summary for outbound replies.

    Returns an empty string when the log captured no tool calls, so the
    caller can simply concatenate the result without conditional logic.
    """
    if log is None or log.total == 0:
        return ""
    return (
        f"\n\n— Actions: {log.total} tool"
        f"{'s' if log.total != 1 else ''} "
        f"({log.success_count} ok, {log.failure_count} fail)"
    )


def _summarize_args(args: Any) -> str:
    """Compact, lossy serialization of tool arguments for the log."""
    if args is None:
        return ""
    try:
        text = json.dumps(args, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(args)
    if len(text) > _MAX_ARGS_CHARS:
        return text[: _MAX_ARGS_CHARS - 3] + "..."
    return text


def _summarize_error(message: Any) -> str:
    """Truncate an error message to a stable, log-friendly length."""
    if message is None:
        return ""
    text = str(message)
    if len(text) > _MAX_ERROR_CHARS:
        return text[: _MAX_ERROR_CHARS - 3] + "..."
    return text


class TurnRecorder:
    """Collect tool-call activity for a single agent turn.

    Designed to be driven from a streaming ``ProgressUpdate`` callback
    (or directly from ``StreamEvent`` data dicts in tests). Each call
    to :meth:`observe` consumes one event; matching ``tool_call`` and
    ``tool_result`` pairs are linked via ``call_id`` when available.

    The recorder tolerates streams that omit ``tool_result`` events
    (e.g. when execution fails mid-turn) — any unmatched call is
    finalized as ``success=False`` by :meth:`finalize`.
    """

    def __init__(self, *, turn_index: int, user_message: str) -> None:
        self._turn_index = turn_index
        # Truncate the preview at construction time — the user_message
        # is captured purely for display in /actions output.
        if len(user_message) > _MAX_ARGS_CHARS:
            self._user_message = user_message[: _MAX_ARGS_CHARS - 3] + "..."
        else:
            self._user_message = user_message
        # Ordered list of {tool, args_summary, started_at, call_id?, …}
        # so that the final ActionLog preserves invocation order.
        self._pending: list[dict[str, Any]] = []
        # Indexed lookup for fast match-on-result. When call_id is
        # missing we fall back to FIFO matching by tool name.
        self._by_call_id: dict[str, dict[str, Any]] = {}

    def observe(self, event_type: str, data: dict[str, Any] | None) -> None:
        """Record one event from the executor stream.

        ``event_type`` is the canonical ``EventType`` value (string).
        ``data`` is the event payload as produced by the executor;
        ``None`` is treated as an empty payload.
        """
        payload = data or {}
        if event_type == EventType.TOOL_CALL.value:
            self._record_call(payload)
        elif event_type == EventType.TOOL_RESULT.value:
            self._record_result(payload)

    def _record_call(self, payload: dict[str, Any]) -> None:
        entry: dict[str, Any] = {
            "tool_name": str(payload.get("tool") or payload.get("name") or "unknown"),
            "args_summary": _summarize_args(payload.get("args") or payload.get("arguments")),
            "started_at": time.monotonic(),
            "call_id": payload.get("call_id") or payload.get("id"),
            "result": None,
        }
        self._pending.append(entry)
        if entry["call_id"] is not None:
            self._by_call_id[str(entry["call_id"])] = entry

    def _record_result(self, payload: dict[str, Any]) -> None:
        entry = self._match_entry(payload)
        if entry is None:
            return
        success = bool(payload.get("success", True))
        error = payload.get("error") if not success else None
        entry["result"] = {
            "success": success,
            "error": _summarize_error(error) if error else None,
            "duration_ms": int((time.monotonic() - entry["started_at"]) * 1000),
        }

    def _match_entry(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Find the pending tool-call that this result belongs to."""
        call_id = payload.get("call_id") or payload.get("id")
        if call_id is not None:
            entry = self._by_call_id.get(str(call_id))
            if entry is not None and entry.get("result") is None:
                return entry
        # Fall back to the most recent pending call for this tool name.
        tool = str(payload.get("tool") or payload.get("name") or "")
        for entry in reversed(self._pending):
            if entry.get("result") is not None:
                continue
            if not tool or entry["tool_name"] == tool:
                return entry
        return None

    def finalize(self) -> ActionLog:
        """Return the finished :class:`ActionLog` for this turn."""
        records: list[ActionRecord] = []
        for entry in self._pending:
            result = entry.get("result")
            if result is None:
                # Unmatched call (turn ended before result arrived).
                records.append(
                    ActionRecord(
                        tool_name=entry["tool_name"],
                        args_summary=entry["args_summary"],
                        success=False,
                        error="no result observed",
                        duration_ms=None,
                    )
                )
                continue
            records.append(
                ActionRecord(
                    tool_name=entry["tool_name"],
                    args_summary=entry["args_summary"],
                    success=bool(result["success"]),
                    error=result.get("error"),
                    duration_ms=result.get("duration_ms"),
                )
            )
        return ActionLog(
            turn_index=self._turn_index,
            user_message=self._user_message,
            records=records,
        )
