"""Integration test: ``run_context`` propagates into ``per_session`` aggregations.

The eval-runner harvester relies on this chain — if it ever breaks, every
eval-result row would silently report zero tokens / zero cost.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from taskforce.application import token_ledger
from taskforce.application.pricing import (
    ModelPrice,
    PricingTable,
    reset_pricing_table,
)


@pytest.fixture
def ledger(tmp_path: Path):
    table = PricingTable(
        models={"azure/gpt-5.4-mini": ModelPrice(0.15, 0.60)},
        default=ModelPrice(1.0, 3.0),
        as_of="2026-04-30",
    )
    reset_pricing_table()
    inst = token_ledger.TokenLedger(db_path=tmp_path / "analytics.db", pricing=table)
    token_ledger._ledger = inst  # type: ignore[attr-defined]
    yield inst
    token_ledger.reset_token_ledger()
    reset_pricing_table()


def _record(ledger: token_ledger.TokenLedger) -> None:
    ledger.record(
        timestamp=datetime(2026, 4, 30, tzinfo=UTC),
        model="azure/gpt-5.4-mini",
        prompt_tokens=1000,
        completion_tokens=200,
    )


@pytest.mark.spec("observability.token_ledger_attaches_run_context")
def test_per_session_aggregates_records_made_inside_run_context(ledger) -> None:
    with token_ledger.run_context(
        session_id="sess-eval-1",
        agent_id="butler",
        profile="butler",
    ):
        _record(ledger)
        _record(ledger)

    agg = ledger.per_session("sess-eval-1")
    assert agg["session_id"] == "sess-eval-1"
    assert agg["prompt_tokens"] == 2000
    assert agg["completion_tokens"] == 400
    # 2000 prompt × $0.15/1M = $0.0003; 400 completion × $0.60/1M = $0.00024;
    # total cost across both calls = $0.00054.
    assert agg["cost_usd"] == pytest.approx(0.00054, abs=1e-6)


def test_per_session_returns_zero_for_unknown_session(ledger) -> None:
    agg = ledger.per_session("never-recorded")
    assert agg["prompt_tokens"] == 0
    assert agg["completion_tokens"] == 0
    assert agg["cost_usd"] == 0.0


def test_run_context_reset_after_block(ledger) -> None:
    """After leaving the context, new records should not be tagged with the prior session."""
    with token_ledger.run_context(session_id="sess-A"):
        _record(ledger)
    _record(ledger)  # outside context — has no session_id

    inside = ledger.per_session("sess-A")
    assert inside["prompt_tokens"] == 1000

    # The second call has session_id="" so per_session("") would return its row;
    # confirm it didn't bleed into sess-A.
    assert inside["completion_tokens"] == 200
