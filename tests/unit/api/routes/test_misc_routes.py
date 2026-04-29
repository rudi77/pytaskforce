"""Unit tests for the lightweight Phase-2 listing routes."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from taskforce.api.server import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_planning_strategies_returns_four_entries(client: TestClient) -> None:
    response = client.get("/api/v1/planning-strategies")
    assert response.status_code == 200
    body = response.json()
    ids = {s["id"] for s in body["strategies"]}
    assert ids == {"native_react", "plan_and_execute", "plan_and_react", "spar"}


def test_llm_models_returns_default_and_aliases(client: TestClient) -> None:
    response = client.get("/api/v1/llm/models")
    assert response.status_code == 200
    body = response.json()
    assert "default_model" in body
    assert "models" in body
    if body["models"]:
        first = body["models"][0]
        assert {"alias", "model_id", "provider"} <= first.keys()


def test_skills_endpoint_returns_list(client: TestClient) -> None:
    response = client.get("/api/v1/skills")
    assert response.status_code == 200
    body = response.json()
    assert "skills" in body
    assert isinstance(body["skills"], list)
