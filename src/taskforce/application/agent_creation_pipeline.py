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
        work_dir: str | None = None,
    ) -> Agent:
        """Create Agent using factory, dispatching to the right strategy.

        ``work_dir`` overrides the profile's ``persistence.work_dir`` and
        is used when the agent runs against a project-rooted workspace
        (a conversation linked to a :class:`Project`). Only the
        profile-driven path (``_from_profile``) honours the override
        today; the agent-id and plugin paths use the registered
        definition's own ``work_dir`` and are out of scope for the
        Cowork-style project model.
        """
        self._logger.debug(
            "creating_lean_agent",
            profile=profile,
            has_user_context=user_context is not None,
            agent_id=agent_id,
            environment=environment,
            version=version,
            planning_strategy=planning_strategy,
            plugin_path=plugin_path,
            work_dir=work_dir,
        )

        if plugin_path:
            return await self._from_plugin_path(
                plugin_path,
                profile,
                user_context,
                planning_strategy,
                planning_strategy_params,
            )

        if agent_id:
            return await self._from_agent_id(
                agent_id,
                profile,
                user_context,
                planning_strategy,
                planning_strategy_params,
                environment,
                version,
            )

        return await self._from_profile(
            profile,
            user_context,
            planning_strategy,
            planning_strategy_params,
            work_dir=work_dir,
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
                agent_response,
                resolved_agent_id,
                profile,
                user_context,
                planning_strategy,
                planning_strategy_params,
            )

        if isinstance(agent_response, CustomAgentDefinition):
            return await self._from_custom_definition(
                agent_response,
                resolved_agent_id,
                planning_strategy,
                planning_strategy_params,
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
        """Resolve the agent/version to load for a given environment.

        Resolution order:
        1. Explicit version wins (returns the versioned id without
           consulting the deployment registry).
        2. ``environment`` set + active deployment exists → resolved version.
        3. ``environment`` set + no deployment but a draft/custom agent
           exists → fall back to the draft.
        4. ``environment`` set + nothing exists → ``NotFoundError``.
        5. No environment → return the requested agent_id verbatim.
        """
        if not environment:
            return (
                agent_id,
                requested_version,
                "version_override" if requested_version else "not_requested",
            )

        if requested_version:
            return (
                self._build_versioned_agent_id(agent_id, requested_version),
                requested_version,
                "explicit_version",
            )

        deployment_registry = self._build_deployment_registry()
        active = deployment_registry.get_active(agent_id, environment)

        if active is None:
            if self._lookup_agent_definition(agent_id):
                return agent_id, None, "fallback_draft_or_custom"
            raise NotFoundError(
                f"No active deployment found for agent '{agent_id}' "
                f"in environment '{environment}'",
                details={"agent_id": agent_id, "environment": environment},
            )

        from taskforce.core.domain.agent_deployment import AgentDeploymentStatus

        if active.status != AgentDeploymentStatus.DEPLOYED:
            raise ConflictError(
                f"Deployment for agent '{agent_id}' in '{environment}' is not active",
                details={
                    "agent_id": agent_id,
                    "environment": environment,
                    "status": active.status.value,
                },
            )

        if not active.version:
            return agent_id, None, "active_no_version"

        return (
            self._build_versioned_agent_id(agent_id, active.version),
            active.version,
            "active_deployment",
        )

    def _build_deployment_registry(self) -> Any:
        """Build the file-backed deployment registry (lazy infra import)."""
        from taskforce.infrastructure.persistence.file_agent_deployment_registry import (
            FileAgentDeploymentRegistry,
        )

        return FileAgentDeploymentRegistry()

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
        work_dir: str | None = None,
    ) -> Agent:
        """Create agent from a profile, checking for plugin match first.

        Multi-runtime: if the profile carries a non-default ``runtime``
        field (``hermes``, ``openclaw``, …), dispatch to the registered
        runtime factory instead of building a native Taskforce agent.
        """
        agent_response = self._lookup_agent_definition(profile)

        if isinstance(agent_response, PluginAgentDefinition):
            return await self._from_plugin_via_profile_name(
                agent_response,
                profile,
                user_context,
                planning_strategy,
                planning_strategy_params,
            )

        runtime_name = self._peek_runtime(profile)
        if runtime_name and runtime_name != "taskforce":
            return await self._from_foreign_runtime(
                runtime_name=runtime_name,
                profile=profile,
                user_context=user_context,
                planning_strategy=planning_strategy,
                planning_strategy_params=planning_strategy_params,
            )

        return await self._factory.create_agent(
            config=profile,
            user_context=user_context,
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
            work_dir=work_dir,
        )

    def _peek_runtime(self, profile: str) -> str | None:
        """Return the ``runtime`` field of the profile, or ``None`` if unknown.

        Falls back to ``None`` (i.e. native taskforce path) on any load
        error — the actual factory will raise the proper user-facing
        FileNotFoundError downstream. Also returns ``None`` when the
        factory has no ``profile_loader`` (some unit tests pass a
        spec-constrained mock).
        """
        loader = getattr(self._factory, "profile_loader", None)
        if loader is None:
            return None
        try:
            config = loader.load(profile)
        except (FileNotFoundError, ValueError, AttributeError):
            return None
        if not isinstance(config, dict):
            return None
        runtime = config.get("runtime")
        if not isinstance(runtime, str) or not runtime.strip():
            return None
        return runtime.strip().lower()

    async def _from_foreign_runtime(
        self,
        runtime_name: str,
        profile: str,
        user_context: dict[str, Any] | None,
        planning_strategy: str | None,
        planning_strategy_params: dict[str, Any] | None,
    ) -> Agent:
        """Build an agent via a non-Taskforce runtime adapter."""
        from taskforce.application.agent_runtime_registry import get_runtime

        try:
            factory_callable = get_runtime(runtime_name)
        except KeyError as exc:
            raise ValidationError(
                str(exc),
                details={"runtime": runtime_name, "profile": profile},
            ) from exc

        profile_dict = dict(self._factory.profile_loader.load(profile))
        profile_dict["__profile_name__"] = profile
        profile_dict["__user_context__"] = user_context
        profile_dict["__planning_strategy__"] = planning_strategy
        profile_dict["__planning_strategy_params__"] = planning_strategy_params

        self._logger.info(
            "creating_foreign_runtime_agent",
            profile=profile,
            runtime=runtime_name,
        )
        runtime_agent = await factory_callable(profile_dict)

        # Stamp runtime_name for introspection if the adapter forgot to.
        if not getattr(runtime_agent, "runtime_name", None):
            try:
                runtime_agent.runtime_name = runtime_name  # type: ignore[attr-defined]
            except (AttributeError, TypeError):
                pass

        return runtime_agent  # type: ignore[return-value]

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
