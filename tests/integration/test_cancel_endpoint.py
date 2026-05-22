"""Integration tests for the POST /api/v1/execute/{session_id}/cancel endpoint."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from taskforce.api.dependencies import get_executor  # noqa: E402
from taskforce.api.server import create_app  # noqa: E402


@pytest.fixture
def app():
    application = create_app()
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.mark.integration
def test_cancel_returns_202_when_agent_is_running(app, client):
    mock_executor = MagicMock()
    mock_executor.interrupt = MagicMock(return_value=True)
    app.dependency_overrides[get_executor] = lambda: mock_executor

    response = client.post("/api/v1/execute/sess-abc/cancel")

    assert response.status_code == 202
    body = response.json()
    assert body["session_id"] == "sess-abc"
    assert body["status"] == "interrupt_requested"
    mock_executor.interrupt.assert_called_once_with("sess-abc")


@pytest.mark.spec("api.execute_cancel_unknown_session_returns_404")
@pytest.mark.integration
def test_cancel_returns_404_when_no_active_session(app, client):
    mock_executor = MagicMock()
    mock_executor.interrupt = MagicMock(return_value=False)
    app.dependency_overrides[get_executor] = lambda: mock_executor

    response = client.post("/api/v1/execute/unknown/cancel")

    assert response.status_code == 404
    body = response.json()
    # Server-wide exception handler flattens the ErrorResponse payload.
    assert body["code"] == "session_not_running"
    assert body["details"]["session_id"] == "unknown"
    assert "No active execution" in body["message"]
    mock_executor.interrupt.assert_called_once_with("unknown")
