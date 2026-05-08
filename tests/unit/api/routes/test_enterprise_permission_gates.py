"""Regression tests for enterprise-authenticated host API permission gates."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastapi")

from fastapi import Request
from fastapi.testclient import TestClient

from taskforce.api.dependencies import (
    get_agent_deployment_service,
    get_agent_registry,
    get_executor,
    get_workflow_runtime_service,
)
from taskforce.api.server import create_app
from taskforce.core.domain.agent_models import CustomAgentDefinition


def _agent(**overrides) -> CustomAgentDefinition:
    defaults = {
        "agent_id": "writer",
        "name": "Writer",
        "description": "A test agent",
        "system_prompt": "You are a test agent.",
        "tool_allowlist": [],
        "mcp_servers": [],
        "mcp_tool_allowlist": [],
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    defaults.update(overrides)
    return CustomAgentDefinition(**defaults)


def _client_with_permissions(permissions: set[str]) -> TestClient:
    from taskforce.application import plugin_loader

    plugin_loader._plugin_registry = None
    for info in plugin_loader.discover_plugins():
        if info.instance is not None:
            setattr(info.instance, "_initialized", False)
            setattr(info.instance, "_middleware", [])

    app = create_app(
        plugin_config={
            "enterprise": {
                "auth": {"enabled": False, "allow_anonymous": True},
                "policy": {"enabled": False},
                "audit": {"enabled": False},
            }
        }
    )

    registry = MagicMock()
    registry.create_agent.return_value = _agent()
    registry.list_agents.return_value = [_agent()]
    registry.get_agent.return_value = _agent()
    registry.update_agent.return_value = _agent(name="Updated")
    registry.delete_agent.return_value = None
    app.dependency_overrides[get_agent_registry] = lambda: registry

    class WorkflowService:
        async def run_workflow_id(self, workflow_id, executor, session_id=None):
            assert workflow_id == "daily-report"
            assert session_id == "session-1"
            return [
                {
                    "step_id": "collect",
                    "agent": "butler",
                    "task": "Collect news",
                    "status": "completed",
                    "output": "Briefing ready",
                }
            ]

    app.dependency_overrides[get_workflow_runtime_service] = lambda: WorkflowService()
    app.dependency_overrides[get_executor] = lambda: object()

    deployment_service = MagicMock()
    deployment_service.deploy.return_value = SimpleNamespace(
        deployment_id="dep-1",
        agent_id="writer",
        version="v1",
        status="deployed",
        environment="local",
        deployed_at="2026-01-01T00:00:00+00:00",
        error=None,
    )
    app.dependency_overrides[get_agent_deployment_service] = lambda: deployment_service

    @app.middleware("http")
    async def _inject_enterprise_user(request: Request, call_next):
        request.state.user = SimpleNamespace(permissions=permissions)
        return await call_next(request)

    return TestClient(app)


def test_viewer_cannot_create_custom_agent() -> None:
    client = _client_with_permissions({"agent:read"})

    response = client.post(
        "/api/v1/agents",
        json={
            "agent_id": "writer",
            "name": "Writer",
            "description": "A test agent",
            "system_prompt": "You are a test agent.",
        },
    )

    assert response.status_code == 403


def test_agent_create_permission_allows_custom_agent_creation() -> None:
    client = _client_with_permissions({"agent:create"})

    response = client.post(
        "/api/v1/agents",
        json={
            "agent_id": "writer",
            "name": "Writer",
            "description": "A test agent",
            "system_prompt": "You are a test agent.",
        },
    )

    assert response.status_code == 201
    assert response.json()["agent_id"] == "writer"


def test_workflow_run_requires_execute_permission() -> None:
    client = _client_with_permissions({"agent:read"})

    response = client.post(
        "/api/v1/workflows/definitions/daily-report/run",
        json={"session_id": "session-1"},
    )

    assert response.status_code == 403


def test_workflow_run_returns_step_results_to_ui() -> None:
    client = _client_with_permissions({"agent:execute"})

    response = client.post(
        "/api/v1/workflows/definitions/daily-report/run",
        json={"session_id": "session-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["workflow_id"] == "daily-report"
    assert body["steps"] == [
        {
            "step_id": "collect",
            "agent": "butler",
            "task": "Collect news",
            "status": "completed",
            "output": "Briefing ready",
        }
    ]


def test_profiles_list_requires_agent_read() -> None:
    client = _client_with_permissions(set())

    response = client.get("/api/v1/profiles")

    assert response.status_code == 403


def test_agent_deployment_requires_update_permission() -> None:
    client = _client_with_permissions({"agent:read"})

    response = client.post("/api/v1/agents/writer/deploy", json={})

    assert response.status_code == 403


def test_agent_deployment_history_requires_read_permission() -> None:
    client = _client_with_permissions(set())

    response = client.get("/api/v1/agents/writer/deployments")

    assert response.status_code == 403


def test_workflow_save_requires_update_permission() -> None:
    client = _client_with_permissions({"agent:read"})

    response = client.post(
        "/api/v1/workflows/definitions",
        json={
            "workflow_id": "daily-report",
            "name": "Daily Report",
            "trigger": "manual",
            "steps": [],
        },
    )

    assert response.status_code == 403


def test_workflow_delete_requires_delete_permission() -> None:
    client = _client_with_permissions({"agent:read", "agent:execute"})

    response = client.delete("/api/v1/workflows/definitions/daily-report")

    assert response.status_code == 403
