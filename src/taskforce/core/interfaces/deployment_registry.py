"""Protocol for the agent deployment registry.

The deployment registry stores the lifecycle records for custom-agent
releases (deploys, rollbacks, failures) and resolves the active version
of an agent for a given environment.

Storage backend is opaque to consumers — file-based for local development
and tests, but other backends (e.g. PostgreSQL) can implement the same
contract.
"""

from __future__ import annotations

from typing import Protocol

from taskforce.core.domain.agent_deployment import (
    AgentDeployment,
    DeploymentEnvironment,
)


class DeploymentRegistryProtocol(Protocol):
    """Persistence contract for agent deployments."""

    def record(self, deployment: AgentDeployment) -> AgentDeployment:
        """Persist a deployment record and update the active pointer.

        For ``DEPLOYED`` records, also updates the active pointer for
        the deployment's environment. For ``ROLLED_BACK`` records, the
        rolled-back version is no longer active and must be replaced
        by an explicit subsequent deploy/rollback.

        Returns the persisted deployment (with any normalised fields).
        """
        ...

    def get_active(
        self,
        agent_id: str,
        environment: DeploymentEnvironment | str = DeploymentEnvironment.LOCAL,
    ) -> AgentDeployment | None:
        """Return the currently active deployment for an agent/environment, or None."""
        ...

    def list_for_agent(self, agent_id: str) -> list[AgentDeployment]:
        """Return the full deployment history for an agent (newest first)."""
        ...

    def is_deployed(
        self,
        agent_id: str,
        environment: DeploymentEnvironment | str = DeploymentEnvironment.LOCAL,
    ) -> bool:
        """Convenience check — True iff there is an active DEPLOYED record."""
        ...
