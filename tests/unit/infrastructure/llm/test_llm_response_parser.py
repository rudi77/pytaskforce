"""
Unit tests for LLMResponseParser.

Tests cover:
- parse_response: normal content, reasoning_content fallback, refusal, tool calls
- extract_usage: dict form, object form, None, missing fields
- _extract_tool_calls: present, absent, empty list
- _check_model_mismatch: exact match, prefix match, provider prefix, mismatch, None actual
- extract_actual_model_from_chunk: string model, None, non-string
- init_tool_call_entry: full delta, missing fields
- update_tool_call_metadata: updates id/name, no-op on missing
- extract_arguments_delta: present, None, no function attr
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from taskforce.infrastructure.llm.llm_response_parser import LLMResponseParser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(
    content: str | None = "hello",
    tool_calls: list | None = None,
    usage: Any = None,
    model: Any = "gpt-5",
    reasoning_content: str | None = None,
    refusal: str | None = None,
) -> SimpleNamespace:
    """Build a fake LiteLLM response object."""
    message_kwargs: dict[str, Any] = {"content": content, "tool_calls": tool_calls}
    if reasoning_content is not None:
        message_kwargs["reasoning_content"] = reasoning_content
    if refusal is not None:
        message_kwargs["refusal"] = refusal
    message = SimpleNamespace(**message_kwargs)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice], usage=usage, model=model)


def _make_tool_call(
    tc_id: str = "tc_1",
    name: str = "file_read",
    arguments: str = '{"path": "x.py"}',
    tc_type: str = "function",
) -> SimpleNamespace:
    """Build a fake tool call object."""
    func = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(id=tc_id, type=tc_type, function=func)


def _make_usage_obj(
    total: int = 100, prompt: int = 40, completion: int = 60
) -> SimpleNamespace:
    return SimpleNamespace(
        total_tokens=total, prompt_tokens=prompt, completion_tokens=completion
    )


# ---------------------------------------------------------------------------
# parse_response
# ---------------------------------------------------------------------------


class TestParseResponse:
    def test_basic_content(self):
        resp = _make_response(content="Hello world")
        result = LLMResponseParser.parse_response(resp, model="gpt-5", latency_ms=150)

        assert result["success"] is True
        assert result["content"] == "Hello world"
        assert result["tool_calls"] is None
        assert result["model"] == "gpt-5"
        assert result["actual_model"] == "gpt-5"
        assert result["latency_ms"] == 150

    def test_empty_content_falls_back_to_reasoning_content(self):
        resp = _make_response(content="", reasoning_content="thinking deeply")
        result = LLMResponseParser.parse_response(resp, model="o1", latency_ms=200)
        assert result["content"] == "thinking deeply"

    def test_none_content_falls_back_to_reasoning_content(self):
        resp = _make_response(content=None, reasoning_content="chain of thought")
        result = LLMResponseParser.parse_response(resp, model="o1", latency_ms=100)
        assert result["content"] == "chain of thought"

    def test_refusal_content(self):
        resp = _make_response(content=None, refusal="I cannot do that")
        result = LLMResponseParser.parse_response(resp, model="gpt-5", latency_ms=50)
        assert result["content"] == "[Model refused: I cannot do that]"

    def test_no_content_no_reasoning_no_refusal(self):
        resp = _make_response(content=None)
        result = LLMResponseParser.parse_response(resp, model="gpt-5", latency_ms=10)
        assert result["content"] is None

    def test_with_tool_calls(self):
        tc = _make_tool_call()
        resp = _make_response(content=None, tool_calls=[tc])
        result = LLMResponseParser.parse_response(resp, model="gpt-5", latency_ms=100)

        assert result["tool_calls"] is not None
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["id"] == "tc_1"
        assert result["tool_calls"][0]["function"]["name"] == "file_read"

    def test_usage_dict_passed_through(self):
        usage = {"total_tokens": 50, "prompt_tokens": 20, "completion_tokens": 30}
        resp = _make_response(usage=usage)
        result = LLMResponseParser.parse_response(resp, model="gpt-5", latency_ms=10)
        assert result["usage"] == usage

    def test_usage_object_extracted(self):
        usage = _make_usage_obj(100, 40, 60)
        resp = _make_response(usage=usage)
        result = LLMResponseParser.parse_response(resp, model="gpt-5", latency_ms=10)
        assert result["usage"]["total_tokens"] == 100
        assert result["usage"]["prompt_tokens"] == 40
        assert result["usage"]["completion_tokens"] == 60

    def test_actual_model_non_string_is_none(self):
        resp = _make_response(model=12345)
        result = LLMResponseParser.parse_response(resp, model="gpt-5", latency_ms=10)
        assert result["actual_model"] is None

    def test_actual_model_none(self):
        resp = _make_response(model=None)
        result = LLMResponseParser.parse_response(resp, model="gpt-5", latency_ms=10)
        assert result["actual_model"] is None


# ---------------------------------------------------------------------------
# extract_usage
# ---------------------------------------------------------------------------


class TestExtractUsage:
    def test_none_usage(self):
        resp = SimpleNamespace(usage=None)
        assert LLMResponseParser.extract_usage(resp) == {}

    def test_missing_usage_attr(self):
        resp = SimpleNamespace()
        assert LLMResponseParser.extract_usage(resp) == {}

    def test_dict_usage(self):
        usage = {"total_tokens": 10, "prompt_tokens": 3, "completion_tokens": 7}
        resp = SimpleNamespace(usage=usage)
        assert LLMResponseParser.extract_usage(resp) == usage

    def test_object_usage(self):
        usage = _make_usage_obj(200, 80, 120)
        resp = SimpleNamespace(usage=usage)
        result = LLMResponseParser.extract_usage(resp)
        assert result == {"total_tokens": 200, "prompt_tokens": 80, "completion_tokens": 120}

    def test_object_usage_with_none_fields(self):
        """None token counts should default to 0."""
        usage = SimpleNamespace(total_tokens=None, prompt_tokens=None, completion_tokens=None)
        resp = SimpleNamespace(usage=usage)
        result = LLMResponseParser.extract_usage(resp)
        assert result == {"total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0}

    def test_object_usage_with_missing_fields(self):
        """Missing token attributes should default to 0."""
        usage = SimpleNamespace()
        resp = SimpleNamespace(usage=usage)
        result = LLMResponseParser.extract_usage(resp)
        assert result == {"total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0}


# ---------------------------------------------------------------------------
# _extract_tool_calls
# ---------------------------------------------------------------------------


class TestExtractToolCalls:
    def test_no_tool_calls_attr(self):
        message = SimpleNamespace()
        assert LLMResponseParser._extract_tool_calls(message) is None

    def test_none_tool_calls(self):
        message = SimpleNamespace(tool_calls=None)
        assert LLMResponseParser._extract_tool_calls(message) is None

    def test_empty_tool_calls(self):
        message = SimpleNamespace(tool_calls=[])
        assert LLMResponseParser._extract_tool_calls(message) is None

    def test_single_tool_call(self):
        tc = _make_tool_call(tc_id="abc", name="shell", arguments='{"cmd":"ls"}')
        message = SimpleNamespace(tool_calls=[tc])
        result = LLMResponseParser._extract_tool_calls(message)

        assert result is not None
        assert len(result) == 1
        assert result[0] == {
            "id": "abc",
            "type": "function",
            "function": {"name": "shell", "arguments": '{"cmd":"ls"}'},
        }

    def test_multiple_tool_calls(self):
        tc1 = _make_tool_call(tc_id="a", name="file_read", arguments="{}")
        tc2 = _make_tool_call(tc_id="b", name="file_write", arguments='{"data":"x"}')
        message = SimpleNamespace(tool_calls=[tc1, tc2])
        result = LLMResponseParser._extract_tool_calls(message)

        assert len(result) == 2
        assert result[0]["id"] == "a"
        assert result[1]["id"] == "b"

    def test_tool_call_missing_type_defaults_to_function(self):
        """If the tool call object has no 'type' attr, default to 'function'."""
        func = SimpleNamespace(name="test", arguments="{}")
        tc = SimpleNamespace(id="x", function=func)  # no 'type' attr
        message = SimpleNamespace(tool_calls=[tc])
        result = LLMResponseParser._extract_tool_calls(message)
        assert result[0]["type"] == "function"


# ---------------------------------------------------------------------------
# _check_model_mismatch
# ---------------------------------------------------------------------------


class TestCheckModelMismatch:
    """Tests verify no exceptions are raised. Logging is side-effect only."""

    def test_none_actual_no_error(self):
        LLMResponseParser._check_model_mismatch("gpt-5", None)

    def test_exact_match(self):
        LLMResponseParser._check_model_mismatch("gpt-5", "gpt-5")

    def test_provider_prefix_stripped(self):
        LLMResponseParser._check_model_mismatch("azure/gpt-5-nano", "gpt-5-nano")

    def test_version_suffix_accepted(self):
        LLMResponseParser._check_model_mismatch("gpt-5-nano", "gpt-5-nano-2025-08-07")

    def test_provider_prefix_and_version_suffix(self):
        LLMResponseParser._check_model_mismatch("azure/gpt-5-nano", "gpt-5-nano-2025-08-07")

    def test_case_insensitive(self):
        LLMResponseParser._check_model_mismatch("GPT-5", "gpt-5")

    def test_mismatch_no_exception(self):
        # Different model entirely; should log warning but not raise
        LLMResponseParser._check_model_mismatch("gpt-5", "claude-opus-4-6")

    def test_both_have_provider_prefix(self):
        LLMResponseParser._check_model_mismatch("azure/gpt-5", "azure/gpt-5")


# ---------------------------------------------------------------------------
# extract_actual_model_from_chunk
# ---------------------------------------------------------------------------


class TestExtractActualModelFromChunk:
    def test_string_model(self):
        chunk = SimpleNamespace(model="gpt-5")
        assert LLMResponseParser.extract_actual_model_from_chunk(chunk) == "gpt-5"

    def test_none_model(self):
        chunk = SimpleNamespace(model=None)
        assert LLMResponseParser.extract_actual_model_from_chunk(chunk) is None

    def test_missing_model_attr(self):
        chunk = SimpleNamespace()
        assert LLMResponseParser.extract_actual_model_from_chunk(chunk) is None

    def test_non_string_model(self):
        chunk = SimpleNamespace(model=42)
        assert LLMResponseParser.extract_actual_model_from_chunk(chunk) is None


# ---------------------------------------------------------------------------
# init_tool_call_entry
# ---------------------------------------------------------------------------


class TestInitToolCallEntry:
    def test_full_delta(self):
        func = SimpleNamespace(name="file_read")
        tc = SimpleNamespace(id="tc_1", function=func)
        entry = LLMResponseParser.init_tool_call_entry(tc)
        assert entry == {"id": "tc_1", "name": "file_read", "arguments": ""}

    def test_missing_id(self):
        func = SimpleNamespace(name="shell")
        tc = SimpleNamespace(function=func)  # no id attr
        entry = LLMResponseParser.init_tool_call_entry(tc)
        assert entry["id"] == ""
        assert entry["name"] == "shell"

    def test_none_id(self):
        func = SimpleNamespace(name="shell")
        tc = SimpleNamespace(id=None, function=func)
        entry = LLMResponseParser.init_tool_call_entry(tc)
        assert entry["id"] == ""

    def test_no_function(self):
        tc = SimpleNamespace(id="tc_2")
        entry = LLMResponseParser.init_tool_call_entry(tc)
        assert entry == {"id": "tc_2", "name": "", "arguments": ""}

    def test_none_function(self):
        tc = SimpleNamespace(id="tc_3", function=None)
        entry = LLMResponseParser.init_tool_call_entry(tc)
        assert entry["name"] == ""

    def test_function_with_none_name(self):
        func = SimpleNamespace(name=None)
        tc = SimpleNamespace(id="tc_4", function=func)
        entry = LLMResponseParser.init_tool_call_entry(tc)
        assert entry["name"] == ""


# ---------------------------------------------------------------------------
# update_tool_call_metadata
# ---------------------------------------------------------------------------


class TestUpdateToolCallMetadata:
    def test_updates_id_and_name(self):
        func = SimpleNamespace(name="python")
        tc = SimpleNamespace(id="new_id", function=func)
        entry = {"id": "old_id", "name": "old_name", "arguments": ""}
        LLMResponseParser.update_tool_call_metadata(tc, entry)
        assert entry["id"] == "new_id"
        assert entry["name"] == "python"

    def test_no_update_when_missing(self):
        tc = SimpleNamespace()
        entry = {"id": "keep", "name": "keep", "arguments": ""}
        LLMResponseParser.update_tool_call_metadata(tc, entry)
        assert entry["id"] == "keep"
        assert entry["name"] == "keep"

    def test_no_update_when_id_empty(self):
        tc = SimpleNamespace(id="", function=None)
        entry = {"id": "keep", "name": "keep", "arguments": ""}
        LLMResponseParser.update_tool_call_metadata(tc, entry)
        assert entry["id"] == "keep"

    def test_no_update_when_function_name_empty(self):
        func = SimpleNamespace(name="")
        tc = SimpleNamespace(id=None, function=func)
        entry = {"id": "keep", "name": "keep", "arguments": ""}
        LLMResponseParser.update_tool_call_metadata(tc, entry)
        assert entry["id"] == "keep"
        assert entry["name"] == "keep"

    def test_updates_only_id(self):
        tc = SimpleNamespace(id="updated_id")
        entry = {"id": "old", "name": "keep", "arguments": ""}
        LLMResponseParser.update_tool_call_metadata(tc, entry)
        assert entry["id"] == "updated_id"
        assert entry["name"] == "keep"


# ---------------------------------------------------------------------------
# extract_arguments_delta
# ---------------------------------------------------------------------------


class TestExtractArgumentsDelta:
    def test_returns_arguments(self):
        func = SimpleNamespace(arguments='{"key": "val"}')
        tc = SimpleNamespace(function=func)
        assert LLMResponseParser.extract_arguments_delta(tc) == '{"key": "val"}'

    def test_none_arguments_returns_none(self):
        func = SimpleNamespace(arguments=None)
        tc = SimpleNamespace(function=func)
        assert LLMResponseParser.extract_arguments_delta(tc) is None

    def test_empty_string_arguments_returns_none(self):
        func = SimpleNamespace(arguments="")
        tc = SimpleNamespace(function=func)
        assert LLMResponseParser.extract_arguments_delta(tc) is None

    def test_no_function_attr(self):
        tc = SimpleNamespace()
        assert LLMResponseParser.extract_arguments_delta(tc) is None

    def test_none_function(self):
        tc = SimpleNamespace(function=None)
        assert LLMResponseParser.extract_arguments_delta(tc) is None

    def test_function_missing_arguments_attr(self):
        func = SimpleNamespace()
        tc = SimpleNamespace(function=func)
        assert LLMResponseParser.extract_arguments_delta(tc) is None
