"""Spec-coverage tests for content-filter recovery.

Covers the two claims in ``docs/spec/content-filter-recovery.md`` that
lacked a focused test: the ``aggressive`` strip's ``recovery_keep_last_n``
window, and that both the blocking and streaming paths run a recovery
cascade for the same content-filter error.

Spec: docs/spec/content-filter-recovery.md — tests tagged
@pytest.mark.spec("content-filter-recovery.*").
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
import yaml

from taskforce.infrastructure.llm.litellm_service import LiteLLMService

_CONTENT_FILTER_MSG = (
    "litellm.ContentPolicyViolationError: AzureException - The response was "
    "filtered due to the prompt triggering Azure OpenAI's content management policy."
)


@pytest.fixture
def config_file(tmp_path) -> str:
    config = {
        "default_model": "main",
        "models": {"main": "gpt-test"},
        "model_params": {"gpt-test": {"temperature": 0.0, "max_tokens": 100}},
        "default_params": {"temperature": 0.7, "max_tokens": 200},
        "retry": {"max_attempts": 1, "backoff_multiplier": 2, "timeout": 30},
        "logging": {"log_token_usage": False},
    }
    path = tmp_path / "llm_config.yaml"
    path.write_text(yaml.dump(config), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# aggressive strip window
# ---------------------------------------------------------------------------


@pytest.mark.spec("content-filter-recovery.aggressive_strip_keeps_recovery_keep_last_n_turns")
def test_aggressive_strip_keeps_recovery_keep_last_n_turns(config_file: str) -> None:
    """The ``aggressive`` strip keeps system + the last N plain turns only."""
    service = LiteLLMService(config_path=config_file, recovery_keep_last_n=2)

    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "tool", "content": "t1"},  # dropped — not a plain turn
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "u3"},
    ]

    stripped = service._strip_messages_for_content_recovery(messages, mode="aggressive")

    # System prompt is always retained …
    assert stripped[0] == {"role": "system", "content": "sys"}
    # … plus exactly the last 2 plain user/assistant turns (tool turn excluded).
    assert [m["content"] for m in stripped[1:]] == ["a2", "u3"]


@pytest.mark.spec("content-filter-recovery.aggressive_strip_keeps_recovery_keep_last_n_turns")
def test_aggressive_strip_keep_last_n_floored_at_one(config_file: str) -> None:
    """``recovery_keep_last_n`` is floored at 1 even when configured lower."""
    service = LiteLLMService(config_path=config_file, recovery_keep_last_n=0)

    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u1"},
        {"role": "user", "content": "u2"},
    ]
    stripped = service._strip_messages_for_content_recovery(messages, mode="aggressive")

    assert stripped[0]["role"] == "system"
    assert [m["content"] for m in stripped[1:]] == ["u2"]


# ---------------------------------------------------------------------------
# blocking + streaming both run a recovery cascade
# ---------------------------------------------------------------------------


@pytest.mark.spec("content-filter-recovery.complete_and_complete_stream_run_same_cascade")
@pytest.mark.asyncio
async def test_complete_and_complete_stream_run_same_cascade(config_file: str) -> None:
    """Both ``complete()`` and ``complete_stream()`` run a recovery cascade.

    Faced with the same content-filter error, both paths retry on a
    stripped history rather than failing on the first block — i.e. both
    issue more than one upstream LLM call. (The exact stage *count*
    differs between the two paths — see the documented Known gap in
    content-filter-recovery.md — so this test pins the shared invariant:
    both run the cascade, neither gives up on the first filter.)
    """
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "tool", "content": "raw snippet"},
        {"role": "user", "content": "u2"},
    ]

    # --- blocking path -----------------------------------------------------
    blocking_calls = {"n": 0}

    async def blocking_acompletion(**_kwargs: Any) -> Any:
        blocking_calls["n"] += 1
        raise RuntimeError(_CONTENT_FILTER_MSG)

    blocking_service = LiteLLMService(config_path=config_file, recover_via_rephrase=False)
    with patch(
        "taskforce.infrastructure.llm.litellm_service.litellm.acompletion",
        side_effect=blocking_acompletion,
    ):
        blocking_result = await blocking_service.complete(messages=list(messages))

    assert blocking_result["success"] is False
    assert blocking_calls["n"] > 1, "complete() must retry recovery, not bail on first filter"

    # --- streaming path ----------------------------------------------------
    streaming_calls = {"n": 0}

    async def streaming_acompletion(**_kwargs: Any) -> Any:
        streaming_calls["n"] += 1
        raise RuntimeError(_CONTENT_FILTER_MSG)

    streaming_service = LiteLLMService(config_path=config_file, recover_via_rephrase=False)
    with patch(
        "taskforce.infrastructure.llm.litellm_service.litellm.acompletion",
        side_effect=streaming_acompletion,
    ):
        events = [
            evt async for evt in streaming_service.complete_stream(messages=list(messages))
        ]

    error = events[-1]
    assert error["type"] == "error"
    assert error.get("error_kind") == "content_filter"
    assert streaming_calls["n"] > 1, "complete_stream() must retry recovery too"
