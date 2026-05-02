"""Tests for agent deployment API schemas."""

from datetime import datetime, timezone

from taskforce.api.schemas.agent_deployment_schemas import (
    AgentDeploymentResponse,
    DeployRequest,
    RollbackRequest,
)
from taskforce.core.domain.agent_deployment import (
    AgentDeployment,
    AgentDeploymentStatus,
    DeploymentEnvironment,
)


def test_deploy_request_defaults() -> None:
    req = DeployRequest()
    assert req.environment is DeploymentEnvironment.LOCAL
    assert req.deployed_by is None
    assert req.message is None


def test_rollback_request_requires_to_version() -> None:
    req = RollbackRequest(to_version="2024-01-01T00:00:00+00:00")
    assert req.to_version == "2024-01-01T00:00:00+00:00"
    assert req.environment is DeploymentEnvironment.LOCAL


def test_response_round_trip_from_domain() -> None:
    deployed_at = datetime.now(timezone.utc)
    domain = AgentDeployment(
        agent_id="writer",
        version="2024-04-01",
        status=AgentDeploymentStatus.DEPLOYED,
        environment=DeploymentEnvironment.STAGING,
        deployed_at=deployed_at,
        deployed_by="ci",
        config_snapshot={"system_prompt": "you are a writer"},
    )

    resp = AgentDeploymentResponse.from_domain(domain)

    assert resp.agent_id == "writer"
    assert resp.version == "2024-04-01"
    assert resp.status is AgentDeploymentStatus.DEPLOYED
    assert resp.environment is DeploymentEnvironment.STAGING
    assert resp.deployed_at == deployed_at
    assert resp.config_snapshot == {"system_prompt": "you are a writer"}
