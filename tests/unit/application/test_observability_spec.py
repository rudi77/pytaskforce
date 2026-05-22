"""Spec-coverage tests for observability — token analytics + Phoenix tracing.

Spec: docs/spec/observability.md — tests tagged @pytest.mark.spec("observability.*").
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from taskforce.application import token_ledger
from taskforce.infrastructure.tracing import phoenix_tracer
from taskforce.infrastructure.tracing.phoenix_tracer import (
    TracingConfig,
    get_tracer,
    init_tracing,
    shutdown_tracing,
)


@pytest.fixture
def ledger(tmp_path: Path) -> token_ledger.TokenLedger:
    return token_ledger.TokenLedger(db_path=tmp_path / "analytics.db")


# ---------------------------------------------------------------------------
# Token ledger
# ---------------------------------------------------------------------------


@pytest.mark.spec("observability.token_ledger_swallows_sqlite_errors")
def test_token_ledger_swallows_sqlite_errors(ledger: token_ledger.TokenLedger) -> None:
    """A sqlite failure in the write path returns None, never raises."""
    ledger._connect = MagicMock(side_effect=sqlite3.OperationalError("disk I/O error"))

    result = ledger.record(
        timestamp=datetime(2026, 5, 1, tzinfo=UTC),
        model="azure/gpt-5.4-mini",
        prompt_tokens=100,
        completion_tokens=20,
    )
    # A corrupt / locked ledger never breaks an agent run.
    assert result is None


@pytest.mark.spec("observability.cost_summary_returns_zeros_on_empty_db")
def test_cost_summary_returns_zeros_on_empty_db(ledger: token_ledger.TokenLedger) -> None:
    """cost_summary returns the three rollups as zeros on a fresh ledger."""
    summary = ledger.cost_summary()
    assert summary.today_usd == 0.0
    assert summary.week_usd == 0.0
    assert summary.month_usd == 0.0
    assert summary.by_agent == []
    assert summary.by_model == []


@pytest.mark.spec("observability.token_usage_buckets_by_granularity")
def test_token_usage_buckets_by_granularity(ledger: token_ledger.TokenLedger) -> None:
    """aggregate_by_period buckets recorded calls by the requested granularity."""
    for hour in (9, 10):
        ledger.record(
            timestamp=datetime(2026, 5, 1, hour, 0, tzinfo=UTC),
            model="azure/gpt-5.4-mini",
            prompt_tokens=100,
            completion_tokens=20,
        )

    # Day granularity → both calls fall in one bucket.
    day_buckets = ledger.aggregate_by_period(granularity="day")
    assert len(day_buckets) == 1
    assert day_buckets[0].call_count == 2

    # Hour granularity → one bucket per distinct hour.
    hour_buckets = ledger.aggregate_by_period(granularity="hour")
    assert len(hour_buckets) == 2
    assert {b.call_count for b in hour_buckets} == {1}


@pytest.mark.spec("observability.analytics_db_path_honours_env_override")
def test_analytics_db_path_honours_env_override(monkeypatch, tmp_path: Path) -> None:
    """``TASKFORCE_ANALYTICS_DB`` overrides the default ledger location."""
    custom = tmp_path / "nested" / "custom-ledger.db"
    monkeypatch.setenv("TASKFORCE_ANALYTICS_DB", str(custom))

    resolved = token_ledger._default_db_path()
    assert resolved == custom

    # And a ledger built with no explicit path lands at the override.
    monkeypatch.setattr(token_ledger, "_ledger", None, raising=False)
    built = token_ledger.TokenLedger()
    assert built.db_path == custom


# ---------------------------------------------------------------------------
# Phoenix tracing
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_tracing_globals():
    """Keep tracing module-globals clean across tests."""
    phoenix_tracer._tracer_provider = None
    phoenix_tracer._tracer = None
    yield
    phoenix_tracer._tracer_provider = None
    phoenix_tracer._tracer = None


@pytest.mark.spec("observability.tracing_disabled_when_env_false")
def test_tracing_disabled_when_env_false() -> None:
    """init_tracing with the disabled flag exports nothing and sets no tracer."""
    init_tracing(TracingConfig(enabled=False))
    assert get_tracer() is None
    assert phoenix_tracer._tracer_provider is None


@pytest.mark.spec("observability.tracing_init_noop_without_phoenix_installed")
def test_tracing_init_noop_without_phoenix_installed(monkeypatch) -> None:
    """init_tracing is a best-effort no-op when phoenix.otel cannot import."""
    # Make ``from phoenix.otel import register`` raise ImportError.
    monkeypatch.setitem(sys.modules, "phoenix.otel", None)

    # Must not raise — the server keeps starting.
    init_tracing(TracingConfig(enabled=True))
    assert get_tracer() is None


@pytest.mark.spec("observability.tracing_shutdown_flushes_before_clearing")
def test_tracing_shutdown_flushes_before_clearing() -> None:
    """shutdown_tracing force-flushes pending spans, then clears the provider."""
    provider = MagicMock()
    phoenix_tracer._tracer_provider = provider
    phoenix_tracer._tracer = MagicMock()

    shutdown_tracing()

    provider.force_flush.assert_called_once()
    # The provider is cleared after the flush.
    assert phoenix_tracer._tracer_provider is None


def test_shutdown_tracing_without_init_is_noop() -> None:
    """Calling shutdown_tracing with no provider installed does nothing."""
    phoenix_tracer._tracer_provider = None
    shutdown_tracing()  # must not raise
    assert phoenix_tracer._tracer_provider is None
