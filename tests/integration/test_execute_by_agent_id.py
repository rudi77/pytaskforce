"""
Integration Tests for Execute by agent_id (Story 8.3)

Tests the complete flow from API endpoint through executor to agent creation.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from taskforce.api.dependencies import get_executor
from taskforce.api.server import create_app
from taskforce.api.schemas.agent_schemas import CustomAgentResponse
from taskforce.core.domain.models import ExecutionResult


@pytest.fixture
def app():
    """Create FastAPI app."""
    application = create_app()
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_custom_agent():
    """Mock custom agent response."""
    return CustomAgentResponse(
        source="custom",
        agent_id="invoice-extractor",
        name="Invoice Extractor",
        description="Extracts invoice fields",
        system_prompt="You are an invoice extraction agent",
        tool_allowlist=["python", "file_read"],
        mcp_servers=[],
        mcp_tool_allowlist=[],
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )


def test_execute_sync_with_agent_id_success(app, client, mock_custom_agent):
    """Test synchronous execution with agent_id returns success."""
    mock_executor = AsyncMock()
    mock_executor.execute_mission = AsyncMock(
        return_value=ExecutionResult(
            session_id="test-session-123",
            status="completed",
            final_message="Invoice fields extracted successfully",
            execution_history=[],
            todolist_id="plan-456",
        )
    )
    app.dependency_overrides[get_executor] = lambda: mock_executor

    # Make request
    response = client.post(
        "/api/v1/execute",
        json={
            "mission": "Extract invoice fields from invoice.pdf",
            "profile": "coding_agent",
            "agent_id": "invoice-extractor",
        },
    )

    # Verify response
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "test-session-123"
    assert data["status"] == "completed"
    assert "Invoice fields extracted" in data["message"]

    # Verify executor was called with agent_id
    mock_executor.execute_mission.assert_called_once()
    call_kwargs = mock_executor.execute_mission.call_args.kwargs
    assert call_kwargs["agent_id"] == "invoice-extractor"
    assert call_kwargs["mission"] == "Extract invoice fields from invoice.pdf"
    assert call_kwargs["profile"] == "dev"


def test_execute_sync_agent_id_not_found(app, client):
    """Test synchronous execution with non-existent agent_id returns 404."""
    mock_executor = AsyncMock()
    mock_executor.execute_mission = AsyncMock(
        side_effect=FileNotFoundError("Agent 'nonexistent' not found")
    )
    app.dependency_overrides[get_executor] = lambda: mock_executor

    response = client.post(
        "/api/v1/execute",
        json={
            "mission": "Test mission",
            "profile": "coding_agent",
            "agent_id": "nonexistent",
        },
    )

    # Verify 404 response
    assert response.status_code == 404
    body = response.json()
    assert "not found" in body.get("detail", "").lower() or "not found" in body.get("message", "").lower()


def test_execute_sync_agent_id_invalid_definition(app, client):
    """Test synchronous execution with invalid agent definition returns 400."""
    mock_executor = AsyncMock()
    mock_executor.execute_mission = AsyncMock(
        side_effect=ValueError("agent_definition must include 'system_prompt'")
    )
    app.dependency_overrides[get_executor] = lambda: mock_executor

    response = client.post(
        "/api/v1/execute",
        json={
            "mission": "Test mission",
            "profile": "coding_agent",
            "agent_id": "corrupt-agent",
        },
    )

    # Verify 400 response
    assert response.status_code == 400
    body = response.json()
    assert "system_prompt" in body.get("detail", "") or "system_prompt" in body.get("message", "")


def test_execute_sync_backward_compatibility_without_agent_id(app, client):
    """Test that execution without agent_id still works (backward compatibility)."""
    mock_executor = AsyncMock()
    mock_executor.execute_mission = AsyncMock(
        return_value=ExecutionResult(
            session_id="test-123",
            status="completed",
            final_message="Success",
        )
    )
    app.dependency_overrides[get_executor] = lambda: mock_executor

    response = client.post(
        "/api/v1/execute",
        json={
            "mission": "Test mission",
            "profile": "coding_agent",
            # No agent_id - uses legacy path
            "lean": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"

    # Verify agent_id was None
    call_kwargs = mock_executor.execute_mission.call_args.kwargs
    assert call_kwargs["agent_id"] is None


def test_execute_stream_with_agent_id_success(app, client, mock_custom_agent):
    """Test streaming execution with agent_id yields events."""
    from datetime import datetime
    from taskforce.application.executor import ProgressUpdate

    async def mock_streaming_generator(*args, **kwargs):
        yield ProgressUpdate(
            timestamp=datetime.now(),
            event_type="started",
            message="Starting mission",
            details={"agent_id": "invoice-extractor"},
        )
        yield ProgressUpdate(
            timestamp=datetime.now(),
            event_type="tool_call",
            message="Calling: file_read",
            details={"tool": "file_read"},
        )
        yield ProgressUpdate(
            timestamp=datetime.now(),
            event_type="complete",
            message="Mission completed",
            details={"status": "completed"},
        )

    mock_executor = AsyncMock()
    mock_executor.execute_mission_streaming = mock_streaming_generator
    app.dependency_overrides[get_executor] = lambda: mock_executor

    response = client.post(
        "/api/v1/execute/stream",
        json={
            "mission": "Extract invoice",
            "profile": "coding_agent",
            "agent_id": "invoice-extractor",
        },
    )

    # Verify streaming response
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    # Parse SSE events
    events = []
    for line in response.text.split("\n\n"):
        if line.startswith("data: "):
            event_data = json.loads(line[6:])
            events.append(event_data)

    # Verify events
    assert len(events) == 3
    assert events[0]["event_type"] == "started"
    assert events[0]["details"]["agent_id"] == "invoice-extractor"
    assert events[1]["event_type"] == "tool_call"
    assert events[2]["event_type"] == "complete"


def test_execute_stream_agent_id_not_found(app, client):
    """Test streaming execution with non-existent agent_id yields error event."""
    async def mock_streaming_generator(*args, **kwargs):
        # Simulate FileNotFoundError in generator
        raise FileNotFoundError("Agent 'nonexistent' not found")
        yield  # Make it a generator

    mock_executor = AsyncMock()
    mock_executor.execute_mission_streaming = mock_streaming_generator
    app.dependency_overrides[get_executor] = lambda: mock_executor

    response = client.post(
        "/api/v1/execute/stream",
        json={
            "mission": "Test",
            "profile": "coding_agent",
            "agent_id": "nonexistent",
        },
    )

    # Streaming endpoints return 200 but send error events
    assert response.status_code == 200

    # Parse error event
    events = []
    for line in response.text.split("\n\n"):
        if line.startswith("data: "):
            event_data = json.loads(line[6:])
            events.append(event_data)

    # Should have error event
    assert len(events) > 0
    error_event = events[0]
    assert error_event["event_type"] == "error"
    assert "not found" in error_event["message"].lower()
    assert error_event["details"]["status_code"] == 404


def test_execute_with_agent_id_ignores_lean_flag(app, client, mock_custom_agent):
    """Test that agent_id takes priority over lean flag."""
    mock_executor = AsyncMock()
    mock_executor.execute_mission = AsyncMock(
        return_value=ExecutionResult(
            session_id="test-123",
            status="completed",
            final_message="Success",
        )
    )
    app.dependency_overrides[get_executor] = lambda: mock_executor

    response = client.post(
        "/api/v1/execute",
        json={
            "mission": "Test",
            "profile": "coding_agent",
            "agent_id": "invoice-extractor",
            "lean": False,  # Should be ignored
        },
    )

    assert response.status_code == 200

    # Verify agent_id was passed (lean flag ignored)
    call_kwargs = mock_executor.execute_mission.call_args.kwargs
    assert call_kwargs["agent_id"] == "invoice-extractor"


def test_execute_with_agent_id_and_user_context(app, client, mock_custom_agent):
    """Test agent_id execution with RAG user context."""
    mock_executor = AsyncMock()
    mock_executor.execute_mission = AsyncMock(
        return_value=ExecutionResult(
            session_id="test-123",
            status="completed",
            final_message="Success",
        )
    )
    app.dependency_overrides[get_executor] = lambda: mock_executor

    response = client.post(
        "/api/v1/execute",
        json={
            "mission": "Search documents",
            "profile": "coding_agent",
            "agent_id": "invoice-extractor",
            "user_id": "user123",
            "org_id": "org456",
            "scope": "private",
        },
    )

    assert response.status_code == 200

    # Verify user_context was passed
    call_kwargs = mock_executor.execute_mission.call_args.kwargs
    assert call_kwargs["agent_id"] == "invoice-extractor"
    assert call_kwargs["user_context"] == {
        "user_id": "user123",
        "org_id": "org456",
        "scope": "private",
    }
