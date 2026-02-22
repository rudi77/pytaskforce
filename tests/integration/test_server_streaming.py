"""
Integration Tests for Server SSE Streaming

Tests the Server-Sent Events (SSE) streaming endpoint for real-time
agent execution progress updates.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from httpx import Response

from taskforce.api.dependencies import get_executor
from taskforce.api.server import create_app
from taskforce.application.executor import ProgressUpdate
from taskforce.core.domain.models import ExecutionResult


@pytest.fixture
def app():
    application = create_app()
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app):
    return TestClient(app)


def make_progress_update(
    event_type: str,
    message: str = "",
    details: dict = None,
) -> ProgressUpdate:
    """Helper to create a ProgressUpdate for testing."""
    return ProgressUpdate(
        timestamp=datetime.now(),
        event_type=event_type,
        message=message,
        details=details or {},
    )


async def mock_streaming_generator(updates: list[ProgressUpdate]):
    """Create an async generator from a list of updates."""
    for update in updates:
        yield update


def collect_sse_events(
    response: Response,
    max_events: int | None = None,
) -> list[dict]:
    """Collect SSE events, stopping after complete/error or max_events."""
    events: list[dict] = []
    for line in response.iter_lines():
        if line.startswith("data: "):
            event_data = json.loads(line[6:])
            events.append(event_data)
            if event_data.get("event_type") in {"complete", "error"}:
                break
            if max_events is not None and len(events) >= max_events:
                break
    return events


def _override_streaming(app, mock_updates):
    """Set up dependency override with a mock streaming executor."""
    mock_executor = AsyncMock()
    mock_executor.execute_mission_streaming = lambda *a, **kw: mock_streaming_generator(
        mock_updates
    )
    app.dependency_overrides[get_executor] = lambda: mock_executor
    return mock_executor


class TestServerSSEStreaming:
    """Tests for Server SSE streaming endpoint."""

    @pytest.mark.integration
    def test_sse_endpoint_returns_event_stream(self, app, client):
        """Test that SSE endpoint returns correct content type."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test"}),
            make_progress_update("complete", "Done", {"status": "completed"}),
        ]
        _override_streaming(app, mock_updates)

        with client.stream(
            "POST",
            "/api/v1/execute/stream",
            json={"mission": "Test", "profile": "coding_agent"},
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    @pytest.mark.integration
    def test_sse_yields_started_event(self, app, client):
        """Test that SSE endpoint yields started event."""
        mock_updates = [
            make_progress_update("started", "Starting mission", {"session_id": "test-123", "profile": "coding_agent"}),
            make_progress_update("complete", "Done", {"status": "completed"}),
        ]
        _override_streaming(app, mock_updates)

        with client.stream(
            "POST",
            "/api/v1/execute/stream",
            json={"mission": "Test mission", "profile": "coding_agent"},
        ) as response:
            events = collect_sse_events(response, max_events=len(mock_updates))

            assert len(events) >= 1
            assert events[0]["event_type"] == "started"
            assert "session_id" in events[0]["details"]

    @pytest.mark.integration
    def test_sse_yields_step_start_events(self, app, client):
        """Test that SSE endpoint yields step_start events."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test"}),
            make_progress_update("step_start", "Step 1 starting...", {"step": 1, "max_steps": 30}),
            make_progress_update("final_answer", "", {"content": "Done"}),
            make_progress_update("complete", "Done", {"status": "completed"}),
        ]
        _override_streaming(app, mock_updates)

        with client.stream(
            "POST",
            "/api/v1/execute/stream",
            json={"mission": "Test", "profile": "coding_agent"},
        ) as response:
            events = collect_sse_events(response, max_events=len(mock_updates))

            step_events = [e for e in events if e["event_type"] == "step_start"]
            assert len(step_events) >= 1
            assert step_events[0]["details"]["step"] == 1

    @pytest.mark.integration
    def test_sse_yields_tool_call_events(self, app, client):
        """Test that SSE endpoint yields tool_call and tool_result events."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test"}),
            make_progress_update("step_start", "", {"step": 1}),
            make_progress_update("tool_call", "Calling: web_search", {"tool": "web_search", "status": "starting"}),
            make_progress_update(
                "tool_result",
                "web_search: Found results",
                {"tool": "web_search", "success": True, "output": "Found results"},
            ),
            make_progress_update("final_answer", "", {"content": "Search complete"}),
            make_progress_update("complete", "Search complete", {"status": "completed"}),
        ]
        _override_streaming(app, mock_updates)

        with client.stream(
            "POST",
            "/api/v1/execute/stream",
            json={"mission": "Search for data", "profile": "coding_agent"},
        ) as response:
            events = collect_sse_events(response, max_events=len(mock_updates))

            event_types = [e["event_type"] for e in events]
            assert "tool_call" in event_types
            assert "tool_result" in event_types

            tool_call = next(e for e in events if e["event_type"] == "tool_call")
            assert tool_call["details"]["tool"] == "web_search"

            tool_result = next(e for e in events if e["event_type"] == "tool_result")
            assert tool_result["details"]["success"] is True

    @pytest.mark.integration
    def test_sse_yields_llm_token_events(self, app, client):
        """Test that SSE endpoint yields llm_token events for streaming LLM output."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test"}),
            make_progress_update("step_start", "", {"step": 1}),
            make_progress_update("llm_token", "Hello", {"content": "Hello"}),
            make_progress_update("llm_token", " ", {"content": " "}),
            make_progress_update("llm_token", "World", {"content": "World"}),
            make_progress_update("final_answer", "", {"content": "Hello World"}),
            make_progress_update("complete", "Hello World", {"status": "completed"}),
        ]
        _override_streaming(app, mock_updates)

        with client.stream(
            "POST",
            "/api/v1/execute/stream",
            json={"mission": "Say hello", "profile": "coding_agent"},
        ) as response:
            events = collect_sse_events(response, max_events=len(mock_updates))

            token_events = [e for e in events if e["event_type"] == "llm_token"]
            assert len(token_events) == 3

            # Verify token content
            tokens = [e["details"]["content"] for e in token_events]
            assert tokens == ["Hello", " ", "World"]

    @pytest.mark.integration
    def test_sse_yields_final_answer_event(self, app, client):
        """Test that SSE endpoint yields final_answer event."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test"}),
            make_progress_update("step_start", "", {"step": 1}),
            make_progress_update("final_answer", "This is the final answer", {"content": "This is the final answer"}),
            make_progress_update("complete", "This is the final answer", {"status": "completed"}),
        ]
        _override_streaming(app, mock_updates)

        with client.stream(
            "POST",
            "/api/v1/execute/stream",
            json={"mission": "Answer question", "profile": "coding_agent"},
        ) as response:
            events = collect_sse_events(response, max_events=len(mock_updates))

            final_events = [e for e in events if e["event_type"] == "final_answer"]
            assert len(final_events) == 1
            assert final_events[0]["details"]["content"] == "This is the final answer"

    @pytest.mark.integration
    def test_sse_yields_complete_event(self, app, client):
        """Test that SSE endpoint yields complete event at the end."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test"}),
            make_progress_update("complete", "Mission completed", {"status": "completed"}),
        ]
        _override_streaming(app, mock_updates)

        with client.stream(
            "POST",
            "/api/v1/execute/stream",
            json={"mission": "Test", "profile": "coding_agent"},
        ) as response:
            events = collect_sse_events(response, max_events=len(mock_updates))

            complete_events = [e for e in events if e["event_type"] == "complete"]
            assert len(complete_events) == 1
            assert complete_events[0]["details"]["status"] == "completed"

    @pytest.mark.integration
    def test_sse_yields_error_events(self, app, client):
        """Test that SSE endpoint yields error events when errors occur."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test"}),
            make_progress_update("error", "Error: API timeout", {"message": "API timeout", "step": 1}),
            make_progress_update("complete", "Failed", {"status": "failed"}),
        ]
        _override_streaming(app, mock_updates)

        with client.stream(
            "POST",
            "/api/v1/execute/stream",
            json={"mission": "Test error", "profile": "coding_agent"},
        ) as response:
            events = collect_sse_events(response, max_events=len(mock_updates))

            error_events = [e for e in events if e["event_type"] == "error"]
            assert len(error_events) >= 1
            assert "API timeout" in error_events[0]["details"]["message"]


class TestServerSSEEventFormat:
    """Tests for SSE event format compliance."""

    @pytest.mark.integration
    def test_sse_events_have_timestamp(self, app, client):
        """Test that all SSE events include a timestamp."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test"}),
            make_progress_update("step_start", "", {"step": 1}),
            make_progress_update("complete", "Done", {"status": "completed"}),
        ]
        _override_streaming(app, mock_updates)

        with client.stream(
            "POST",
            "/api/v1/execute/stream",
            json={"mission": "Test", "profile": "coding_agent"},
        ) as response:
            events = collect_sse_events(response, max_events=len(mock_updates))

            for event in events:
                assert "timestamp" in event
                # Timestamp should be parseable
                assert event["timestamp"] is not None

    @pytest.mark.integration
    def test_sse_events_follow_sse_format(self, app, client):
        """Test that events follow SSE format (data: prefix, double newline)."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test"}),
            make_progress_update("complete", "Done", {"status": "completed"}),
        ]
        _override_streaming(app, mock_updates)

        with client.stream(
            "POST",
            "/api/v1/execute/stream",
            json={"mission": "Test", "profile": "coding_agent"},
        ) as response:
            lines = []
            for line in response.iter_lines():
                lines.append(line)
                if line.startswith("data: "):
                    event_json = line[6:]
                    parsed = json.loads(event_json)
                    assert "event_type" in parsed
                    assert "message" in parsed
                    assert "details" in parsed
                    if parsed.get("event_type") in {"complete", "error"}:
                        break

            data_lines = [line for line in lines if line.startswith("data: ")]
            assert len(data_lines) >= 1, "SSE should have at least one data: event"


class TestServerSSEBackwardCompatibility:
    """Tests for SSE endpoint backward compatibility."""

    @pytest.mark.integration
    def test_non_streaming_endpoint_unchanged(self, app, client):
        """Test that non-streaming /execute endpoint still works."""
        mock_result = ExecutionResult(
            status="completed",
            session_id="session-123",
            final_message="Done",
            execution_history=[],
        )
        mock_executor = AsyncMock()
        mock_executor.execute_mission = AsyncMock(return_value=mock_result)
        app.dependency_overrides[get_executor] = lambda: mock_executor

        response = client.post(
            "/api/v1/execute",
            json={"mission": "Test", "profile": "coding_agent"},
        )

        assert response.status_code == 200

        data = response.json()
        assert "session_id" in data
        assert "status" in data
        assert "message" in data
