"""API schemas for agent deployment lifecycle operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from taskforce.core.domain.agent_deployment import (
    AgentDeployment,
    AgentDeploymentStatus,
    DeploymentEnvironment,
)


class DeployRequest(BaseModel):
    """Body for ``POST /agents/{agent_id}/deploy``.

    All fields are optional. Defaults match the most common case
    (deploy the current agent definition to ``local`` with no message).
    """

    environment: DeploymentEnvironment = DeploymentEnvironment.LOCAL
    deployed_by: str | None = Field(default=None, max_length=128)
    message: str | None = Field(default=None, max_length=512)


class RollbackRequest(BaseModel):
    """Body for ``POST /agents/{agent_id}/rollback``."""

    to_version: str = Field(..., min_length=1, max_length=128)
    environment: DeploymentEnvironment = DeploymentEnvironment.LOCAL
    deployed_by: str | None = Field(default=None, max_length=128)
    message: str | None = Field(default=None, max_length=512)


class AgentDeploymentResponse(BaseModel):
    """Single deployment record returned to the management UI."""

    agent_id: str
    version: str
    status: AgentDeploymentStatus
    environment: DeploymentEnvironment
    deployed_at: datetime | None = None
    deployed_by: str | None = None
    message: str | None = None
    rollback_from: str | None = None
    error: str | None = None
    config_snapshot: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_domain(cls, deployment: AgentDeployment) -> AgentDeploymentResponse:
        return cls(
            agent_id=deployment.agent_id,
            version=deployment.version,
            status=deployment.status,
            environment=deployment.environment,
            deployed_at=deployment.deployed_at,
            deployed_by=deployment.deployed_by,
            message=deployment.message,
            rollback_from=deployment.rollback_from,
            error=deployment.error,
            config_snapshot=dict(deployment.config_snapshot),
        )


class AgentDeploymentListResponse(BaseModel):
    """Deployment history response."""

    deployments: list[AgentDeploymentResponse]
