"""Tests for TokenAnalyticsCallback (LiteLLM integration)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import litellm
import pytest

from taskforce.infrastructure.llm.token_analytics_callback import (
    TokenAnalyticsCallback,
    get_token_analytics,
)


@pytest.fixture()
def callback():
    """Create a fresh callback and clean up after test."""
    cb = TokenAnalyticsCallback()
    yield cb
    cb.uninstall()


def _make_response(
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    total_tokens: int = 150,
    tool_calls: list | None = None,
):
    """Build a mock LiteLLM response object."""
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )
    msg = SimpleNamespace(tool_calls=tool_calls)
    choice = SimpleNamespace(message=msg)
    return SimpleNamespace(usage=usage, choices=[choice])


class TestTokenAnalyticsCallback:
    def test_install_and_get(self, callback):
        assert get_token_analytics() is None
        callback.install()
        assert get_token_analytics() is callback

    def test_uninstall(self, callback):
        callback.install()
        callback.uninstall()
        assert get_token_analytics() is None

    def test_install_idempotent(self, callback):
        callback.install()
        callback.install()
        count = sum(1 for c in litellm.callbacks if c is callback)
        assert count == 1

    def test_log_success_event(self, callback):
        kwargs = {"model": "gpt-4o"}
        response = _make_response(prompt_tokens=500, completion_tokens=100, total_tokens=600)
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 1, 0, 0, 1, tzinfo=UTC)

        callback.log_success_event(kwargs, response, start, end)

        assert len(callback.calls) == 1
        record = callback.calls[0]
        assert record.model == "gpt-4o"
        assert record.prompt_tokens == 500
        assert record.completion_tokens == 100
        assert record.total_tokens == 600
        assert record.latency_ms == 1000

    def test_log_stream_event(self, callback):
        kwargs = {"model": "claude-3"}
        response = _make_response(prompt_tokens=200, completion_tokens=80, total_tokens=280)
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 1, 0, 0, 2, tzinfo=UTC)

        callback.log_stream_event(kwargs, response, start, end)

        assert len(callback.calls) == 1
        assert callback.calls[0].model == "claude-3"
        assert callback.calls[0].latency_ms == 2000

    def test_tool_calls_captured(self, callback):
        tc = SimpleNamespace(function=SimpleNamespace(name="file_read"))
        response = _make_response(tool_calls=[tc])
        callback.log_success_event({"model": "m"}, response, None, None)

        assert callback.calls[0].tool_call_names == ["file_read"]

    def test_reset(self, callback):
        callback.log_success_event(
            {"model": "m"}, _make_response(), None, None
        )
        assert len(callback.calls) == 1
        callback.reset()
        assert len(callback.calls) == 0

    def test_build_summary(self, callback):
        callback.log_success_event(
            {"model": "gpt-4o"},
            _make_response(prompt_tokens=1000, completion_tokens=200, total_tokens=1200),
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2025, 1, 1, 0, 0, 1, tzinfo=UTC),
        )
        callback.log_success_event(
            {"model": "gpt-4o-mini"},
            _make_response(prompt_tokens=300, completion_tokens=400, total_tokens=700),
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2025, 1, 1, 0, 0, 0, 500000, tzinfo=UTC),
        )
        summary = callback.build_summary()
        assert summary.total_tokens == 1900
        assert summary.total_llm_calls == 2
        assert "gpt-4o" in summary.model_breakdown
        assert "gpt-4o-mini" in summary.model_breakdown

    def test_error_in_callback_does_not_propagate(self, callback):
        """Callback must never break LLM calls, even with bad input."""
        # Pass garbage - should not raise
        callback.log_success_event({}, None, None, None)
        # Gracefully recorded a zero-value record (model defaults to "unknown")
        assert callback.calls[0].model == "unknown"
        assert callback.calls[0].total_tokens == 0

    def test_missing_usage(self, callback):
        """Handle response without usage gracefully."""
        response = SimpleNamespace(usage=None, choices=[])
        callback.log_success_event({"model": "m"}, response, None, None)
        assert callback.calls[0].total_tokens == 0
