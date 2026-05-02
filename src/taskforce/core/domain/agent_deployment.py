"""Domain model for versioned agent releases and deployments."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class AgentDeploymentStatus(str, Enum):
    """Supported deployment lifecycle states."""

    PENDING = "pending"
    VALIDATING = "validating"
    DEPLOYED = "deployed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class DeploymentEnvironment(str, Enum):
    """Supported deployment target environments."""

    LOCAL = "local"
    STAGING = "staging"
    PROD = "prod"

    @classmethod
    def coerce(cls, value: DeploymentEnvironment | str) -> DeploymentEnvironment:
        """Convert a string or enum into a ``DeploymentEnvironment``."""
        if isinstance(value, cls):
            return value
        try:
            return cls(value)
        except ValueError as exc:
            allowed = ", ".join(e.value for e in cls)
            raise ValueError(
                f"Unknown deployment environment '{value}'. Allowed: {allowed}"
            ) from exc


_ALLOWED_TRANSITIONS: dict[AgentDeploymentStatus, set[AgentDeploymentStatus]] = {
    AgentDeploymentStatus.PENDING: {
        AgentDeploymentStatus.VALIDATING,
        AgentDeploymentStatus.FAILED,
    },
    AgentDeploymentStatus.VALIDATING: {
        AgentDeploymentStatus.DEPLOYED,
        AgentDeploymentStatus.FAILED,
    },
    AgentDeploymentStatus.DEPLOYED: {
        AgentDeploymentStatus.FAILED,
        AgentDeploymentStatus.ROLLED_BACK,
    },
    AgentDeploymentStatus.FAILED: {
        AgentDeploymentStatus.PENDING,
        AgentDeploymentStatus.VALIDATING,
    },
    AgentDeploymentStatus.ROLLED_BACK: {
        AgentDeploymentStatus.PENDING,
        AgentDeploymentStatus.VALIDATING,
    },
}


@dataclass(frozen=True)
class AgentDeployment:
    """Represents a versioned release of an agent for one environment.

    A deployment is the persistent record of *what was promoted when*. The
    immutable agent definition itself lives in the agent registry; this
    record references that definition by ``(agent_id, version)`` and
    captures the lifecycle metadata (status, who, when, why).

    ``version`` is a free-form string set by the deploy service — typically
    the agent's ``updated_at`` timestamp. ``config_snapshot`` is an optional
    inline copy of the agent definition at deploy time so historical
    deployments can be replayed even after the source definition has changed.
    """

    agent_id: str
    version: str
    status: AgentDeploymentStatus
    environment: DeploymentEnvironment
    deployed_at: datetime | None = None
    deployed_by: str | None = None
    message: str | None = None
    rollback_from: str | None = None
    error: str | None = None
    config_snapshot: Mapping[str, Any] = field(default_factory=dict)

    def can_transition_to(self, next_status: AgentDeploymentStatus) -> bool:
        """Return whether a transition to ``next_status`` is allowed."""
        return next_status in _ALLOWED_TRANSITIONS.get(self.status, set())

    def with_status(
        self,
        next_status: AgentDeploymentStatus,
        *,
        deployed_at: datetime | None = None,
        deployed_by: str | None = None,
        rollback_from: str | None = None,
        error: str | None = None,
        message: str | None = None,
    ) -> AgentDeployment:
        """Return a new deployment with a validated status transition."""
        if not self.can_transition_to(next_status):
            raise ValueError(
                f"Invalid status transition: {self.status.value} -> {next_status.value}"
            )

        return replace(
            self,
            status=next_status,
            deployed_at=deployed_at or self.deployed_at,
            deployed_by=deployed_by or self.deployed_by,
            rollback_from=rollback_from or self.rollback_from,
            error=error,
            message=message or self.message,
        )

    @staticmethod
    def now() -> datetime:
        """UTC ``datetime`` helper used by the service when stamping records."""
        return datetime.now(UTC)


def validate_unique_deployments(deployments: list[AgentDeployment]) -> None:
    """Validate uniqueness constraints for agent deployments.

    Constraints:
    - ``agent_id`` + ``version`` + ``environment`` must be unique.
    - Only one ``deployed`` version is allowed per ``agent_id`` and environment.
    """
    seen_versions: set[tuple[str, str, str]] = set()
    active_per_environment: set[tuple[str, str]] = set()

    for deployment in deployments:
        env_key = deployment.environment.value
        unique_key = (deployment.agent_id, deployment.version, env_key)
        if unique_key in seen_versions:
            raise ValueError(
                "Duplicate agent deployment version in environment: "
                f"agent_id={deployment.agent_id}, version={deployment.version}, "
                f"environment={env_key}"
            )
        seen_versions.add(unique_key)

        if deployment.status == AgentDeploymentStatus.DEPLOYED:
            active_key = (deployment.agent_id, env_key)
            if active_key in active_per_environment:
                raise ValueError(
                    "Multiple active deployments found for agent/environment: "
                    f"agent_id={deployment.agent_id}, environment={env_key}"
                )
            active_per_environment.add(active_key)
