"""Tests for streaming-path content-filter recovery.

Azure OpenAI's content classifier sometimes blocks perfectly legitimate
prompts because of trigger words sitting in older tool-result chunks
(e.g. web-search snippets discussing BMI / Adipositas while answering a
benign anthropometry question). The non-streaming ``complete()`` path
strips those messages and retries once. These tests pin the same
behavior for the streaming path that the agent actually uses.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

from taskforce.infrastructure.llm.litellm_service import LiteLLMService


@pytest.fixture
def temp_config_file(tmp_path):
    config = {
        "default_model": "main",
        "models": {"main": "gpt-test"},
        "model_params": {"gpt-test": {"temperature": 0.0, "max_tokens": 100}},
        "default_params": {"temperature": 0.7, "max_tokens": 200},
        "retry": {"max_attempts": 1, "backoff_multiplier": 2, "timeout": 30},
        "logging": {"log_token_usage": False},
    }
    path = tmp_path / "llm_config.yaml"
    with open(path, "w") as f:
        yaml.dump(config, f)
    return str(path)


def _content_chunk(text: str | None, finish_reason: str | None = None) -> MagicMock:
    chunk = MagicMock()
    delta = MagicMock()
    delta.content = text
    delta.tool_calls = None
    chunk.choices = [MagicMock(delta=delta, finish_reason=finish_reason)]
    chunk.usage = None
    return chunk


async def _stream_of(*chunks: MagicMock):
    for c in chunks:
        yield c


_CONTENT_FILTER_MSG = (
    "litellm.BadRequestError: litellm.ContentPolicyViolationError: "
    "AzureException - The response was filtered due to the prompt "
    "triggering Azure OpenAI's content management policy."
)


@pytest.mark.asyncio
async def test_recovery_succeeds_after_content_filter(temp_config_file: str) -> None:
    """First call raises content filter, retry on stripped history succeeds."""
    service = LiteLLMService(config_path=temp_config_file)

    messages = [
        {"role": "system", "content": "you are a research assistant"},
        {"role": "user", "content": "Topic A"},
        {"role": "assistant", "content": "Result A"},
        {"role": "tool", "content": "raw web-search snippets"},
        {"role": "user", "content": "Now visualize the data"},
    ]

    call_count = {"n": 0}

    async def fake_acompletion(**_kwargs: Any) -> Any:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError(_CONTENT_FILTER_MSG)
        return _stream_of(_content_chunk("Hier sind die Daten.", finish_reason="stop"))

    with patch(
        "taskforce.infrastructure.llm.litellm_service.litellm.acompletion",
        side_effect=fake_acompletion,
    ):
        events = [evt async for evt in service.complete_stream(messages=messages)]

    assert call_count["n"] == 2
    types = [e.get("type") for e in events]
    assert "error" not in types
    assert "done" in types
    token_text = "".join(e.get("content", "") for e in events if e.get("type") == "token")
    assert token_text == "Hier sind die Daten."


@pytest.mark.asyncio
async def test_recovery_failure_surfaces_content_filter_error(temp_config_file: str) -> None:
    """When all recovery stages also content-filter, surface non_retryable error.

    Recovery now runs two staged retries (``tool_results_only`` then
    ``aggressive``), so the total call count is primary + 2 stages = 3
    when both stages keep getting filtered.
    """
    service = LiteLLMService(config_path=temp_config_file)

    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "tool", "content": "t1"},
        {"role": "user", "content": "u2"},
    ]

    call_count = {"n": 0}

    async def fake_acompletion(**_kwargs: Any) -> Any:
        call_count["n"] += 1
        raise RuntimeError(_CONTENT_FILTER_MSG)

    with patch(
        "taskforce.infrastructure.llm.litellm_service.litellm.acompletion",
        side_effect=fake_acompletion,
    ):
        events = [evt async for evt in service.complete_stream(messages=messages)]

    assert call_count["n"] == 3
    assert len(events) == 1
    err = events[0]
    assert err["type"] == "error"
    assert err.get("error_kind") == "content_filter"
    assert err.get("non_retryable") is True


@pytest.mark.asyncio
async def test_recovery_stages_succeed_in_first_stage(temp_config_file: str) -> None:
    """The cheaper ``tool_results_only`` stage runs first; if it succeeds,
    the more aggressive stage is not attempted."""
    service = LiteLLMService(config_path=temp_config_file)

    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "tool", "content": "raw snippet"},
        {"role": "user", "content": "u2"},
    ]

    call_count = {"n": 0}

    async def fake_acompletion(**_kwargs: Any) -> Any:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError(_CONTENT_FILTER_MSG)
        return _stream_of(_content_chunk("ok", finish_reason="stop"))

    with patch(
        "taskforce.infrastructure.llm.litellm_service.litellm.acompletion",
        side_effect=fake_acompletion,
    ):
        events = [evt async for evt in service.complete_stream(messages=messages)]

    # Primary + first-stage recovery only — second stage never runs.
    assert call_count["n"] == 2
    assert any(e.get("type") == "done" for e in events)


@pytest.mark.asyncio
async def test_rephrase_stage_off_by_default(temp_config_file: str) -> None:
    """Without ``recover_via_rephrase=True`` the rephrase stage never fires."""
    service = LiteLLMService(config_path=temp_config_file)

    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "tool", "content": "raw"},
        {"role": "user", "content": "u2"},
    ]

    call_count = {"n": 0}

    async def fake_acompletion(**_kwargs: Any) -> Any:
        call_count["n"] += 1
        raise RuntimeError(_CONTENT_FILTER_MSG)

    with patch(
        "taskforce.infrastructure.llm.litellm_service.litellm.acompletion",
        side_effect=fake_acompletion,
    ):
        _ = [evt async for evt in service.complete_stream(messages=messages)]

    # Primary + 2 staged retries — no rephrase call (would be a 4th).
    assert call_count["n"] == 3


@pytest.mark.asyncio
async def test_rephrase_stage_runs_when_enabled(temp_config_file: str) -> None:
    """With ``recover_via_rephrase=True`` the rephrase stage runs after both
    strip stages fail. The rephrase makes one extra LLM call (no tools,
    no streaming) and then re-streams the rebuilt message list."""
    service = LiteLLMService(
        config_path=temp_config_file,
        recover_via_rephrase=True,
    )

    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "Iran-USA Krise: zähle ORF-Artikel"},
        {"role": "assistant", "content": "a1"},
        {"role": "tool", "content": "raw"},
        {"role": "user", "content": "Iran-USA Krise: zähle ORF-Artikel"},
    ]

    call_count = {"streams": 0, "rephrase": 0}

    rephrase_choice = MagicMock()
    rephrase_choice.message = MagicMock(content="Bitte zähle Artikel pro Tag.")
    rephrase_response = MagicMock()
    rephrase_response.choices = [rephrase_choice]

    async def fake_acompletion(**kwargs: Any) -> Any:
        # The rephrase call is non-streaming and uses tools=None +
        # max_tokens=200 — distinguish via kwargs.
        if kwargs.get("max_tokens") == 200 and "tools" not in kwargs:
            call_count["rephrase"] += 1
            return rephrase_response
        call_count["streams"] += 1
        if call_count["streams"] <= 3:
            raise RuntimeError(_CONTENT_FILTER_MSG)
        return _stream_of(_content_chunk("ok", finish_reason="stop"))

    with patch(
        "taskforce.infrastructure.llm.litellm_service.litellm.acompletion",
        side_effect=fake_acompletion,
    ):
        events = [evt async for evt in service.complete_stream(messages=messages)]

    # 1 rephrase LLM call + 4 stream attempts (primary + tool_only + aggressive + rephrased)
    assert call_count["rephrase"] == 1
    assert call_count["streams"] == 4
    assert any(e.get("type") == "done" for e in events)


@pytest.mark.asyncio
async def test_no_recovery_when_history_cannot_be_stripped(temp_config_file: str) -> None:
    """If stripping doesn't reduce message count, skip recovery and surface immediately."""
    service = LiteLLMService(config_path=temp_config_file)

    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "u1"},
    ]

    call_count = {"n": 0}

    async def fake_acompletion(**_kwargs: Any) -> Any:
        call_count["n"] += 1
        raise RuntimeError(_CONTENT_FILTER_MSG)

    with patch(
        "taskforce.infrastructure.llm.litellm_service.litellm.acompletion",
        side_effect=fake_acompletion,
    ):
        events = [evt async for evt in service.complete_stream(messages=messages)]

    assert call_count["n"] == 1
    assert len(events) == 1
    assert events[0].get("error_kind") == "content_filter"


@pytest.mark.asyncio
async def test_non_content_filter_error_does_not_trigger_recovery(temp_config_file: str) -> None:
    """Generic errors must not enter the recovery branch."""
    service = LiteLLMService(config_path=temp_config_file)

    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "tool", "content": "t1"},
        {"role": "user", "content": "u2"},
    ]

    call_count = {"n": 0}

    async def fake_acompletion(**_kwargs: Any) -> Any:
        call_count["n"] += 1
        raise RuntimeError("upstream connection reset")

    with patch(
        "taskforce.infrastructure.llm.litellm_service.litellm.acompletion",
        side_effect=fake_acompletion,
    ):
        events = [evt async for evt in service.complete_stream(messages=messages)]

    assert call_count["n"] == 1
    assert len(events) == 1
    err = events[0]
    assert err["type"] == "error"
    assert "non_retryable" not in err
    assert "error_kind" not in err


@pytest.mark.asyncio
async def test_successful_first_attempt_does_not_strip(temp_config_file: str) -> None:
    """Sanity: a clean stream goes through unchanged."""
    service = LiteLLMService(config_path=temp_config_file)

    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "u1"},
    ]

    call_count = {"n": 0}

    async def fake_acompletion(**_kwargs: Any) -> Any:
        call_count["n"] += 1
        return _stream_of(_content_chunk("OK", finish_reason="stop"))

    with patch(
        "taskforce.infrastructure.llm.litellm_service.litellm.acompletion",
        side_effect=fake_acompletion,
    ):
        events = [evt async for evt in service.complete_stream(messages=messages)]

    assert call_count["n"] == 1
    types = [e.get("type") for e in events]
    assert "error" not in types
    assert "done" in types
