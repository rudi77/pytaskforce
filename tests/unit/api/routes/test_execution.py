"""Unit tests for the execution routes."""

import json
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from taskforce.api.dependencies import get_executor
from taskforce.api.server import create_app
from taskforce.core.domain.enums import EventType
from taskforce.core.domain.errors import LLMError, PlanningError, ToolError
from taskforce.core.domain.models import ExecutionResult


def _mock_result(**overrides):
    defaults = {
        "status": "completed",
        "session_id": "test-session-123",
        "final_message": "Done!",
        "execution_history": [],
    }
    defaults.update(overrides)
    return ExecutionResult(**defaults)


def _make_client(mock_executor):
    """Create a TestClient with a mock executor dependency override."""
    app = create_app()
    app.dependency_overrides[get_executor] = lambda: mock_executor
    return TestClient(app), app


class TestExecuteMission:
    """Tests for POST /api/v1/execute."""

    def test_execute_success(self):
        mock_executor = AsyncMock()
        mock_executor.execute_mission = AsyncMock(return_value=_mock_result())
        client, app = _make_client(mock_executor)

        response = client.post(
            "/api/v1/execute",
            json={"mission": "Say hello"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["session_id"] == "test-session-123"
        assert body["status"] == "completed"
        assert body["message"] == "Done!"
        app.dependency_overrides.clear()

    def test_execute_missing_mission_returns_422(self):
        mock_executor = AsyncMock()
        client, app = _make_client(mock_executor)
        response = client.post("/api/v1/execute", json={})
        assert response.status_code == 422
        app.dependency_overrides.clear()

    def test_execute_file_not_found_returns_404(self):
        mock_executor = AsyncMock()
        mock_executor.execute_mission = AsyncMock(
            side_effect=FileNotFoundError("Profile not found: unknown")
        )
        client, app = _make_client(mock_executor)

        response = client.post(
            "/api/v1/execute",
            json={"mission": "test"},
        )

        assert response.status_code == 404
        body = response.json()
        assert body["code"] == "profile_not_found"
        app.dependency_overrides.clear()

    def test_execute_value_error_returns_400(self):
        mock_executor = AsyncMock()
        mock_executor.execute_mission = AsyncMock(
            side_effect=ValueError("Invalid agent definition")
        )
        client, app = _make_client(mock_executor)

        response = client.post(
            "/api/v1/execute",
            json={"mission": "test"},
        )

        assert response.status_code == 400
        body = response.json()
        assert body["code"] == "invalid_request"
        app.dependency_overrides.clear()

    def test_execute_llm_error_returns_502(self):
        mock_executor = AsyncMock()
        mock_executor.execute_mission = AsyncMock(
            side_effect=LLMError("Rate limit exceeded")
        )
        client, app = _make_client(mock_executor)

        response = client.post(
            "/api/v1/execute",
            json={"mission": "test"},
        )

        assert response.status_code == 502
        body = response.json()
        assert "code" in body
        assert "message" in body
        app.dependency_overrides.clear()

    def test_execute_planning_error_returns_400(self):
        mock_executor = AsyncMock()
        mock_executor.execute_mission = AsyncMock(
            side_effect=PlanningError("Plan generation failed")
        )
        client, app = _make_client(mock_executor)

        response = client.post(
            "/api/v1/execute",
            json={"mission": "test"},
        )

        assert response.status_code == 400
        app.dependency_overrides.clear()

    def test_execute_generic_error_returns_500(self):
        mock_executor = AsyncMock()
        mock_executor.execute_mission = AsyncMock(
            side_effect=RuntimeError("Unexpected")
        )
        client, app = _make_client(mock_executor)

        response = client.post(
            "/api/v1/execute",
            json={"mission": "test"},
        )

        assert response.status_code == 500
        body = response.json()
        assert body["code"] == "internal_server_error"
        app.dependency_overrides.clear()

    def test_error_response_has_standardized_format(self):
        mock_executor = AsyncMock()
        mock_executor.execute_mission = AsyncMock(
            side_effect=LLMError("Rate limit")
        )
        client, app = _make_client(mock_executor)

        response = client.post(
            "/api/v1/execute",
            json={"mission": "test"},
        )

        body = response.json()
        assert "code" in body
        assert "message" in body
        app.dependency_overrides.clear()


class TestExecuteStream:
    """Tests for POST /api/v1/execute/stream."""

    def test_stream_returns_sse_content_type(self):
        from taskforce.application.executor import ProgressUpdate

        async def mock_stream(*args, **kwargs):
            yield ProgressUpdate(
                timestamp=datetime.now(),
                event_type=EventType.STARTED,
                message="Starting",
                details={"session_id": "s1"},
            )
            yield ProgressUpdate(
                timestamp=datetime.now(),
                event_type=EventType.COMPLETE,
                message="Done",
                details={"status": "completed"},
            )

        mock_executor = AsyncMock()
        mock_executor.execute_mission_streaming = mock_stream
        client, app = _make_client(mock_executor)

        with client.stream(
            "POST",
            "/api/v1/execute/stream",
            json={"mission": "test"},
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
        app.dependency_overrides.clear()

    def test_stream_missing_mission_returns_422(self):
        mock_executor = AsyncMock()
        client, app = _make_client(mock_executor)
        response = client.post("/api/v1/execute/stream", json={})
        assert response.status_code == 422
        app.dependency_overrides.clear()
