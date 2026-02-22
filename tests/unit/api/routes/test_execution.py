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


@pytest.fixture
def mock_executor():
    return AsyncMock()


@pytest.fixture
def client(mock_executor):
    """Create a TestClient with a mock executor dependency override."""
    app = create_app()
    app.dependency_overrides[get_executor] = lambda: mock_executor
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestExecuteMission:
    """Tests for POST /api/v1/execute."""

    def test_execute_success(self, client, mock_executor):
        mock_executor.execute_mission = AsyncMock(return_value=_mock_result())

        response = client.post(
            "/api/v1/execute",
            json={"mission": "Say hello"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["session_id"] == "test-session-123"
        assert body["status"] == "completed"
        assert body["message"] == "Done!"

    def test_execute_with_profile(self, client, mock_executor):
        mock_executor.execute_mission = AsyncMock(return_value=_mock_result())

        response = client.post(
            "/api/v1/execute",
            json={"mission": "test", "profile": "coding_agent"},
        )

        assert response.status_code == 200
        call_kwargs = mock_executor.execute_mission.call_args
        assert call_kwargs.kwargs["profile"] == "coding_agent"

    def test_execute_default_profile_is_dev(self, client, mock_executor):
        mock_executor.execute_mission = AsyncMock(return_value=_mock_result())

        response = client.post(
            "/api/v1/execute",
            json={"mission": "test"},
        )

        assert response.status_code == 200
        call_kwargs = mock_executor.execute_mission.call_args
        assert call_kwargs.kwargs["profile"] == "dev"

    def test_execute_missing_mission_returns_422(self, client):
        response = client.post("/api/v1/execute", json={})
        assert response.status_code == 422

    def test_execute_file_not_found_returns_404(self, client, mock_executor):
        mock_executor.execute_mission = AsyncMock(
            side_effect=FileNotFoundError("Profile not found: unknown")
        )

        response = client.post(
            "/api/v1/execute",
            json={"mission": "test"},
        )

        assert response.status_code == 404
        body = response.json()
        assert body["code"] == "profile_not_found"

    def test_execute_value_error_returns_400(self, client, mock_executor):
        mock_executor.execute_mission = AsyncMock(
            side_effect=ValueError("Invalid agent definition")
        )

        response = client.post(
            "/api/v1/execute",
            json={"mission": "test"},
        )

        assert response.status_code == 400
        body = response.json()
        assert body["code"] == "invalid_request"

    def test_execute_llm_error_returns_502(self, client, mock_executor):
        mock_executor.execute_mission = AsyncMock(
            side_effect=LLMError("Rate limit exceeded")
        )

        response = client.post(
            "/api/v1/execute",
            json={"mission": "test"},
        )

        assert response.status_code == 502
        body = response.json()
        assert "code" in body
        assert "message" in body

    def test_execute_planning_error_returns_400(self, client, mock_executor):
        mock_executor.execute_mission = AsyncMock(
            side_effect=PlanningError("Plan generation failed")
        )

        response = client.post(
            "/api/v1/execute",
            json={"mission": "test"},
        )

        assert response.status_code == 400

    def test_execute_tool_error_upstream_returns_502(self, client, mock_executor):
        err = ToolError("External API failed")
        err.upstream = True
        mock_executor.execute_mission = AsyncMock(side_effect=err)

        response = client.post(
            "/api/v1/execute",
            json={"mission": "test"},
        )

        assert response.status_code == 502

    def test_execute_tool_error_internal_returns_500(self, client, mock_executor):
        err = ToolError("Internal tool failure")
        err.upstream = False
        mock_executor.execute_mission = AsyncMock(side_effect=err)

        response = client.post(
            "/api/v1/execute",
            json={"mission": "test"},
        )

        assert response.status_code == 500

    def test_execute_generic_error_returns_500(self, client, mock_executor):
        mock_executor.execute_mission = AsyncMock(
            side_effect=RuntimeError("Unexpected")
        )

        response = client.post(
            "/api/v1/execute",
            json={"mission": "test"},
        )

        assert response.status_code == 500
        body = response.json()
        assert body["code"] == "internal_server_error"

    def test_error_response_has_standardized_format(self, client, mock_executor):
        mock_executor.execute_mission = AsyncMock(
            side_effect=LLMError("Rate limit")
        )

        response = client.post(
            "/api/v1/execute",
            json={"mission": "test"},
        )

        body = response.json()
        assert "code" in body
        assert "message" in body


class TestExecuteStream:
    """Tests for POST /api/v1/execute/stream."""

    def test_stream_returns_sse_content_type(self, client, mock_executor):
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

        mock_executor.execute_mission_streaming = mock_stream

        with client.stream(
            "POST",
            "/api/v1/execute/stream",
            json={"mission": "test"},
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]

    def test_stream_missing_mission_returns_422(self, client):
        response = client.post("/api/v1/execute/stream", json={})
        assert response.status_code == 422
