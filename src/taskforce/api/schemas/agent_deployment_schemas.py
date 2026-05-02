"""API schemas for agent deployment lifecycle operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from taskforce.core.domain.agent_deployment import (
    AgentDeployment,
    AgentDeploymentStatus,
    DeploymentEnvironment,
)


class AgentDeploymentRequest(BaseModel):
    """Request payload for creating or updating an agent deployment."""

    agent_id: str = Field(..., min_length=3, max_length=64)
    version: str | int
    status: AgentDeploymentStatus
    target_environment: DeploymentEnvironment
    deployed_at: datetime | None = None
    deployed_by: str | None = None
    rollback_from: str | int | None = None
    config_snapshot: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_status_fields(self) -> "AgentDeploymentRequest":
        """Enforce status-dependent deployment fields."""
        if self.status == AgentDeploymentStatus.DEPLOYED:
            if self.deployed_at is None or not self.deployed_by:
                raise ValueError(
                    "deployed status requires deployed_at and deployed_by"
                )
        if self.status == AgentDeploymentStatus.ROLLED_BACK and self.rollback_from is None:
            raise ValueError("rolled_back status requires rollback_from")
        return self

    def to_domain(self) -> AgentDeployment:
        """Convert request schema to domain model."""
        return AgentDeployment(
            agent_id=self.agent_id,
            version=self.version,
            status=self.status,
            target_environment=self.target_environment,
            deployed_at=self.deployed_at,
            deployed_by=self.deployed_by,
            rollback_from=self.rollback_from,
            config_snapshot=self.config_snapshot,
        )


class AgentDeploymentResponse(BaseModel):
    """Response payload representing a versioned deployment."""

    agent_id: str
    version: str | int
    status: AgentDeploymentStatus
    target_environment: DeploymentEnvironment
    deployed_at: datetime | None = None
    deployed_by: str | None = None
    rollback_from: str | int | None = None
    config_snapshot: dict[str, Any]

    @classmethod
    def from_domain(cls, deployment: AgentDeployment) -> "AgentDeploymentResponse":
        """Build API response from domain model."""
        return cls(
            agent_id=deployment.agent_id,
            version=deployment.version,
            status=deployment.status,
            target_environment=deployment.target_environment,
            deployed_at=deployment.deployed_at,
            deployed_by=deployment.deployed_by,
            rollback_from=deployment.rollback_from,
            config_snapshot=dict(deployment.config_snapshot),
        )
