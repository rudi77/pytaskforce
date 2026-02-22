from unittest.mock import AsyncMock

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from taskforce.api.dependencies import get_executor
from taskforce.api.server import create_app
from taskforce.core.domain.errors import (
    CancelledError,
    ConfigError,
    LLMError,
    PlanningError,
    ToolError,
)


@pytest.fixture
def app():
    application = create_app()
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app):
    return TestClient(app)


def _assert_error_response(
    response,
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict | None = None,
) -> None:
    assert response.status_code == status_code
    data = response.json()
    assert data["code"] == code
    assert data["message"] == message
    assert data["detail"] == message
    if details is None:
        assert "details" not in data
    else:
        assert data["details"] == details


@pytest.mark.integration
@pytest.mark.parametrize(
    ("error", "status_code", "code", "details"),
    [
        (
            PlanningError("Planning failed", details={"step": 1}),
            400,
            "planning_error",
            {"step": 1},
        ),
        (
            ConfigError(
                "Invalid config",
                details={"field": "profile"},
            ),
            400,
            "config_error",
            {"field": "profile"},
        ),
        (
            ToolError(
                "Web search tool failed",
                tool_name="web_search",
            ),
            500,
            "tool_error",
            {"tool_name": "web_search"},
        ),
        (
            ToolError(
                "File read tool failed",
                tool_name="file_read",
            ),
            500,
            "tool_error",
            {"tool_name": "file_read"},
        ),
        (
            CancelledError("Execution cancelled"),
            409,
            "cancelled",
            {},  # CancelledError defaults to empty dict
        ),
        (
            LLMError("LLM unavailable", details={"provider": "openai"}),
            502,
            "llm_error",
            {"provider": "openai"},
        ),
    ],
)
def test_execute_returns_standard_error_schema(
    app,
    client,
    error,
    status_code,
    code,
    details,
):
    mock_executor = AsyncMock()
    mock_executor.execute_mission = AsyncMock(side_effect=error)
    app.dependency_overrides[get_executor] = lambda: mock_executor

    response = client.post(
        "/api/v1/execute",
        json={"mission": "Test", "profile": "coding_agent"},
    )

    _assert_error_response(
        response,
        status_code=status_code,
        code=code,
        message=str(error),
        details=details,
    )


@pytest.mark.integration
@pytest.mark.parametrize("lean", [False, True])
def test_execute_unknown_error_preserves_detail(app, client, lean):
    mock_executor = AsyncMock()
    mock_executor.execute_mission = AsyncMock(
        side_effect=RuntimeError("Unexpected failure")
    )
    app.dependency_overrides[get_executor] = lambda: mock_executor

    response = client.post(
        "/api/v1/execute",
        json={"mission": "Test", "profile": "coding_agent", "lean": lean},
    )

    _assert_error_response(
        response,
        status_code=500,
        code="internal_server_error",
        message="Unexpected failure",
    )
