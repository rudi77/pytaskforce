"""Unit tests for agent deployment routes."""

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from taskforce.api.server import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_deploy_and_active(client):
    response = client.post(
        "/api/v1/agents/coding-agent/deploy",
        json={"version": "1.2.3", "environment": "staging", "message": "Promote"},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["version"] == "1.2.3"
    assert payload["environment"] == "staging"

    active = client.get("/api/v1/agents/coding-agent/active")
    assert active.status_code == 200
    assert active.json()["version"] == "1.2.3"


def test_list_and_rollback(client):
    client.post(
        "/api/v1/agents/reviewer/deploy",
        json={"version": "2.0.0", "environment": "production"},
    )

    rollback = client.post(
        "/api/v1/agents/reviewer/rollback",
        json={"version": "1.9.9", "environment": "production"},
    )
    assert rollback.status_code == 200
    assert rollback.json()["status"] == "rolled_back"

    history = client.get("/api/v1/agents/reviewer/deployments")
    assert history.status_code == 200
    assert len(history.json()["deployments"]) >= 2


def test_active_not_found_uses_error_response(client):
    response = client.get("/api/v1/agents/missing-agent/active")
    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "deployment_not_found"
    assert "message" in payload
