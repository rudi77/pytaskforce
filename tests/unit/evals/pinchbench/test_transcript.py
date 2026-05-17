"""Unit tests for evals.pinchbench.transcript.build_transcript."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from evals.pinchbench.transcript import build_transcript
from taskforce.core.domain.enums import EventType


@dataclass
class FakeEvent:
    """Stand-in for taskforce.application.executor.ProgressUpdate."""

    event_type: EventType
    details: dict[str, Any]
    message: str = ""


def test_user_prompt_is_first_entry() -> None:
    transcript = build_transcript([], prompt="Hello there")
    assert transcript[0] == {
        "type": "message",
        "message": {"role": "user", "content": [{"type": "text", "text": "Hello there"}]},
    }


def test_llm_tokens_coalesce_into_one_assistant_message() -> None:
    events = [
        FakeEvent(EventType.LLM_TOKEN, {"content": "Hel"}),
        FakeEvent(EventType.LLM_TOKEN, {"content": "lo"}),
        FakeEvent(EventType.LLM_TOKEN, {"content": " world"}),
    ]
    transcript = build_transcript(events, prompt="say hi")

    # entry[0] is the user prompt; entry[1] should be the coalesced assistant text.
    assert transcript[1] == {
        "type": "message",
        "message": {"role": "assistant", "content": [{"type": "text", "text": "Hello world"}]},
    }


def test_tool_call_event_uses_args_key_not_params() -> None:
    """Regression: transcript.py used details['params'], real key is 'args'."""
    events = [
        FakeEvent(
            EventType.TOOL_CALL,
            {"tool": "file_write", "args": {"path": "/tmp/x", "content": "hi"}, "id": "1"},
        ),
    ]
    transcript = build_transcript(events, prompt="write a file")
    tool_use = transcript[1]["message"]["content"][0]
    assert tool_use == {
        "type": "tool_use",
        "name": "file_write",
        "input": {"path": "/tmp/x", "content": "hi"},
    }


def test_tool_result_event_uses_output_key_not_result() -> None:
    """Regression: transcript.py used details['result'], real key is 'output'."""
    events = [
        FakeEvent(
            EventType.TOOL_RESULT,
            {"tool": "file_write", "success": True, "output": "wrote 2 bytes", "args": {}},
        ),
    ]
    transcript = build_transcript(events, prompt="write")
    tool_result = transcript[1]["message"]["content"][0]
    assert tool_result == {"type": "tool_result", "content": "wrote 2 bytes"}


def test_complete_event_emits_final_assistant_message_from_event_message() -> None:
    """COMPLETE's final message lives on evt.message, not in details."""
    events = [
        FakeEvent(EventType.LLM_TOKEN, {"content": "draft "}),
        FakeEvent(
            EventType.COMPLETE,
            {"status": "completed", "session_id": "s1"},
            message="All done.",
        ),
    ]
    transcript = build_transcript(events, prompt="do x")

    # Expect: user prompt -> assistant draft (flushed on COMPLETE) -> assistant final
    roles = [e["message"]["role"] for e in transcript]
    texts = [e["message"]["content"][0].get("text", "") for e in transcript]
    assert roles == ["user", "assistant", "assistant"]
    assert texts[1] == "draft "
    assert texts[2] == "All done."


def test_pending_text_flushed_before_tool_call() -> None:
    events = [
        FakeEvent(EventType.LLM_TOKEN, {"content": "thinking..."}),
        FakeEvent(EventType.TOOL_CALL, {"tool": "shell", "args": {"command": "ls"}}),
    ]
    transcript = build_transcript(events, prompt="p")
    # user, assistant text, assistant tool_use
    assert [e["message"]["role"] for e in transcript] == ["user", "assistant", "assistant"]
    assert transcript[1]["message"]["content"][0]["type"] == "text"
    assert transcript[2]["message"]["content"][0]["type"] == "tool_use"


def test_final_answer_content_is_appended_to_pending_text() -> None:
    events = [
        FakeEvent(EventType.FINAL_ANSWER, {"content": "The answer is 42."}),
        FakeEvent(EventType.COMPLETE, {"status": "completed"}, message=""),
    ]
    transcript = build_transcript(events, prompt="q")
    assert transcript[1]["message"]["content"][0]["text"] == "The answer is 42."


@pytest.mark.parametrize("evt_type_value", ["llm_token", EventType.LLM_TOKEN])
def test_event_type_accepts_enum_or_string(evt_type_value: Any) -> None:
    events = [FakeEvent(evt_type_value, {"content": "x"})]
    transcript = build_transcript(events, prompt="p")
    assert transcript[1]["message"]["content"][0]["text"] == "x"
