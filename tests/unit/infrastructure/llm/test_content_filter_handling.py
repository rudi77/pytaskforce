"""Unit tests for content-filter handling in LiteLLMService.

These tests pin the contract that content-filter errors are tagged as
``non_retryable`` so the ReAct loop can short-circuit instead of burning
the consecutive-error budget on the same blocked request.
"""

from __future__ import annotations

import pytest

from taskforce.infrastructure.llm.litellm_service import LiteLLMService


@pytest.fixture
def service() -> LiteLLMService:
    """Build a LiteLLMService without loading any config.

    ``_handle_stream_error`` does not touch the config — it only logs and
    fires a fire-and-forget trace task. We stub out tracing to keep the
    test self-contained and silence the unused-coroutine warning.
    """
    import structlog

    instance = LiteLLMService.__new__(LiteLLMService)
    instance.logger = structlog.get_logger("test")  # type: ignore[attr-defined]

    async def _noop_trace(*_args, **_kwargs) -> None:
        return None

    instance._trace_failure = _noop_trace  # type: ignore[method-assign]
    return instance


@pytest.mark.parametrize(
    "message",
    [
        "BadRequestError: content filter triggered on response",
        "Azure OpenAI returned content_policy violation",
        "Request blocked by ContentPolicy",
    ],
)
def test_is_content_filter_error_detects_known_messages(message: str) -> None:
    err = RuntimeError(message)
    assert LiteLLMService._is_content_filter_error(err) is True


def test_is_content_filter_error_ignores_unrelated_errors() -> None:
    err = RuntimeError("connection reset")
    assert LiteLLMService._is_content_filter_error(err) is False


async def test_handle_stream_error_tags_content_filter(service: LiteLLMService) -> None:
    err = RuntimeError("Azure content_policy violation: harmful content blocked")
    event = await service._handle_stream_error(err, "main", messages=[])

    assert event["type"] == "error"
    assert event.get("non_retryable") is True
    assert event.get("error_kind") == "content_filter"


async def test_handle_stream_error_does_not_tag_other_errors(
    service: LiteLLMService,
) -> None:
    err = TimeoutError("upstream timed out")
    event = await service._handle_stream_error(err, "main", messages=[])

    assert event["type"] == "error"
    assert "non_retryable" not in event
    assert "error_kind" not in event
