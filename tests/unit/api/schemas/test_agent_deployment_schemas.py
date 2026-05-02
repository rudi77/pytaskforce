from datetime import datetime

import pytest
from pydantic import ValidationError

from taskforce.api.schemas.agent_deployment_schemas import AgentDeploymentRequest
from taskforce.core.domain.agent_deployment import AgentDeploymentStatus, DeploymentEnvironment


def test_deployment_request_requires_metadata_for_deployed_status() -> None:
    with pytest.raises(ValidationError, match="deployed status requires"):
        AgentDeploymentRequest(
            agent_id="writer",
            version="1.0.0",
            status=AgentDeploymentStatus.DEPLOYED,
            target_environment=DeploymentEnvironment.PROD,
            config_snapshot={"profile": "coding"},
        )


def test_deployment_request_to_domain_roundtrip() -> None:
    deployed_at = datetime.utcnow()
    req = AgentDeploymentRequest(
        agent_id="writer",
        version=2,
        status=AgentDeploymentStatus.DEPLOYED,
        target_environment=DeploymentEnvironment.STAGING,
        deployed_at=deployed_at,
        deployed_by="ci",
        config_snapshot={"max_parallel_tools": 4},
    )

    deployment = req.to_domain()

    assert deployment.version == 2
    assert deployment.status == AgentDeploymentStatus.DEPLOYED
    assert deployment.target_environment == DeploymentEnvironment.STAGING
