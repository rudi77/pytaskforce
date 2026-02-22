"""Unit tests for the tools route."""

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from taskforce.api.server import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_get_tools_returns_list(client):
    response = client.get("/api/v1/tools")
    assert response.status_code == 200
    body = response.json()
    assert "tools" in body
    assert isinstance(body["tools"], list)
    assert len(body["tools"]) > 0


def test_get_tools_contains_expected_fields(client):
    response = client.get("/api/v1/tools")
    body = response.json()
    for tool in body["tools"]:
        assert "name" in tool
        assert "description" in tool
