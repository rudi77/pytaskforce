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
    # version is dynamic (from package metadata or "0.0.0-dev")
    assert "version" in body
    assert isinstance(body["version"], str)


def test_health_exposes_default_profile(client):
    """UI uses ``default_profile`` so chat doesn't hardcode butler."""
    response = client.get("/health")
    body = response.json()
    assert "default_profile" in body
    # Either ``butler`` (when taskforce_butler is installed) or ``default``.
    assert body["default_profile"] in {"butler", "default"}


def test_readiness_returns_ready(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert "version" in body
    assert "checks" in body
    assert "tool_registry" in body["checks"]
    assert body["checks"]["tool_registry"].startswith("ok")
