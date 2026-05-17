"""Translate Taskforce execution events into pinchbench's transcript format.

Pinchbench's ``def grade(transcript: list, workspace_path: str) -> dict``
functions consume a list of dicts shaped like OpenClaw's JSONL session log:

    {"type": "message",
     "message": {"role": "assistant",
                 "content": [{"type": "text", "text": "..."}]}}

    {"type": "message",
     "message": {"role": "assistant",
                 "content": [{"type": "tool_use",
                              "name": "...", "input": {...}}]}}

    {"type": "message",
     "message": {"role": "user",
                 "content": [{"type": "tool_result", "content": "..."}]}}

We accumulate Taskforce ``ProgressUpdate`` events and emit the equivalent
structure so existing pinchbench ``grade()`` functions Just Work.
"""

from __future__ import annotations

from typing import Any


def _text_entry(role: str, text: str) -> dict[str, Any]:
    return {
        "type": "message",
        "message": {"role": role, "content": [{"type": "text", "text": text}]},
    }


def _tool_use_entry(name: str, params: Any) -> dict[str, Any]:
    return {
        "type": "message",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "name": name, "input": params or {}}
            ],
        },
    }


def _tool_result_entry(content: Any) -> dict[str, Any]:
    return {
        "type": "message",
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "content": content}],
        },
    }


def build_transcript(events: list[Any], prompt: str) -> list[dict[str, Any]]:
    """Build a pinchbench-compatible transcript from Taskforce events.

    ``events`` is the list of ``ProgressUpdate`` objects yielded by
    ``AgentExecutor.execute_mission_streaming``. We coalesce ``llm_token``
    streams into single text messages and flush them whenever a tool call
    or completion event arrives.
    """
    from taskforce.core.domain.enums import EventType

    transcript: list[dict[str, Any]] = [_text_entry("user", prompt)]
    pending_text: list[str] = []

    def flush_text() -> None:
        if pending_text:
            transcript.append(_text_entry("assistant", "".join(pending_text)))
            pending_text.clear()

    for evt in events:
        evt_type = evt.event_type
        evt_str = evt_type.value if hasattr(evt_type, "value") else str(evt_type)
        details = getattr(evt, "details", None) or {}

        if evt_str == EventType.LLM_TOKEN.value:
            token = details.get("content") or getattr(evt, "message", "") or ""
            if token:
                pending_text.append(str(token))

        elif evt_str == EventType.TOOL_CALL.value:
            flush_text()
            tool_name = (
                details.get("tool")
                or details.get("name")
                or details.get("tool_name")
                or ""
            )
            params = details.get("params") or details.get("input") or {}
            transcript.append(_tool_use_entry(tool_name, params))

        elif evt_str == EventType.TOOL_RESULT.value:
            result = details.get("result")
            if result is None:
                result = getattr(evt, "message", "") or ""
            transcript.append(_tool_result_entry(result))

        elif evt_str == EventType.FINAL_ANSWER.value:
            content = details.get("content") or ""
            if content:
                pending_text.append(str(content))

        elif evt_str == EventType.COMPLETE.value:
            flush_text()
            final = details.get("final_message") or getattr(evt, "message", "")
            if final and not any(
                e.get("type") == "message"
                and e["message"].get("role") == "assistant"
                and any(
                    c.get("type") == "text" and c.get("text", "").strip() == str(final).strip()
                    for c in e["message"].get("content", [])
                )
                for e in transcript[-3:]
            ):
                transcript.append(_text_entry("assistant", str(final)))

    flush_text()
    return transcript
