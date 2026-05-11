"""Pure stateless helper functions for planning strategies."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from taskforce.core.domain.enums import EventType, MessageRole
from taskforce.core.domain.models import StreamEvent
from taskforce.core.interfaces.logging import LoggerProtocol

if TYPE_CHECKING:
    from taskforce.core.domain.agent import Agent


def _persist_active_skill(agent: Agent, state: dict[str, Any]) -> None:
    """Snapshot the active skill name into ``state`` for session persistence."""
    if agent.skill_manager:
        state["active_skill"] = agent.skill_manager.active_skill_name
    elif "active_skill" not in state:
        state["active_skill"] = None


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _ensure_event_type(event: StreamEvent) -> EventType:
    """Coerce ``event.event_type`` to ``EventType`` enum.

    Some code paths store event types as plain strings for backwards
    compatibility.  This helper normalises them so callers can compare
    via ``==`` against enum members.
    """
    et = event.event_type
    return et if isinstance(et, EventType) else EventType(et)


def _parse_tool_args(tool_call: dict[str, Any], logger: LoggerProtocol) -> dict[str, Any]:
    """Parse tool call arguments from JSON string."""
    try:
        result: dict[str, Any] = json.loads(tool_call["function"]["arguments"])
        return result
    except json.JSONDecodeError:
        logger.warning("tool_args_parse_failed", tool=tool_call["function"]["name"])
        return {}


def _extract_tool_output(result: dict[str, Any]) -> str:
    """Extract display-friendly output from a tool result dict."""
    if "output" in result:
        out = result["output"]
        return out if isinstance(out, str) else json.dumps(out, default=str)
    return result.get("error", "") or json.dumps(result, default=str)


def _parse_plan_steps(content: str, logger: LoggerProtocol) -> list[str]:
    """Parse plan steps from LLM response."""
    text = content.strip()
    if not text:
        return []

    # Extract JSON from code blocks
    json_text = text
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            json_text = parts[1].strip()
            if "\n" in json_text and not json_text.split("\n")[0].startswith("["):
                json_text = json_text.split("\n", 1)[1].strip()

    try:
        data = json.loads(json_text)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except (json.JSONDecodeError, TypeError):
        logger.debug("json_parse_failed")

    # Fallback: line-based
    steps = []
    for line in text.splitlines():
        c = line.strip().lstrip("-").strip()
        if c and not c.startswith("```"):
            if c[0].isdigit() and "." in c:
                c = c.split(".", 1)[1].strip()
            if c:
                steps.append(c)
    return steps


_TERMINAL_APPROVAL_ERROR_KINDS = frozenset({"approval_denied", "approval_timeout"})


def _build_retry_nudge(
    failed_tool_names: list[str],
    attempt: int = 1,
    *,
    error_kinds: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a user-role message nudging the agent after tool failures.

    Args:
        failed_tool_names: Names of tools that failed in the current step.
        attempt: How many times this tool has already failed (1 = first failure).
        error_kinds: Optional map of ``tool_name → error_kind`` for the
            failed tools. When present, an approval-denied / approval-timeout
            failure switches the nudge from "retry differently" to "tell
            the user the action wasn't permitted" — retrying the same or
            a similar forbidden action after the user has explicitly said
            no is the bug that issue #190 sub-item (a) calls out.

    Returns:
        A message dict with role ``user`` containing retry instructions.
    """
    tools_str = ", ".join(dict.fromkeys(failed_tool_names))  # deduplicate, preserve order

    # Approval-denied / approval-timeout means the user has refused (or
    # the request expired without consent). The LLM must NOT retry the
    # same action with different args, NOR fall back to a tool that
    # would achieve the same forbidden outcome. Tell it to surface the
    # refusal to the user instead. Applies whenever at least one
    # failed tool was approval-blocked — even if mixed with other
    # failures we want the LLM to lead with the refusal.
    error_kinds = error_kinds or {}
    approval_blocked = [
        t
        for t in dict.fromkeys(failed_tool_names)
        if error_kinds.get(t) in _TERMINAL_APPROVAL_ERROR_KINDS
    ]
    if approval_blocked:
        approval_str = ", ".join(approval_blocked)
        kind_label = (
            "denied"
            if any(error_kinds.get(t) == "approval_denied" for t in approval_blocked)
            else "timed out"
        )
        return {
            "role": MessageRole.USER.value,
            "content": (
                f"[System: Approval was {kind_label} for {approval_str}. "
                "Do NOT retry this action, NOR any tool that would have "
                "the same effect. In your next reply, tell the user in "
                "plain language that the action was not permitted and "
                "ask what they would prefer instead.]"
            ),
        }

    if attempt >= 2:
        return {
            "role": MessageRole.USER.value,
            "content": (
                f"[System: {tools_str} failed again (attempt {attempt}). "
                "STOP retrying the same approach. "
                "Options: (1) delegate to a sub-agent via call_agents_parallel "
                "— sub-agents have more tools (file_read, web_search, python, etc.), "
                "(2) use ask_user to get help, "
                "(3) provide your best answer with the information you already have.]"
            ),
        }
    return {
        "role": MessageRole.USER.value,
        "content": (
            f"[System: {tools_str} failed. "
            "Try a different tool or approach. "
            "If this is a non-critical step (like notifications) and "
            "the alternative also fails, skip it and move on. "
            "Use `python` or `powershell`/`shell` as alternatives.]"
        ),
    }


def _is_no_progress_tool_output(output: str) -> bool:
    """Heuristic detection for low-signal tool outputs.

    This helps the ReAct loop detect repeated search cycles that keep
    returning empty results.
    """
    normalized = output.lower()
    no_progress_markers = (
        "0 matches",
        "no files found",
        "no records",
        "not found",
        "0 file",
        "0 results",
    )
    return any(marker in normalized for marker in no_progress_markers)
