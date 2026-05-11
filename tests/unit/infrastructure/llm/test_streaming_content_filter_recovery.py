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
    # Two recovery stages run → one stream_restart per stage, then the
    # final error event after both stages fail.
    types = [e["type"] for e in events]
    assert types == ["stream_restart", "stream_restart", "error"]
    err = events[-1]
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
        # The production rephrase call carries an explicit
        # ``metadata={"phase": "filter_recovery_rephrase"}`` sentinel
        # — assert on that instead of sniffing kwargs heuristics.
        metadata = kwargs.get("metadata") or {}
        if metadata.get("phase") == "filter_recovery_rephrase":
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


def test_tool_results_only_strip_drops_pre_existing_orphan_tool_messages(
    temp_config_file: str,
) -> None:
    """The ``tool_results_only`` strip mode must not leave behind an
    orphan ``role="tool"`` message whose matching assistant turn was
    already missing in the input. Regression for an upstream 400 we
    would otherwise hit on the recovery retry."""
    service = LiteLLMService(config_path=temp_config_file)

    # Input is malformed on purpose: a tool reply with no preceding
    # assistant ``tool_calls`` carrying its id. Today the strip mode
    # drops every tool message (so this case also collapses) — the
    # regression we're pinning is that the defensive sanitiser pass
    # is in place and would catch any future variant where the strip
    # decided to keep an orphan.
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u1"},
        {"role": "tool", "content": "orphan", "tool_call_id": "missing", "name": "x"},
        {"role": "user", "content": "u2"},
    ]

    stripped = service._strip_messages_for_content_recovery(messages, mode="tool_results_only")

    assert all(m.get("role") != "tool" for m in stripped), stripped
    # No assistant orphan tool_call should remain either.
    for m in stripped:
        if m.get("role") == "assistant":
            assert not m.get("tool_calls")


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
    # Sanity: a clean stream must NOT inject a stream_restart marker.
    assert "stream_restart" not in types


@pytest.mark.asyncio
async def test_stream_restart_emitted_before_recovery_tokens(
    temp_config_file: str,
) -> None:
    """Issue #159 sub-item (a): when a streaming attempt is truncated
    by a content filter mid-stream, consumers must be told to discard
    the partial output before the retry tokens arrive.

    Without the ``stream_restart`` marker, the failed-attempt tokens
    and the retry tokens get concatenated in the consumer's
    accumulator (half-sentence + full retry sentence).
    """
    service = LiteLLMService(config_path=temp_config_file)

    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "tool", "content": "tool snippet"},
        {"role": "user", "content": "u2"},
    ]

    async def partial_then_fail() -> Any:
        # The provider streams two tokens, then aborts with a
        # content-filter exception. The consumer sees both tokens
        # before the error propagates.
        async def gen():
            yield _content_chunk("partial ")
            yield _content_chunk("answer")
            raise RuntimeError(_CONTENT_FILTER_MSG)

        return gen()

    call_count = {"n": 0}

    async def fake_acompletion(**_kwargs: Any) -> Any:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return await partial_then_fail()
        return _stream_of(_content_chunk("recovered answer", finish_reason="stop"))

    with patch(
        "taskforce.infrastructure.llm.litellm_service.litellm.acompletion",
        side_effect=fake_acompletion,
    ):
        events = [evt async for evt in service.complete_stream(messages=messages)]

    types = [e.get("type") for e in events]

    # The partial tokens are still surfaced (we can't unsend them) but
    # are followed by a stream_restart, then the recovered tokens.
    assert types.count("stream_restart") == 1
    restart_idx = types.index("stream_restart")
    pre_restart_tokens = [
        e.get("content", "") for e in events[:restart_idx] if e.get("type") == "token"
    ]
    post_restart_tokens = [
        e.get("content", "") for e in events[restart_idx + 1 :] if e.get("type") == "token"
    ]
    assert pre_restart_tokens == ["partial ", "answer"]
    assert post_restart_tokens == ["recovered answer"]
    # A consumer that resets its accumulator on stream_restart ends up
    # with just the clean retry content.
    assert "done" in types
    assert "error" not in types


@pytest.mark.asyncio
async def test_stream_restart_carries_stage_metadata(temp_config_file: str) -> None:
    """Each ``stream_restart`` must name the recovery stage it precedes
    so consumers can log / show a meaningful reason."""
    service = LiteLLMService(config_path=temp_config_file)

    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "tool", "content": "raw tool"},
        {"role": "user", "content": "u2"},
    ]

    call_count = {"n": 0}

    async def fake_acompletion(**_kwargs: Any) -> Any:
        call_count["n"] += 1
        # primary + tool_results_only filtered, aggressive succeeds
        if call_count["n"] <= 2:
            raise RuntimeError(_CONTENT_FILTER_MSG)
        return _stream_of(_content_chunk("ok", finish_reason="stop"))

    with patch(
        "taskforce.infrastructure.llm.litellm_service.litellm.acompletion",
        side_effect=fake_acompletion,
    ):
        events = [evt async for evt in service.complete_stream(messages=messages)]

    restarts = [e for e in events if e.get("type") == "stream_restart"]
    assert len(restarts) == 2
    assert restarts[0] == {
        "type": "stream_restart",
        "reason": "content_filter",
        "stage": "tool_results_only",
    }
    assert restarts[1] == {
        "type": "stream_restart",
        "reason": "content_filter",
        "stage": "aggressive",
    }


@pytest.mark.asyncio
async def test_stream_restart_emitted_for_rephrase_stage(temp_config_file: str) -> None:
    """The optional rephrase stage must also emit a ``stream_restart``."""
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

    rephrase_choice = MagicMock()
    rephrase_choice.message = MagicMock(content="Bitte zähle Artikel pro Tag.")
    rephrase_response = MagicMock()
    rephrase_response.choices = [rephrase_choice]

    call_count = {"streams": 0}

    async def fake_acompletion(**kwargs: Any) -> Any:
        metadata = kwargs.get("metadata") or {}
        if metadata.get("phase") == "filter_recovery_rephrase":
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

    stages = [
        e["stage"] for e in events if e.get("type") == "stream_restart"
    ]
    assert stages == ["tool_results_only", "aggressive", "rephrase"]
