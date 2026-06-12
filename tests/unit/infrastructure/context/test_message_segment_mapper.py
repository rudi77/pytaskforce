"""Table-driven tests for the OpenAI-message ↔ ctxman-segment mapping."""

from __future__ import annotations

import json

from taskforce.infrastructure.context.message_segment_mapper import (
    build_static_segments,
    message_to_segments,
    messages_to_segments,
    split_static,
)


def test_system_message_maps_to_no_segments() -> None:
    assert message_to_segments({"role": "system", "content": "base"}) == []


def test_user_message_maps_to_user_msg() -> None:
    segments = message_to_segments({"role": "user", "content": "hello"})
    assert segments == [{"kind": "user_msg", "role": "user", "content": "hello"}]


def test_assistant_without_tool_calls_maps_to_assistant_msg() -> None:
    segments = message_to_segments({"role": "assistant", "content": "answer"})
    assert segments == [{"kind": "assistant_msg", "role": "assistant", "content": "answer"}]


def test_assistant_with_tool_calls_maps_to_tool_call_segments() -> None:
    message = {
        "role": "assistant",
        "content": "Let me check.",
        "tool_calls": [
            {
                "id": "call_1",
                "function": {"name": "file_read", "arguments": '{"path": "a.txt"}'},
            },
            {
                "id": "call_2",
                "function": {"name": "web_search", "arguments": '{"query": "x"}'},
            },
        ],
    }
    segments = message_to_segments(message)
    assert len(segments) == 3
    assert segments[0] == {
        "kind": "assistant_msg",
        "role": "assistant",
        "content": "Let me check.",
    }
    assert segments[1]["kind"] == "tool_call"
    assert segments[1]["tool_call_id"] == "call_1"
    assert json.loads(segments[1]["content"]) == {
        "name": "file_read",
        "arguments": '{"path": "a.txt"}',
    }
    assert segments[2]["tool_call_id"] == "call_2"


def test_assistant_tool_calls_without_content_skips_assistant_msg() -> None:
    message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": "call_1", "function": {"name": "t", "arguments": "{}"}}],
    }
    segments = message_to_segments(message)
    assert len(segments) == 1
    assert segments[0]["kind"] == "tool_call"


def test_tool_message_maps_to_tool_result() -> None:
    segments = message_to_segments(
        {"role": "tool", "tool_call_id": "call_1", "content": "result text"}
    )
    assert segments == [
        {
            "kind": "tool_result",
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "result text",
        }
    ]


def test_content_part_list_is_flattened() -> None:
    message = {
        "role": "user",
        "content": [{"type": "text", "text": "part one"}, {"text": "part two"}],
    }
    segments = message_to_segments(message)
    assert segments[0]["content"] == "part one\npart two"


def test_messages_to_segments_flattens_and_skips_system() -> None:
    messages = [
        {"role": "system", "content": "base"},
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "a"},
    ]
    segments = messages_to_segments(messages)
    assert [segment["kind"] for segment in segments] == ["user_msg", "assistant_msg"]


def test_split_static_extracts_first_system_prompt() -> None:
    system, rest = split_static(
        [
            {"role": "system", "content": "base"},
            {"role": "user", "content": "q"},
        ]
    )
    assert system == "base"
    assert rest == [{"role": "user", "content": "q"}]


def test_build_static_segments_includes_prompt_and_tool_defs() -> None:
    tools = [
        {"type": "function", "function": {"name": "file_read", "parameters": {}}},
    ]
    segments = build_static_segments("base prompt", tools)
    assert segments[0] == {
        "kind": "system_prompt",
        "role": "system",
        "content": "base prompt",
        "source": "core",
    }
    assert segments[1]["kind"] == "tool_def"
    assert segments[1]["source"] == "taskforce:file_read"
    assert json.loads(segments[1]["content"])["function"]["name"] == "file_read"
