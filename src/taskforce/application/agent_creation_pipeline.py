"""Agent Creation Pipeline - Extracted from AgentExecutor.

Dispatches agent creation based on plugin_path, agent_id, or profile
parameters. Handles lookup, validation, and delegation to AgentFactory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from taskforce.core.domain.agent import Agent
from taskforce.core.domain.agent_models import (
    CustomAgentDefinition,
    PluginAgentDefinition,
)
from taskforce.core.domain.errors import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from taskforce.application.factory import AgentFactory

logger = structlog.get_logger(__name__)


class AgentCreationPipeline:
    """Dispatches agent creation to the appropriate factory method.

    Handles three creation paths:
    - Plugin path: direct external plugin directory
    - Agent ID: registered custom/plugin agent definition
    - Profile: YAML profile (with optional plugin agent fallback)
    """

    def __init__(self, factory: AgentFactory) -> None:
        self._factory = factory
        self._logger = logger.bind(component="agent_creation_pipeline")

    async def create_agent(
        self,
        profile: str,
        user_context: dict[str, Any] | None = None,
        agent_id: str | None = None,
        environment: str | None = None,
        version: str | None = None,
        planning_strategy: str | None = None,
        planning_strategy_params: dict[str, Any] | None = None,
        plugin_path: str | None = None,
    ) -> Agent:
        """Create Agent using factory, dispatching to the right strategy."""
        self._logger.debug(
            "creating_lean_agent",
            profile=profile,
            has_user_context=user_context is not None,
            agent_id=agent_id,
            environment=environment,
            version=version,
            planning_strategy=planning_strategy,
            plugin_path=plugin_path,
        )

        if plugin_path:
            return await self._from_plugin_path(
                plugin_path, profile, user_context,
                planning_strategy, planning_strategy_params,
            )

        if agent_id:
            return await self._from_agent_id(
                agent_id, profile, user_context,
                planning_strategy, planning_strategy_params,
                environment, version,
            )

        return await self._from_profile(
            profile, user_context,
            planning_strategy, planning_strategy_params,
        )

    async def _from_plugin_path(
        self,
        plugin_path: str,
        profile: str,
        user_context: dict[str, Any] | None,
        planning_strategy: str | None,
        planning_strategy_params: dict[str, Any] | None,
    ) -> Agent:
        """Create agent from an explicit plugin directory path."""
        self._logger.info(
            "creating_agent_with_plugin",
            plugin_path=plugin_path,
            profile=profile,
        )
        return await self._factory.create_agent_with_plugin(
            plugin_path=plugin_path,
            profile=profile,
            user_context=user_context,
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
        )

    async def _from_agent_id(
        self,
        agent_id: str,
        profile: str,
        user_context: dict[str, Any] | None,
        planning_strategy: str | None,
        planning_strategy_params: dict[str, Any] | None,
        environment: str | None,
        version: str | None,
    ) -> Agent:
        """Create agent from a registered agent ID."""
        self._validate_agent_id_format(agent_id)

        resolved_agent_id = agent_id
        deployment_status = "not_requested"
        resolved_version = version
        if environment or version:
            (
                resolved_agent_id,
                resolved_version,
                deployment_status,
            ) = self._resolve_deployment_context(agent_id, environment, version)

        agent_response = self._lookup_agent_definition(agent_id)
        if resolved_agent_id != agent_id:
            agent_response = self._lookup_agent_definition(resolved_agent_id)
        if not agent_response:
            raise NotFoundError(
                f"Agent '{resolved_agent_id}' not found",
                details={
                    "agent_id": resolved_agent_id,
                    "requested_agent_id": agent_id,
                    "environment": environment,
                    "version": resolved_version,
                },
            )

        self._logger.info(
            "agent_deployment_context_resolved",
            requested_agent_id=agent_id,
            resolved_agent_id=resolved_agent_id,
            resolved_version=resolved_version,
            environment=environment,
            deployment_status=deployment_status,
        )

        if isinstance(agent_response, PluginAgentDefinition):
            return await self._from_plugin_definition(
                agent_response, resolved_agent_id, profile, user_context,
                planning_strategy, planning_strategy_params,
            )

        if isinstance(agent_response, CustomAgentDefinition):
            return await self._from_custom_definition(
                agent_response, resolved_agent_id,
                planning_strategy, planning_strategy_params,
            )

        raise ValidationError(
            f"Agent '{agent_id}' is a profile agent, not a custom or plugin agent. "
            "Use 'profile' parameter for profile agents.",
            details={"agent_id": agent_id, "source": agent_response.source},
        )

    def _resolve_deployment_context(
        self,
        agent_id: str,
        environment: str | None,
        requested_version: str | None,
    ) -> tuple[str, str | None, str]:
        """Resolve deployed agent/version for an environment with draft fallback.

        Fallback behavior:
        - If no deployment registry is available, fall back to the requested agent.
        - If explicit version is provided, use it directly.
        - If environment is provided, resolve the active deployment.
        - If no active deployment exists, fall back to draft/custom agent if present.
        - If neither deployment nor draft/custom exists, raise NotFoundError.
        - If deployment metadata exists but is not active, raise ConflictError.
        """
        registry = self._build_agent_registry()
        if not environment:
            return agent_id, requested_version, "version_override" if requested_version else "not_requested"

        resolver = getattr(registry, "get_active_deployment", None)
        if not callable(resolver):
            return agent_id, requested_version, "registry_no_deployment_support"

        if requested_version:
            versioned_agent_id = self._build_versioned_agent_id(agent_id, requested_version)
            return versioned_agent_id, requested_version, "explicit_version"

        deployment = resolver(agent_id=agent_id, environment=environment)
        if deployment is None:
            fallback_definition = self._lookup_agent_definition(agent_id)
            if fallback_definition:
                return agent_id, None, "fallback_draft_or_custom"
            raise NotFoundError(
                f"No active deployment found for agent '{agent_id}' in environment '{environment}'",
                details={"agent_id": agent_id, "environment": environment},
            )

        status = getattr(deployment, "status", "active")
        if status != "active":
            raise ConflictError(
                f"Deployment for agent '{agent_id}' in '{environment}' is not active",
                details={"agent_id": agent_id, "environment": environment, "status": status},
            )

        resolved_version = str(getattr(deployment, "version", "")) or None
        if not resolved_version:
            return agent_id, None, "active_no_version"

        resolved_agent_id = self._build_versioned_agent_id(agent_id, resolved_version)
        return resolved_agent_id, resolved_version, "active_deployment"

    def _build_versioned_agent_id(self, agent_id: str, version: str) -> str:
        """Build canonical agent ID for a specific version."""
        return f"{agent_id}@{version}"

    def _build_agent_registry(self) -> Any:
        """Build and return the configured agent registry instance."""
        from taskforce.application.infrastructure_builder import InfrastructureBuilder

        return InfrastructureBuilder().build_agent_registry()

    def _validate_agent_id_format(self, agent_id: str) -> None:
        """Validate that agent_id does not contain slashes."""
        if "/" in agent_id:
            raise ValidationError(
                f"Invalid agent_id format: '{agent_id}'. "
                f"Agent IDs cannot contain slashes. "
                f"Use 'profile' parameter instead "
                f"(e.g., profile='{agent_id.split('/')[0]}').",
                details={"agent_id": agent_id},
            )

    def _lookup_agent_definition(self, agent_id: str) -> Any:
        """Look up an agent definition from the agent registry."""
        from taskforce.application.infrastructure_builder import (
            InfrastructureBuilder,
        )

        registry = InfrastructureBuilder().build_agent_registry()
        return registry.get_agent(agent_id)

    async def _from_plugin_definition(
        self,
        definition: PluginAgentDefinition,
        agent_id: str,
        profile: str,
        user_context: dict[str, Any] | None,
        planning_strategy: str | None,
        planning_strategy_params: dict[str, Any] | None,
    ) -> Agent:
        """Create agent from a PluginAgentDefinition."""
        from taskforce.application.factory import get_base_path

        base_path = get_base_path()
        plugin_path_abs = (base_path / definition.plugin_path).resolve()

        self._logger.info(
            "loading_plugin_agent",
            agent_id=agent_id,
            plugin_path=str(plugin_path_abs),
        )

        return await self._factory.create_agent_with_plugin(
            plugin_path=str(plugin_path_abs),
            profile=profile,
            user_context=user_context,
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
        )

    async def _from_custom_definition(
        self,
        definition: CustomAgentDefinition,
        agent_id: str,
        planning_strategy: str | None,
        planning_strategy_params: dict[str, Any] | None,
    ) -> Agent:
        """Create agent from a CustomAgentDefinition."""
        self._logger.info(
            "loading_custom_agent",
            agent_id=agent_id,
            agent_name=definition.name,
            tool_count=len(definition.tool_allowlist),
        )

        return await self._factory.create_agent(
            system_prompt=definition.system_prompt,
            tools=definition.tool_allowlist,
            mcp_servers=definition.mcp_servers,
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
        )

    async def _from_profile(
        self,
        profile: str,
        user_context: dict[str, Any] | None,
        planning_strategy: str | None,
        planning_strategy_params: dict[str, Any] | None,
    ) -> Agent:
        """Create agent from a profile, checking for plugin match first."""
        agent_response = self._lookup_agent_definition(profile)

        if isinstance(agent_response, PluginAgentDefinition):
            return await self._from_plugin_via_profile_name(
                agent_response, profile, user_context,
                planning_strategy, planning_strategy_params,
            )

        return await self._factory.create_agent(
            config=profile,
            user_context=user_context,
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
        )

    async def _from_plugin_via_profile_name(
        self,
        definition: PluginAgentDefinition,
        profile: str,
        user_context: dict[str, Any] | None,
        planning_strategy: str | None,
        planning_strategy_params: dict[str, Any] | None,
    ) -> Agent:
        """Create a plugin agent when the profile name matched a plugin."""
        from taskforce.application.factory import get_base_path

        base_path = get_base_path()
        plugin_path_abs = (base_path / definition.plugin_path).resolve()

        self._logger.info(
            "profile_matches_plugin_agent",
            profile=profile,
            plugin_path=str(plugin_path_abs),
            hint="Using profile name as plugin agent. Consider using agent_id parameter instead.",
        )

        return await self._factory.create_agent_with_plugin(
            plugin_path=str(plugin_path_abs),
            profile="butler",
            user_context=user_context,
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
        )
