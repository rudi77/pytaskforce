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

    from taskforce.core.domain.lean_agent_components.message_sanitizer import (
        MessageSanitizer,
    )

    instance = LiteLLMService.__new__(LiteLLMService)
    instance.logger = structlog.get_logger("test")  # type: ignore[attr-defined]
    # ``_sanitizer`` is normally wired by ``LiteLLMService.__init__`` and is
    # used by the ``tool_results_only`` recovery stage to drop orphan tool
    # messages. Tests bypass __init__ via __new__, so wire it explicitly.
    instance._sanitizer = MessageSanitizer(instance.logger)  # type: ignore[attr-defined]

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


# ---------------------------------------------------------------------------
# Non-streaming _recover_from_content_filter: rephrase fallback
# ---------------------------------------------------------------------------


@pytest.fixture
def recovery_service(service: LiteLLMService) -> LiteLLMService:
    """Service with rephrase recovery enabled and stubbed prepare_request."""
    service._recover_via_rephrase = True  # type: ignore[attr-defined]
    service._recovery_keep_last_n = 2  # type: ignore[attr-defined]

    def _prepare(messages, model, tools, tool_choice, **kwargs):  # noqa: ANN001
        return (None, model or "gpt-test", {"messages": messages, "model": model or "gpt-test"})

    service._prepare_request = _prepare  # type: ignore[method-assign]
    return service


async def test_recovery_falls_through_to_rephrase_when_strip_fails(
    recovery_service: LiteLLMService,
) -> None:
    """Stage 2 (rephrase) runs when stage 1 (aggressive strip) also throws."""
    messages = [
        {"role": "system", "content": "you are helpful"},
        {"role": "user", "content": "old turn 1"},
        {"role": "assistant", "content": "old reply 1"},
        {"role": "user", "content": "register Rudi Dittrich for voting"},
    ]

    call_log: list[str] = []

    async def _attempt(_litellm_kwargs, _model, _msgs, _tools, attempt):  # noqa: ANN001
        call_log.append("strip")
        raise RuntimeError("Azure content_policy violation again")

    async def _rephrase(_messages, _resolved):  # noqa: ANN001
        call_log.append("rephrase_call")
        return [{"role": "user", "content": "submit a vote on behalf of a participant"}]

    rephrase_success: dict[str, object] = {
        "success": True,
        "content": "rephrased response",
    }

    attempt_iter = iter([_attempt, lambda *a, **kw: rephrase_success])

    async def _wrapper(*args, **kwargs):  # noqa: ANN001
        call_log.append("attempt")
        fn = next(attempt_iter)
        result = fn(*args, **kwargs)
        if hasattr(result, "__await__"):
            return await result
        return result

    recovery_service._attempt_completion = _wrapper  # type: ignore[method-assign]
    recovery_service._rephrase_user_message_for_recovery = _rephrase  # type: ignore[method-assign]

    result = await recovery_service._recover_from_content_filter(
        messages, model="main", tools=None, tool_choice=None, resolved_model="gpt-test"
    )

    assert result is rephrase_success
    # Stage 1 (strip) attempted then failed, stage 2 (rephrase) succeeded.
    assert call_log == ["attempt", "strip", "rephrase_call", "attempt"]


async def test_recovery_returns_none_when_rephrase_disabled(
    recovery_service: LiteLLMService,
) -> None:
    """When recover_via_rephrase=False, recovery stops after the strip stage."""
    recovery_service._recover_via_rephrase = False  # type: ignore[attr-defined]
    messages = [
        {"role": "system", "content": "you are helpful"},
        {"role": "user", "content": "old turn"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "current request"},
    ]

    async def _attempt(*_args, **_kwargs) -> None:
        raise RuntimeError("Azure content_policy violation")

    async def _rephrase(*_args, **_kwargs):  # noqa: ANN001
        raise AssertionError("rephrase must not be called when disabled")

    recovery_service._attempt_completion = _attempt  # type: ignore[method-assign]
    recovery_service._rephrase_user_message_for_recovery = _rephrase  # type: ignore[method-assign]

    result = await recovery_service._recover_from_content_filter(
        messages, model="main", tools=None, tool_choice=None, resolved_model="gpt-test"
    )

    assert result is None
