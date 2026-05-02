"""Agent deployment lifecycle service.

Single source of truth for *deploying* a custom agent: validates the
agent's configuration, records the deployment in the
:class:`DeploymentRegistryProtocol`, and exposes query helpers used by
the API and the executor's deploy gate.

Design
------
``deploy()`` is the only mutating entry point used by callers; it
performs the readiness check, then transitions a fresh
``AgentDeployment`` through ``PENDING -> VALIDATING -> DEPLOYED`` (or
``FAILED``). ``rollback()`` re-points the active version to a previously
deployed version. The registry is the only persistence touch-point.

The service deliberately does **not** mutate the agent definition file.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol

import structlog

from taskforce.core.domain.agent_deployment import (
    AgentDeployment,
    AgentDeploymentStatus,
    DeploymentEnvironment,
)
from taskforce.core.domain.agent_models import CustomAgentDefinition
from taskforce.core.interfaces.deployment_registry import DeploymentRegistryProtocol

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class DeploymentPreflightError(Exception):
    """Structured preflight validation error.

    Raised by ``deploy()`` when the agent fails readiness checks. The
    ``code`` and ``details`` fields are surfaced 1:1 in the API error
    response for the management UI.
    """

    code: str
    message: str
    details: dict[str, Any]

    def __str__(self) -> str:  # pragma: no cover — trivial
        return self.message


class _AgentLookup(Protocol):
    """Minimal interface required from the agent registry."""

    def get_agent(self, agent_id: str) -> Any: ...


class _ToolCatalog(Protocol):
    """Minimal interface for tool validation (matches ``ToolRegistry``)."""

    def validate_native_tools(self, names: list[str]) -> tuple[bool, list[str]]: ...

    def get_native_tool_names(self) -> list[str]: ...


class AgentDeploymentService:
    """Coordinates the agent deployment lifecycle.

    The service is intentionally registry-agnostic: it holds references
    to whatever ``agent_registry``, ``deployment_registry`` and
    ``tool_catalog`` are wired by ``api/dependencies.py`` (or by tests).
    """

    def __init__(
        self,
        *,
        agent_registry: _AgentLookup,
        deployment_registry: DeploymentRegistryProtocol,
        tool_catalog: _ToolCatalog,
    ) -> None:
        self._agents = agent_registry
        self._deployments = deployment_registry
        self._tools = tool_catalog
        self._logger = logger.bind(component="agent_deployment_service")

    # ============================================================== mutating

    def deploy(
        self,
        agent_id: str,
        *,
        environment: DeploymentEnvironment | str = DeploymentEnvironment.LOCAL,
        deployed_by: str | None = None,
        message: str | None = None,
    ) -> AgentDeployment:
        """Deploy ``agent_id`` to ``environment``.

        Steps:
            1. Resolve the agent definition (must be a custom agent).
            2. Run preflight checks (tools, prompt, MCP wiring).
            3. Persist a ``DEPLOYED`` record and update the active pointer.

        On preflight failure, a ``FAILED`` record is persisted and a
        :class:`DeploymentPreflightError` is raised.
        """
        env = DeploymentEnvironment.coerce(environment)
        agent = self._require_custom_agent(agent_id)
        version = self._derive_version(agent)

        snapshot = self._snapshot_agent(agent)
        pending = AgentDeployment(
            agent_id=agent_id,
            version=version,
            status=AgentDeploymentStatus.PENDING,
            environment=env,
            deployed_by=deployed_by,
            message=message,
            config_snapshot=snapshot,
        )

        validating = pending.with_status(AgentDeploymentStatus.VALIDATING)
        try:
            self._preflight(agent)
        except DeploymentPreflightError as exc:
            failed = validating.with_status(
                AgentDeploymentStatus.FAILED,
                error=exc.message,
            )
            self._deployments.record(failed)
            self._logger.warning(
                "agent.deployment.failed",
                agent_id=agent_id,
                environment=env.value,
                code=exc.code,
            )
            raise

        deployed = validating.with_status(
            AgentDeploymentStatus.DEPLOYED,
            deployed_at=AgentDeployment.now(),
            deployed_by=deployed_by,
            message=message,
        )
        recorded = self._deployments.record(deployed)
        self._logger.info(
            "agent.deployment.deployed",
            agent_id=agent_id,
            version=version,
            environment=env.value,
            deployed_by=deployed_by,
        )
        return recorded

    def rollback(
        self,
        agent_id: str,
        *,
        to_version: str,
        environment: DeploymentEnvironment | str = DeploymentEnvironment.LOCAL,
        deployed_by: str | None = None,
        message: str | None = None,
    ) -> AgentDeployment:
        """Re-activate a previously deployed version.

        ``to_version`` must reference a version that has been deployed
        before for ``environment`` (i.e. there is a ``DEPLOYED`` record
        in history). The currently-active version (if any and different)
        gets a ``ROLLED_BACK`` record; the target version then gets a
        fresh ``DEPLOYED`` record so ``get_active`` returns it.
        """
        env = DeploymentEnvironment.coerce(environment)
        target = self._find_history_record(agent_id, to_version, env)
        if target is None:
            raise DeploymentPreflightError(
                code="rollback_target_not_found",
                message=(
                    f"Cannot rollback agent '{agent_id}' to version '{to_version}': "
                    f"no prior DEPLOYED record found in environment '{env.value}'."
                ),
                details={
                    "agent_id": agent_id,
                    "environment": env.value,
                    "to_version": to_version,
                },
            )

        active = self._deployments.get_active(agent_id, env)
        previous_version = active.version if active else None

        # Mark the previously-active version as rolled back (history audit
        # trail). Skip when we'd be "rolling back to itself" or when nothing
        # was active in the first place.
        if previous_version and previous_version != to_version:
            self._deployments.record(
                AgentDeployment(
                    agent_id=agent_id,
                    version=previous_version,
                    status=AgentDeploymentStatus.ROLLED_BACK,
                    environment=env,
                    deployed_at=AgentDeployment.now(),
                    deployed_by=deployed_by,
                    message=message or f"Rolled back to version {to_version}",
                    rollback_from=previous_version,
                )
            )

        # Re-activate the target version. Reuse its original snapshot so the
        # historical agent definition is preserved across drift.
        replay = AgentDeployment(
            agent_id=agent_id,
            version=to_version,
            status=AgentDeploymentStatus.DEPLOYED,
            environment=env,
            deployed_at=AgentDeployment.now(),
            deployed_by=deployed_by,
            message=message
            or (
                f"Rolled back from {previous_version}"
                if previous_version
                else f"Re-activated version {to_version}"
            ),
            config_snapshot=target.config_snapshot,
        )
        recorded = self._deployments.record(replay)
        self._logger.info(
            "agent.deployment.rolled_back",
            agent_id=agent_id,
            from_version=previous_version,
            to_version=to_version,
            environment=env.value,
        )
        return recorded

    def _find_history_record(
        self,
        agent_id: str,
        version: str,
        environment: DeploymentEnvironment,
    ) -> AgentDeployment | None:
        """Find the most recent DEPLOYED record matching ``version``/``environment``."""
        for record in self._deployments.list_for_agent(agent_id):
            if (
                record.version == version
                and record.environment == environment
                and record.status == AgentDeploymentStatus.DEPLOYED
            ):
                return record
        return None

    # ================================================================ reads

    def get_active(
        self,
        agent_id: str,
        environment: DeploymentEnvironment | str = DeploymentEnvironment.LOCAL,
    ) -> AgentDeployment | None:
        return self._deployments.get_active(agent_id, environment)

    def list_history(self, agent_id: str) -> list[AgentDeployment]:
        return self._deployments.list_for_agent(agent_id)

    def is_deployed(
        self,
        agent_id: str,
        environment: DeploymentEnvironment | str = DeploymentEnvironment.LOCAL,
    ) -> bool:
        return self._deployments.is_deployed(agent_id, environment)

    # ============================================================ internals

    def _require_custom_agent(self, agent_id: str) -> CustomAgentDefinition:
        agent = self._agents.get_agent(agent_id)
        if agent is None:
            raise DeploymentPreflightError(
                code="agent_not_found",
                message=f"Agent '{agent_id}' not found",
                details={"agent_id": agent_id},
            )
        if not isinstance(agent, CustomAgentDefinition):
            raise DeploymentPreflightError(
                code="agent_not_custom",
                message=(
                    f"Agent '{agent_id}' is not a custom agent and cannot be deployed; "
                    "only custom agents have a deployment lifecycle."
                ),
                details={"agent_id": agent_id, "source": getattr(agent, "source", None)},
            )
        return agent

    def _preflight(self, agent: CustomAgentDefinition) -> None:
        """Validate that an agent is safe to deploy.

        MCP wiring is *not* validated here — the codebase convention is
        to defer MCP tool discovery to runtime when the MCP client
        connects. Adding a strict check here would either reject valid
        agents (when ``mcp_tool_allowlist`` uses bare tool names) or
        give false confidence (when names are colon-prefixed but the
        server still rejects them).
        """
        if not (agent.system_prompt or "").strip():
            raise DeploymentPreflightError(
                code="invalid_agent_config",
                message="Agent system_prompt must not be empty.",
                details={"agent_id": agent.agent_id, "field": "system_prompt"},
            )

        if agent.tool_allowlist:
            ok, invalid = self._tools.validate_native_tools(list(agent.tool_allowlist))
            if not ok:
                raise DeploymentPreflightError(
                    code="invalid_tools",
                    message="Agent references unknown native tools.",
                    details={
                        "agent_id": agent.agent_id,
                        "invalid_tools": invalid,
                        "available_tools": sorted(self._tools.get_native_tool_names()),
                    },
                )

    @staticmethod
    def _derive_version(agent: CustomAgentDefinition) -> str:
        # Use ``updated_at`` as a content-derived version. Falls back to
        # ``created_at`` for never-updated drafts.
        return agent.updated_at or agent.created_at or AgentDeployment.now().isoformat()

    @staticmethod
    def _snapshot_agent(agent: CustomAgentDefinition) -> dict[str, Any]:
        return deepcopy(
            {
                "agent_id": agent.agent_id,
                "name": agent.name,
                "description": agent.description,
                "system_prompt": agent.system_prompt,
                "tool_allowlist": list(agent.tool_allowlist),
                "mcp_servers": list(agent.mcp_servers),
                "mcp_tool_allowlist": list(agent.mcp_tool_allowlist),
                "created_at": agent.created_at,
                "updated_at": agent.updated_at,
            }
        )
