"""Deployment readiness validation service.

Provides a pre-deployment validation pass for agent definitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from taskforce.application.factory import AgentFactory
from taskforce.application.planning_strategy_factory import select_planning_strategy
from taskforce.application.tool_registry import get_tool_registry


@dataclass(slots=True)
class DeploymentReadinessError(Exception):
    """Structured deployment readiness error."""

    code: str
    message: str
    details: dict[str, Any]


class DeploymentService:
    """Validate agent deployment readiness.

    Runs config checks for tools, planning strategy and optional dry-run
    instantiation through ``AgentFactory``.
    """

    def __init__(self, factory: AgentFactory | None = None) -> None:
        self._factory = factory or AgentFactory()

    def validate_readiness(
        self,
        *,
        deployment: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Validate deployment payload and return updated deployment.

        Raises:
            DeploymentReadinessError: For structured validation errors.
        """
        profile = str(deployment.get("profile") or "").strip()
        if not profile:
            self._mark_failed(deployment)
            raise DeploymentReadinessError(
                code="invalid_agent_config",
                message="Missing required deployment profile",
                details={"field": "profile"},
            )

        config = self._factory.get_profile_config(profile)
        self._validate_planning_strategy(config)
        self._validate_tool_config_consistency(config)

        if dry_run:
            try:
                self._factory.create_agent(profile)
            except Exception as exc:
                self._mark_failed(deployment)
                raise DeploymentReadinessError(
                    code="agent_instantiation_failed",
                    message="Dry-run AgentFactory instantiation failed",
                    details={"profile": profile, "error": str(exc)},
                ) from exc

        deployment["status"] = "ready"
        deployment["readiness"] = {"validated": True, "dry_run": dry_run}
        return deployment

    def _validate_planning_strategy(self, config: dict[str, Any]) -> None:
        agent_config = config.get("agent") or {}
        try:
            select_planning_strategy(
                strategy_name=agent_config.get("planning_strategy"),
                params=agent_config.get("planning_strategy_params"),
            )
        except ValueError as exc:
            raise DeploymentReadinessError(
                code="invalid_agent_config",
                message="Invalid planning strategy configuration",
                details={"error": str(exc)},
            ) from exc

    def _validate_tool_config_consistency(self, config: dict[str, Any]) -> None:
        tools = config.get("tools") or []
        native_tool_names = [t for t in tools if isinstance(t, str)]
        mcp_entries = [t for t in tools if isinstance(t, dict) and t.get("type") == "mcp"]

        catalog = get_tool_registry()
        is_valid, invalid_tools = catalog.validate_native_tools(native_tool_names)
        if not is_valid:
            raise DeploymentReadinessError(
                code="invalid_tool_config",
                message="Unknown native tools configured",
                details={"invalid_tools": invalid_tools},
            )

        if mcp_entries:
            mcp_config = config.get("mcp") or {}
            servers = mcp_config.get("servers") or []
            server_names = {s.get("name") for s in servers if isinstance(s, dict)}
            missing_servers = [
                entry.get("server")
                for entry in mcp_entries
                if isinstance(entry, dict) and entry.get("server") not in server_names
            ]
            missing_servers = [name for name in missing_servers if name]
            if missing_servers:
                raise DeploymentReadinessError(
                    code="invalid_tool_config",
                    message="MCP tool references unknown MCP server",
                    details={"missing_servers": sorted(set(missing_servers))},
                )

    @staticmethod
    def _mark_failed(deployment: dict[str, Any]) -> None:
        deployment["status"] = "failed"
