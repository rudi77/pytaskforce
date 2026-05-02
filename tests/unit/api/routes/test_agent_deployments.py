"""Integration tests for the agent deployment API routes."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from taskforce.api.dependencies import (
    get_agent_deployment_service,
    get_agent_registry,
    get_deployment_registry,
)
from taskforce.api.server import create_app
from taskforce.application.agent_deployment_service import AgentDeploymentService
from taskforce.core.domain.agent_models import CustomAgentDefinition
from taskforce.infrastructure.persistence.file_agent_deployment_registry import (
    FileAgentDeploymentRegistry,
)


class _Tools:
    """Minimal tool catalog stub — accepts everything."""

    def validate_native_tools(self, names):
        return True, []

    def get_native_tool_names(self):
        return []


class _AgentRegistry:
    """In-memory custom agent registry for tests."""

    def __init__(self) -> None:
        self._agents: dict[str, CustomAgentDefinition] = {}

    def add(self, agent: CustomAgentDefinition) -> CustomAgentDefinition:
        self._agents[agent.agent_id] = agent
        return agent

    def get_agent(self, agent_id: str):
        return self._agents.get(agent_id)


def _make_agent(agent_id: str, *, updated_at: str = "v1") -> CustomAgentDefinition:
    return CustomAgentDefinition(
        agent_id=agent_id,
        name=agent_id.title(),
        description="d",
        system_prompt="You are a helpful assistant.",
        tool_allowlist=[],
        mcp_servers=[],
        mcp_tool_allowlist=[],
        created_at="2025-01-01T00:00:00+00:00",
        updated_at=updated_at,
    )


@pytest.fixture
def fixtures(tmp_path):
    agents = _AgentRegistry()
    deployments = FileAgentDeploymentRegistry(work_dir=tmp_path / ".taskforce")
    service = AgentDeploymentService(
        agent_registry=agents,
        deployment_registry=deployments,
        tool_catalog=_Tools(),
    )
    return agents, deployments, service


@pytest.fixture
def client(fixtures):
    agents, deployments, service = fixtures
    app = create_app()
    app.dependency_overrides[get_agent_registry] = lambda: agents
    app.dependency_overrides[get_deployment_registry] = lambda: deployments
    app.dependency_overrides[get_agent_deployment_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# --- deploy ----------------------------------------------------------------


def test_deploy_returns_deployed_record(client, fixtures):
    agents, _, _ = fixtures
    agents.add(_make_agent("writer", updated_at="v1"))

    response = client.post(
        "/api/v1/agents/writer/deploy",
        json={"deployed_by": "alice", "message": "first deploy"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "deployed"
    assert body["agent_id"] == "writer"
    assert body["version"] == "v1"
    assert body["environment"] == "local"
    assert body["deployed_by"] == "alice"
    assert body["deployed_at"] is not None


def test_deploy_without_body_uses_defaults(client, fixtures):
    agents, _, _ = fixtures
    agents.add(_make_agent("writer"))

    response = client.post("/api/v1/agents/writer/deploy")

    assert response.status_code == 200
    body = response.json()
    assert body["environment"] == "local"
    assert body["deployed_by"] is None


def test_deploy_unknown_agent_returns_404(client):
    response = client.post("/api/v1/agents/missing/deploy")
    assert response.status_code == 404
    assert response.json()["code"] == "agent_not_found"


# --- active ----------------------------------------------------------------


def test_active_returns_current_deployment(client, fixtures):
    agents, _, _ = fixtures
    agents.add(_make_agent("writer", updated_at="v1"))
    client.post("/api/v1/agents/writer/deploy")

    response = client.get("/api/v1/agents/writer/active")
    assert response.status_code == 200
    assert response.json()["version"] == "v1"


def test_active_for_unknown_agent_returns_404(client):
    response = client.get("/api/v1/agents/missing/active")
    assert response.status_code == 404
    assert response.json()["code"] == "deployment_not_found"


def test_active_can_be_scoped_to_environment(client, fixtures):
    agents, _, _ = fixtures
    agents.add(_make_agent("writer"))
    client.post("/api/v1/agents/writer/deploy", json={"environment": "staging"})

    assert client.get("/api/v1/agents/writer/active?environment=staging").status_code == 200
    assert client.get("/api/v1/agents/writer/active?environment=local").status_code == 404


# --- history ---------------------------------------------------------------


def test_history_lists_all_records_newest_first(client, fixtures):
    agents, _, service = fixtures
    agents.add(_make_agent("writer", updated_at="v1"))
    client.post("/api/v1/agents/writer/deploy", json={"message": "first"})

    # Re-deploy with a newer version
    agents.add(_make_agent("writer", updated_at="v2"))
    client.post("/api/v1/agents/writer/deploy", json={"message": "second"})

    response = client.get("/api/v1/agents/writer/deployments")
    assert response.status_code == 200
    versions = [d["version"] for d in response.json()["deployments"]]
    assert versions == ["v2", "v1"]


# --- rollback --------------------------------------------------------------


def test_rollback_re_activates_previous_version(client, fixtures):
    agents, _, _ = fixtures
    agents.add(_make_agent("writer", updated_at="v1"))
    client.post("/api/v1/agents/writer/deploy")

    agents.add(_make_agent("writer", updated_at="v2"))
    client.post("/api/v1/agents/writer/deploy")
    assert client.get("/api/v1/agents/writer/active").json()["version"] == "v2"

    response = client.post(
        "/api/v1/agents/writer/rollback",
        json={"to_version": "v1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "v1"
    assert body["status"] == "deployed"

    assert client.get("/api/v1/agents/writer/active").json()["version"] == "v1"


def test_rollback_unknown_target_returns_404(client, fixtures):
    agents, _, _ = fixtures
    agents.add(_make_agent("writer"))
    client.post("/api/v1/agents/writer/deploy")

    response = client.post(
        "/api/v1/agents/writer/rollback",
        json={"to_version": "nope"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "rollback_target_not_found"
