from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from taskforce.api.server import create_app
from taskforce.core.domain.errors import (
    CancelledError,
    ConfigError,
    LLMError,
    PlanningError,
    ToolError,
)


@pytest.fixture
def client():
    app = create_app()
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
                status_code=422,
            ),
            422,
            "config_error",
            {"field": "profile"},
        ),
        (
            ToolError(
                "Upstream tool failed",
                details={"tool": "web_search"},
                upstream=True,
            ),
            502,
            "tool_error",
            {"tool": "web_search"},
        ),
        (
            ToolError(
                "Local tool failed",
                details={"tool": "file_read"},
                upstream=False,
            ),
            500,
            "tool_error",
            {"tool": "file_read"},
        ),
        (
            CancelledError("Execution cancelled"),
            409,
            "cancelled_error",
            None,
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
    client,
    error,
    status_code,
    code,
    details,
):
    with patch("taskforce.api.routes.execution.executor") as mock_executor:
        mock_executor.execute_mission = AsyncMock(side_effect=error)

        response = client.post(
            "/api/v1/execute",
            json={"mission": "Test", "profile": "dev"},
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
def test_execute_unknown_error_preserves_detail(client, lean):
    with patch("taskforce.api.routes.execution.executor") as mock_executor:
        mock_executor.execute_mission = AsyncMock(
            side_effect=RuntimeError("Unexpected failure")
        )

        response = client.post(
            "/api/v1/execute",
            json={"mission": "Test", "profile": "dev", "lean": lean},
        )

    _assert_error_response(
        response,
        status_code=500,
        code="internal_server_error",
        message="Unexpected failure",
    )
