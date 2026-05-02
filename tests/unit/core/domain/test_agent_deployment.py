from datetime import datetime

import pytest

from taskforce.core.domain.agent_deployment import (
    AgentDeployment,
    AgentDeploymentStatus,
    DeploymentEnvironment,
    validate_unique_deployments,
)


def test_agent_deployment_allows_valid_transition() -> None:
    deployment = AgentDeployment(
        agent_id="writer",
        version="1.0.0",
        status=AgentDeploymentStatus.DRAFT,
        target_environment=DeploymentEnvironment.STAGING,
        config_snapshot={"k": "v"},
    )

    validated = deployment.transition_to(AgentDeploymentStatus.VALIDATED)

    assert validated.status == AgentDeploymentStatus.VALIDATED
    assert dict(validated.config_snapshot) == {"k": "v"}


def test_agent_deployment_rejects_invalid_transition() -> None:
    deployment = AgentDeployment(
        agent_id="writer",
        version="1.0.0",
        status=AgentDeploymentStatus.DRAFT,
        target_environment=DeploymentEnvironment.STAGING,
    )

    with pytest.raises(ValueError, match="Invalid status transition"):
        deployment.transition_to(AgentDeploymentStatus.DEPLOYED)


def test_validate_unique_deployments_rejects_multiple_active_versions() -> None:
    deployed_at = datetime.utcnow()
    deployments = [
        AgentDeployment(
            agent_id="writer",
            version="1.0.0",
            status=AgentDeploymentStatus.DEPLOYED,
            target_environment=DeploymentEnvironment.PROD,
            deployed_at=deployed_at,
            deployed_by="ops",
        ),
        AgentDeployment(
            agent_id="writer",
            version="1.1.0",
            status=AgentDeploymentStatus.DEPLOYED,
            target_environment=DeploymentEnvironment.PROD,
            deployed_at=deployed_at,
            deployed_by="ops",
        ),
    ]

    with pytest.raises(ValueError, match="Multiple active deployments"):
        validate_unique_deployments(deployments)
