import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from taskforce.api.server import app
from taskforce.application.executor import ProgressUpdate
from taskforce.core.domain.enums import EventType
from taskforce.core.domain.models import ExecutionResult

client = TestClient(app)

@pytest.mark.integration
def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

@pytest.mark.integration
def test_execute_mission_endpoint():
    response_payload = ExecutionResult(
        status="completed",
        session_id="test-session-123",
        final_message="Hello!",
        execution_history=[],
    )

    with patch(
        "taskforce.api.routes.execution.executor.execute_mission",
        new=AsyncMock(return_value=response_payload),
    ):
        response = client.post(
            "/api/v1/execute",
            json={
                "mission": "Say hello",
                "profile": "coding_agent",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "test-session-123"
    assert data["status"] == "completed"
    assert data["message"] == "Hello!"

@pytest.mark.integration
def test_list_sessions_endpoint():
    response = client.get("/api/v1/sessions", params={"profile": "dev"})
    assert response.status_code == 200
    assert isinstance(response.json(), list)

@pytest.mark.integration
def test_create_session_endpoint():
    response = client.post(
        "/api/v1/sessions",
        params={"profile": "dev", "mission": "Test Session"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert data["mission"] == "Test Session"

@pytest.mark.integration
def test_streaming_execution():
    async def mock_stream():
        updates = [
            ProgressUpdate(
                timestamp=datetime.now(),
                event_type=EventType.STARTED,
                message="Starting",
                details={"session_id": "stream-1"},
            ),
            ProgressUpdate(
                timestamp=datetime.now(),
                event_type=EventType.COMPLETE,
                message="Done",
                details={"status": "completed"},
            ),
        ]
        for update in updates:
            yield update

    with patch(
        "taskforce.api.routes.execution.executor.execute_mission_streaming",
        return_value=mock_stream(),
    ):
        with client.stream(
            "POST",
            "/api/v1/execute/stream",
            json={"mission": "Test", "profile": "dev"},
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

            events = []
            for line in response.iter_lines():
                if line.startswith("data:"):
                    events.append(line)
                    event_json = line[5:].lstrip()
                    parsed = json.loads(event_json)
                    if parsed.get("event_type") == EventType.COMPLETE.value:
                        break

            assert len(events) >= 2
