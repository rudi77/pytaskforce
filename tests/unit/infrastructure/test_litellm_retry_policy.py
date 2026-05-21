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
        # Status-code-driven classification (issue #191 sub-item c):
        # provider errors typically include both a status and a body.
        _FakeProviderError("404 model not found: gpt-99-turbo"),
        _FakeProviderError("invalid model: claude-doesnt-exist"),
        _FakeProviderError("invalid request: messages must be non-empty"),
        _FakeProviderError("insufficient_quota: please add billing"),
        _FakeProviderError("quota exceeded for organisation"),
        _FakeProviderError("402 billing hard-limit reached"),
    ],
)
@pytest.mark.spec("llm-service.auth_errors_are_non_retryable")
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


# ---------------------------------------------------------------------------
# Issue #191 sub-item (c) — spurious-keyword 5xx bodies must stay retryable.
# Plain substring matching on "billing" / "forbidden" / "not found" used to
# trip the non-retryable branch on 5xx errors that merely *mention* those
# words in their body (operator advice strings, log lines, etc.).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        # Real-world Azure 503 with a billing-related retry hint in the body.
        _FakeProviderError(
            "503 service unavailable: billing service degraded, retry in 30s"
        ),
        # Transient stream-decoder hiccup that mentions "forbidden" in its
        # diagnostic — used to trip the keyword filter.
        _FakeProviderError(
            "502 bad gateway: forbidden character in stream chunk, retrying"
        ),
        # A 5xx whose body just happens to include the word "not found"
        # (operator log line, not the real cause). Must remain retryable.
        _FakeProviderError(
            "503 service unavailable: upstream pod not found, scheduling restart"
        ),
        # 429 with a billing-related message — the rate-limit status must
        # win over the "billing" substring.
        _FakeProviderError(
            "429 too many requests for billing tier free"
        ),
    ],
)
@pytest.mark.spec("llm-service.transient_5xx_with_4xx_in_body_stays_retryable")
def test_spurious_keyword_in_5xx_body_stays_retryable(exc: Exception) -> None:
    """5xx errors whose body merely *mentions* a previously-classified
    non-retryable keyword must stay retryable. Pinning the fix from
    #191 sub-item (c)."""
    assert LiteLLMService._should_retry(exc) is True


def test_402_billing_status_still_non_retryable() -> None:
    """The status-code regex catches genuine billing rejections (402)."""
    err = _FakeProviderError("402 payment required: billing limit exceeded")
    assert LiteLLMService._should_retry(err) is False


def test_403_forbidden_status_still_non_retryable_without_keyword() -> None:
    """A 403 with no extra keyword body still hits the status regex."""
    err = _FakeProviderError("403 access denied by api gateway policy")
    assert LiteLLMService._should_retry(err) is False


def test_404_status_still_non_retryable_without_keyword() -> None:
    """A 404 stays permanent via the status code, even though the
    'not found' keyword was removed."""
    err = _FakeProviderError("404 the requested model does not exist")
    assert LiteLLMService._should_retry(err) is False
