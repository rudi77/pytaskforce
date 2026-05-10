"""Tests for LiteLLMService transient-failure retry classification (issue #156).

The Butler daemon runs unattended for days, so it must:

- retry transient LLM/network failures (rate-limit, 429, 502/503,
  timeouts) so a 30-second cloud blip does not poison a scheduled job;
- NOT retry permanent 4xx errors (auth, quota, invalid model) so a
  rotated API key doesn't burn through retry budget every minute.

We exercise the static ``_should_retry`` classifier directly so the
test stays fast and provider-independent.
"""

from __future__ import annotations

import pytest

from taskforce.infrastructure.llm.litellm_service import LiteLLMService


class _FakeProviderError(Exception):
    """Generic stand-in for provider exceptions in classification tests."""


class RateLimitError(Exception):
    """Mimics LiteLLM/OpenAI's RateLimitError class name."""


class APIConnectionError(Exception):
    """Mimics LiteLLM/OpenAI's APIConnectionError class name."""


class Timeout(Exception):
    """Mimics LiteLLM/OpenAI's Timeout class name."""


class ServiceUnavailableError(Exception):
    """Mimics LiteLLM/OpenAI's ServiceUnavailableError class name."""


@pytest.mark.parametrize(
    "exc",
    [
        RateLimitError("rate limit exceeded"),
        APIConnectionError("connection reset by peer"),
        Timeout("request timed out"),
        ServiceUnavailableError("503 service unavailable"),
        _FakeProviderError("502 bad gateway"),
        _FakeProviderError("429 too many requests"),
        _FakeProviderError("upstream overloaded, please retry"),
    ],
)
def test_transient_errors_are_retryable(exc: Exception) -> None:
    """Network blips and rate-limits must be classified as retryable."""
    assert LiteLLMService._should_retry(exc) is True


@pytest.mark.parametrize(
    "exc",
    [
        _FakeProviderError("invalid api key provided"),
        _FakeProviderError("Authentication failed: missing bearer token"),
        _FakeProviderError("401 Unauthorized"),
        _FakeProviderError("403 Forbidden: permission denied"),
        _FakeProviderError("model not found: gpt-99-turbo"),
        _FakeProviderError("invalid model: claude-doesnt-exist"),
        _FakeProviderError("invalid request: messages must be non-empty"),
        _FakeProviderError("insufficient_quota: please add billing"),
        _FakeProviderError("quota exceeded for organisation"),
        _FakeProviderError("billing hard-limit reached"),
    ],
)
def test_permanent_errors_are_not_retryable(exc: Exception) -> None:
    """4xx auth/quota errors must NOT trigger the retry path."""
    assert LiteLLMService._should_retry(exc) is False


def test_non_retryable_keywords_take_priority_over_retryable_signal() -> None:
    """A message containing both must be classified as non-retryable.

    If a provider returns 'Authentication failed (rate limit handler)'
    the auth error is what the operator needs to fix, retrying makes
    things worse. The classifier must let the non-retryable keyword win.
    """
    err = _FakeProviderError("Authentication failed: rate limit handler error")
    assert LiteLLMService._should_retry(err) is False
