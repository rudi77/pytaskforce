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
            # Taskforce ProgressUpdate keys are ``tool`` / ``args``
            # (see core/domain/planning/tool_execution.py:280-287).
            tool_name = details.get("tool", "")
            args = details.get("args") or {}
            transcript.append(_tool_use_entry(tool_name, args))

        elif evt_str == EventType.TOOL_RESULT.value:
            # Tool output key is ``output``, alongside ``success`` /
            # optional ``error_kind`` (tool_execution.py:223-230).
            output = details.get("output")
            if output is None:
                output = getattr(evt, "message", "") or ""
            transcript.append(_tool_result_entry(output))

        elif evt_str == EventType.FINAL_ANSWER.value:
            content = details.get("content") or ""
            if content:
                pending_text.append(str(content))

        elif evt_str == EventType.COMPLETE.value:
            flush_text()
            # COMPLETE's final message lives on the ProgressUpdate's
            # ``message`` attribute (see
            # application/progress_update_builder.py:build_completion_update).
            final = getattr(evt, "message", "") or details.get("final_message", "")
            if final:
                transcript.append(_text_entry("assistant", str(final)))

    flush_text()
    return transcript
