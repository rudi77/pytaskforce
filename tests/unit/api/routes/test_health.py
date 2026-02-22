"""Unit tests for the health check routes."""

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from taskforce.api.server import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_liveness_returns_healthy(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["version"] == "1.0.0"


def test_readiness_returns_ready(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["version"] == "1.0.0"
    assert "checks" in body
    assert "tool_registry" in body["checks"]
    assert body["checks"]["tool_registry"].startswith("ok")
