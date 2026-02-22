"""Unit tests for the sessions routes."""

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from taskforce.api.server import create_app


def _mock_factory():
    """Create a mock AgentFactory that returns a mock agent."""
    factory = MagicMock()
    agent = AsyncMock()
    agent.state_manager = AsyncMock()
    agent.state_manager.list_sessions = AsyncMock(return_value=["s1", "s2"])
    agent.state_manager.load_state = AsyncMock(
        return_value={
            "mission": "Test mission",
            "status": "completed",
            "created_at": "2025-01-01T00:00:00",
        }
    )
    agent.state_manager.save_state = AsyncMock()
    agent.close = AsyncMock()
    factory.create_agent = AsyncMock(return_value=agent)
    return factory, agent


@pytest.fixture
def client():
    factory, _ = _mock_factory()
    app = create_app()
    from taskforce.api.dependencies import get_factory

    app.dependency_overrides[get_factory] = lambda: factory
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def mock_agent():
    _, agent = _mock_factory()
    return agent


class TestListSessions:
    """Tests for GET /api/v1/sessions."""

    def test_list_sessions_requires_profile(self, client):
        response = client.get("/api/v1/sessions")
        assert response.status_code == 422

    def test_list_sessions_success(self, client):
        response = client.get("/api/v1/sessions", params={"profile": "dev"})
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 2

    def test_list_sessions_profile_not_found(self):
        factory = MagicMock()
        factory.create_agent = AsyncMock(
            side_effect=FileNotFoundError("Profile not found: unknown")
        )
        app = create_app()
        from taskforce.api.dependencies import get_factory

        app.dependency_overrides[get_factory] = lambda: factory
        client = TestClient(app)
        response = client.get(
            "/api/v1/sessions", params={"profile": "unknown"}
        )
        assert response.status_code == 404
        body = response.json()
        assert body["code"] == "profile_not_found"
        app.dependency_overrides.clear()


class TestGetSession:
    """Tests for GET /api/v1/sessions/{session_id}."""

    def test_get_session_success(self, client):
        response = client.get(
            "/api/v1/sessions/s1", params={"profile": "dev"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["session_id"] == "s1"
        assert body["status"] == "completed"

    def test_get_session_not_found(self):
        factory = MagicMock()
        agent = AsyncMock()
        agent.state_manager = AsyncMock()
        agent.state_manager.load_state = AsyncMock(return_value=None)
        agent.close = AsyncMock()
        factory.create_agent = AsyncMock(return_value=agent)

        app = create_app()
        from taskforce.api.dependencies import get_factory

        app.dependency_overrides[get_factory] = lambda: factory
        client = TestClient(app)
        response = client.get(
            "/api/v1/sessions/nonexistent", params={"profile": "dev"}
        )
        assert response.status_code == 404
        body = response.json()
        assert body["code"] == "session_not_found"
        app.dependency_overrides.clear()


class TestCreateSession:
    """Tests for POST /api/v1/sessions."""

    def test_create_session_success(self, client):
        response = client.post(
            "/api/v1/sessions",
            params={"profile": "dev", "mission": "New mission"},
        )
        assert response.status_code == 200
        body = response.json()
        assert "session_id" in body
        assert body["mission"] == "New mission"
        assert body["status"] == "created"
