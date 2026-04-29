"""Tests for the Phase-5 analytics + runs endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from taskforce.api.server import create_app
from taskforce.application import run_registry, token_ledger
from taskforce.application.pricing import (
    ModelPrice,
    PricingTable,
    reset_pricing_table,
)


@pytest.fixture
def ledger(tmp_path: Path):
    db_path = tmp_path / "analytics.db"
    table = PricingTable(
        models={"azure/gpt-5.4-mini": ModelPrice(0.15, 0.60)},
        default=ModelPrice(1.0, 3.0),
        as_of="2026-04-29",
    )
    reset_pricing_table()
    ledger = token_ledger.TokenLedger(db_path=db_path, pricing=table)
    token_ledger._ledger = ledger  # type: ignore[attr-defined]
    yield ledger
    token_ledger.reset_token_ledger()
    reset_pricing_table()


@pytest.fixture
def registry():
    run_registry.reset_run_registry()
    yield run_registry.get_run_registry()
    run_registry.reset_run_registry()


@pytest.fixture
def client(ledger, registry):
    return TestClient(create_app())


def _seed(ledger: token_ledger.TokenLedger, when: datetime, **kwargs):
    return ledger.record(
        timestamp=when,
        model=kwargs.pop("model", "azure/gpt-5.4-mini"),
        prompt_tokens=kwargs.pop("prompt_tokens", 1000),
        completion_tokens=kwargs.pop("completion_tokens", 200),
        session_id=kwargs.pop("session_id", "sess-1"),
        agent_id=kwargs.pop("agent_id", "butler"),
        conversation_id=kwargs.pop("conversation_id", "conv-1"),
        profile=kwargs.pop("profile", "butler"),
    )


def test_pricing_uses_per_million_rate(ledger):
    entry = _seed(ledger, datetime.now(UTC))
    # 1000 prompt @ 0.15/M + 200 completion @ 0.60/M = 0.00015 + 0.00012 = 0.00027
    assert entry is not None
    assert entry.cost_usd == pytest.approx(0.00027, rel=1e-3)


def test_token_usage_buckets_per_day(client, ledger):
    today = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    _seed(ledger, today, prompt_tokens=500, completion_tokens=100)
    _seed(ledger, today, prompt_tokens=300, completion_tokens=80)
    _seed(ledger, yesterday, prompt_tokens=2000, completion_tokens=400)

    response = client.get("/api/v1/analytics/token-usage")
    assert response.status_code == 200
    body = response.json()
    assert body["granularity"] == "day"
    buckets = {b["bucket"]: b for b in body["buckets"]}
    assert today.strftime("%Y-%m-%d") in buckets
    assert buckets[today.strftime("%Y-%m-%d")]["prompt_tokens"] == 800
    assert buckets[today.strftime("%Y-%m-%d")]["call_count"] == 2


def test_cost_summary_aggregates(client, ledger):
    now = datetime.now(UTC)
    _seed(ledger, now, agent_id="alpha", model="azure/gpt-5.4-mini")
    _seed(ledger, now, agent_id="beta", model="anthropic/claude-opus-4-7", prompt_tokens=200, completion_tokens=50)

    response = client.get("/api/v1/analytics/cost-summary")
    assert response.status_code == 200
    body = response.json()
    assert body["pricing_as_of"] == "2026-04-29"
    agents = {a["agent"] for a in body["by_agent"]}
    assert {"alpha", "beta"} <= agents
    models = {m["model"] for m in body["by_model"]}
    assert "azure/gpt-5.4-mini" in models


def test_conversation_usage(client, ledger):
    _seed(ledger, datetime.now(UTC), conversation_id="conv-X", prompt_tokens=750, completion_tokens=150)
    response = client.get("/api/v1/analytics/conversations/conv-X/usage")
    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == "conv-X"
    assert body["total_prompt"] == 750
    assert body["total_completion"] == 150
    assert len(body["calls"]) == 1


def test_active_runs_endpoint(client, registry):
    registry.register("sess-A", profile="butler", agent_id="alpha", mission="Hello")
    registry.update_tokens("sess-A", prompt_delta=100, completion_delta=50, cost_delta=0.001)
    response = client.get("/api/v1/runs/active")
    assert response.status_code == 200
    body = response.json()
    assert len(body["runs"]) == 1
    run = body["runs"][0]
    assert run["session_id"] == "sess-A"
    assert run["profile"] == "butler"
    assert run["prompt_tokens"] == 100
    assert run["total_tokens"] == 150
    assert run["cost_usd"] == pytest.approx(0.001)


def test_active_runs_empty(client, registry):
    response = client.get("/api/v1/runs/active")
    assert response.status_code == 200
    assert response.json() == {"runs": []}
