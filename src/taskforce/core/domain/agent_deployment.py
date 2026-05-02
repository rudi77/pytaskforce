"""Domain model for versioned agent releases and deployments."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping


class AgentDeploymentStatus(str, Enum):
    """Supported deployment lifecycle states."""

    DRAFT = "draft"
    VALIDATED = "validated"
    DEPLOYED = "deployed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class DeploymentEnvironment(str, Enum):
    """Supported deployment target environments."""

    LOCAL = "local"
    STAGING = "staging"
    PROD = "prod"


_ALLOWED_TRANSITIONS: dict[AgentDeploymentStatus, set[AgentDeploymentStatus]] = {
    AgentDeploymentStatus.DRAFT: {AgentDeploymentStatus.VALIDATED},
    AgentDeploymentStatus.VALIDATED: {
        AgentDeploymentStatus.DEPLOYED,
        AgentDeploymentStatus.FAILED,
    },
    AgentDeploymentStatus.DEPLOYED: {
        AgentDeploymentStatus.FAILED,
        AgentDeploymentStatus.ROLLED_BACK,
    },
    AgentDeploymentStatus.FAILED: {AgentDeploymentStatus.VALIDATED},
    AgentDeploymentStatus.ROLLED_BACK: {AgentDeploymentStatus.VALIDATED},
}


@dataclass(frozen=True)
class AgentDeployment:
    """Represents a versioned release of an agent for one environment."""

    agent_id: str
    version: str | int
    status: AgentDeploymentStatus
    target_environment: DeploymentEnvironment
    deployed_at: datetime | None = None
    deployed_by: str | None = None
    rollback_from: str | int | None = None
    config_snapshot: Mapping[str, Any] = field(default_factory=dict)

    def can_transition_to(self, next_status: AgentDeploymentStatus) -> bool:
        """Return whether a transition to ``next_status`` is allowed."""
        allowed = _ALLOWED_TRANSITIONS.get(self.status, set())
        return next_status in allowed

    def transition_to(
        self,
        next_status: AgentDeploymentStatus,
        *,
        deployed_at: datetime | None = None,
        deployed_by: str | None = None,
        rollback_from: str | int | None = None,
    ) -> "AgentDeployment":
        """Return a new deployment with validated status transition."""
        if not self.can_transition_to(next_status):
            raise ValueError(
                f"Invalid status transition: {self.status.value} -> {next_status.value}"
            )

        return AgentDeployment(
            agent_id=self.agent_id,
            version=self.version,
            status=next_status,
            target_environment=self.target_environment,
            deployed_at=deployed_at if next_status == AgentDeploymentStatus.DEPLOYED else None,
            deployed_by=deployed_by if next_status == AgentDeploymentStatus.DEPLOYED else None,
            rollback_from=(rollback_from if next_status == AgentDeploymentStatus.ROLLED_BACK else None),
            config_snapshot=dict(self.config_snapshot),
        )


def validate_unique_deployments(deployments: list[AgentDeployment]) -> None:
    """Validate uniqueness constraints for agent deployments.

    Constraints:
    - ``agent_id`` + ``version`` + ``target_environment`` must be unique.
    - Only one ``deployed`` version is allowed per ``agent_id`` and environment.
    """
    seen_versions: set[tuple[str, str, str]] = set()
    active_per_environment: set[tuple[str, str]] = set()

    for deployment in deployments:
        version_key = str(deployment.version)
        env_key = deployment.target_environment.value
        unique_key = (deployment.agent_id, version_key, env_key)
        if unique_key in seen_versions:
            raise ValueError(
                "Duplicate agent deployment version in environment: "
                f"agent_id={deployment.agent_id}, version={deployment.version}, "
                f"target_environment={env_key}"
            )
        seen_versions.add(unique_key)

        if deployment.status == AgentDeploymentStatus.DEPLOYED:
            active_key = (deployment.agent_id, env_key)
            if active_key in active_per_environment:
                raise ValueError(
                    "Multiple active deployments found for agent/environment: "
                    f"agent_id={deployment.agent_id}, target_environment={env_key}"
                )
            active_per_environment.add(active_key)
