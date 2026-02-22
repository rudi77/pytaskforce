"""Unit tests for the agents routes."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from taskforce.api.server import create_app
from taskforce.core.domain.agent_models import (
    CustomAgentDefinition,
    ProfileAgentDefinition,
)


def _make_custom_agent(**overrides):
    defaults = {
        "agent_id": "test-agent",
        "name": "Test Agent",
        "description": "A test agent",
        "system_prompt": "You are a test agent",
        "tool_allowlist": ["python"],
        "mcp_servers": [],
        "mcp_tool_allowlist": [],
        "created_at": "2025-01-01T00:00:00+00:00",
        "updated_at": "2025-01-01T00:00:00+00:00",
    }
    defaults.update(overrides)
    return CustomAgentDefinition(**defaults)


def _make_profile_agent(**overrides):
    defaults = {
        "profile": "dev",
        "specialist": None,
        "tools": ["python", "file_read"],
        "mcp_servers": [],
        "llm": {"default_model": "main"},
        "persistence": {"type": "file"},
    }
    defaults.update(overrides)
    return ProfileAgentDefinition(**defaults)


@pytest.fixture
def mock_registry():
    """Create a mock FileAgentRegistry."""
    mock = MagicMock()
    mock.create_agent = MagicMock(return_value=_make_custom_agent())
    mock.get_agent = MagicMock(return_value=_make_custom_agent())
    mock.list_agents = MagicMock(return_value=[_make_custom_agent()])
    mock.update_agent = MagicMock(return_value=_make_custom_agent())
    mock.delete_agent = MagicMock(return_value=None)
    return mock


@pytest.fixture
def client(mock_registry):
    from taskforce.api.dependencies import get_agent_registry

    app = create_app()
    app.dependency_overrides[get_agent_registry] = lambda: mock_registry
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestCreateAgent:
    """Tests for POST /api/v1/agents."""

    def test_create_agent_success(self, client, mock_registry):
        response = client.post(
            "/api/v1/agents",
            json={
                "agent_id": "test-agent",
                "name": "Test Agent",
                "description": "A test agent",
                "system_prompt": "You are a test agent",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["agent_id"] == "test-agent"
        assert body["source"] == "custom"

    def test_create_agent_conflict(self, client, mock_registry):
        mock_registry.create_agent.side_effect = FileExistsError(
            "Agent 'test-agent' already exists"
        )
        response = client.post(
            "/api/v1/agents",
            json={
                "agent_id": "test-agent",
                "name": "Test",
                "description": "Test",
                "system_prompt": "Test",
            },
        )
        assert response.status_code == 409
        body = response.json()
        assert body["code"] == "agent_exists"
        assert "message" in body

    def test_create_agent_invalid_id(self, client):
        response = client.post(
            "/api/v1/agents",
            json={
                "agent_id": "INVALID_ID!",
                "name": "Test",
                "description": "Test",
                "system_prompt": "Test",
            },
        )
        assert response.status_code == 422

    def test_create_agent_short_id(self, client):
        response = client.post(
            "/api/v1/agents",
            json={
                "agent_id": "ab",
                "name": "Test",
                "description": "Test",
                "system_prompt": "Test",
            },
        )
        assert response.status_code == 422

    def test_create_agent_missing_fields(self, client):
        response = client.post(
            "/api/v1/agents",
            json={"agent_id": "test-agent"},
        )
        assert response.status_code == 422

    def test_create_agent_system_prompt_too_long(self, client):
        response = client.post(
            "/api/v1/agents",
            json={
                "agent_id": "test-agent",
                "name": "Test",
                "description": "Test",
                "system_prompt": "x" * 100_001,
            },
        )
        assert response.status_code == 422


class TestListAgents:
    """Tests for GET /api/v1/agents."""

    def test_list_agents_success(self, client, mock_registry):
        response = client.get("/api/v1/agents")
        assert response.status_code == 200
        body = response.json()
        assert "agents" in body
        assert len(body["agents"]) == 1

    def test_list_agents_empty(self, client, mock_registry):
        mock_registry.list_agents.return_value = []
        response = client.get("/api/v1/agents")
        assert response.status_code == 200
        assert response.json()["agents"] == []

    def test_list_agents_mixed_types(self, client, mock_registry):
        mock_registry.list_agents.return_value = [
            _make_custom_agent(),
            _make_profile_agent(),
        ]
        response = client.get("/api/v1/agents")
        body = response.json()
        assert len(body["agents"]) == 2
        sources = {a["source"] for a in body["agents"]}
        assert "custom" in sources
        assert "profile" in sources


class TestGetAgent:
    """Tests for GET /api/v1/agents/{agent_id}."""

    def test_get_agent_found(self, client, mock_registry):
        response = client.get("/api/v1/agents/test-agent")
        assert response.status_code == 200
        assert response.json()["agent_id"] == "test-agent"

    def test_get_agent_not_found(self, client, mock_registry):
        mock_registry.get_agent.return_value = None
        response = client.get("/api/v1/agents/nonexistent")
        assert response.status_code == 404
        body = response.json()
        assert body["code"] == "not_found"
        assert "message" in body


class TestUpdateAgent:
    """Tests for PUT /api/v1/agents/{agent_id}."""

    def test_update_agent_success(self, client, mock_registry):
        response = client.put(
            "/api/v1/agents/test-agent",
            json={
                "name": "Updated Agent",
                "description": "Updated",
                "system_prompt": "Updated prompt",
            },
        )
        assert response.status_code == 200

    def test_update_agent_not_found(self, client, mock_registry):
        mock_registry.update_agent.side_effect = FileNotFoundError(
            "Agent 'unknown' not found"
        )
        response = client.put(
            "/api/v1/agents/unknown",
            json={
                "name": "Updated",
                "description": "Updated",
                "system_prompt": "Updated",
            },
        )
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"


class TestDeleteAgent:
    """Tests for DELETE /api/v1/agents/{agent_id}."""

    def test_delete_agent_success(self, client, mock_registry):
        response = client.delete("/api/v1/agents/test-agent")
        assert response.status_code == 204

    def test_delete_agent_not_found(self, client, mock_registry):
        mock_registry.delete_agent.side_effect = FileNotFoundError(
            "Agent 'unknown' not found"
        )
        response = client.delete("/api/v1/agents/unknown")
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"
