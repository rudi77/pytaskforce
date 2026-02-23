"""Application Layer - Agent Factory.

Dependency injection factory for creating Agent instances with infrastructure
adapters based on configuration profiles (dev/staging/prod).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from taskforce.core.domain.agent_definition import AgentDefinition

import aiofiles
import structlog
import yaml

from taskforce.application.intent_router import (
    create_intent_router_from_config,
)
from taskforce.application.planning_strategy_factory import select_planning_strategy
from taskforce.application.plugin_loader import PluginLoader
from taskforce.application.profile_loader import DEFAULT_TOOL_NAMES, ProfileLoader
from taskforce.application.skill_manager import (
    SkillManager,
    create_skill_manager_from_manifest,
)
from taskforce.application.system_prompt_assembler import SystemPromptAssembler
from taskforce.application.tool_builder import ToolBuilder
from taskforce.core.domain.agent import Agent
from taskforce.core.domain.context_policy import ContextPolicy
from taskforce.core.domain.errors import ConfigError
from taskforce.core.interfaces.llm import LLMProviderProtocol
from taskforce.core.interfaces.runtime import AgentRuntimeTrackerProtocol
from taskforce.core.interfaces.state import StateManagerProtocol
from taskforce.core.interfaces.tools import ToolProtocol
from taskforce.core.utils.paths import get_base_path


def _set_mcp_contexts(agent: Agent, mcp_contexts: list[Any]) -> None:
    """Store MCP contexts on an agent for lifecycle management.

    Uses setattr to avoid mypy errors since _mcp_contexts is a
    dynamic attribute consumed via getattr in LeanAgent.close().
    """
    setattr(agent, "_mcp_contexts", mcp_contexts)


def _set_plugin_manifest(agent: Agent, manifest: Any) -> None:
    """Store plugin manifest on an agent for lifecycle management.

    Uses setattr to avoid mypy errors since _plugin_manifest is a
    dynamic attribute consumed via getattr in CLI commands.
    """
    setattr(agent, "_plugin_manifest", manifest)


# Type for factory extension callbacks
FactoryExtensionCallback = Any  # Callable[[AgentFactory, dict, Agent], Agent]

# Global registry for factory extensions from plugins
_factory_extensions: list[FactoryExtensionCallback] = []


def register_factory_extension(extension: FactoryExtensionCallback) -> None:
    """Register a factory extension callback (called after agent creation)."""
    _factory_extensions.append(extension)


def unregister_factory_extension(extension: FactoryExtensionCallback) -> None:
    """Unregister a factory extension callback."""
    if extension in _factory_extensions:
        _factory_extensions.remove(extension)


def clear_factory_extensions() -> None:
    """Clear all registered factory extensions."""
    _factory_extensions.clear()


class AgentFactory:
    """Factory for creating Agent instances with dependency injection.

    Wires core domain objects with infrastructure adapters based on
    configuration profiles (dev/staging/prod).
    """

    def __init__(self, config_dir: str | None = None):
        """Initialize AgentFactory.

        Args:
            config_dir: Path to directory containing profile YAML files.
                       Defaults to ``src/taskforce_extensions/configs/``.
        """
        self.config_dir = self._resolve_config_dir(config_dir)
        self.logger = structlog.get_logger().bind(component="agent_factory")
        self.profile_loader = ProfileLoader(self.config_dir)
        self.prompt_assembler = SystemPromptAssembler()
        self._tool_builder = ToolBuilder(self)

    @staticmethod
    def _resolve_config_dir(config_dir: str | None) -> Path:
        """Resolve the configuration directory path."""
        if config_dir is not None:
            return Path(config_dir)

        base_path = get_base_path()
        new_config_dir = base_path / "src" / "taskforce_extensions" / "configs"
        old_config_dir = base_path / "configs"
        if new_config_dir.exists():
            return new_config_dir
        if old_config_dir.exists():
            return old_config_dir
        return new_config_dir

    def _apply_extensions(self, config: dict[str, Any], agent: Agent) -> Agent:
        """Apply registered factory extensions to the agent."""
        for extension in _factory_extensions:
            try:
                result = extension(self, config, agent)
                if result is not None:
                    agent = result
                self.logger.debug(
                    "factory_extension_applied",
                    extension=str(extension),
                )
            except Exception as e:
                self.logger.warning(
                    "factory_extension_failed",
                    extension=str(extension),
                    error=str(e),
                    error_type=type(e).__name__,
                )
        return agent

    # -------------------------------------------------------------------------
    # New Unified API (Phase 4 Refactoring)
    # -------------------------------------------------------------------------

    async def create(
        self,
        definition: AgentDefinition,
        user_context: dict[str, Any] | None = None,
        base_config_override: dict[str, Any] | None = None,
    ) -> Agent:
        """Create an Agent from a unified AgentDefinition.

        Args:
            definition: Unified agent definition containing all configuration.
            user_context: Optional user context for RAG tools.
            base_config_override: Optional pre-loaded base profile config.

        Returns:
            Agent instance with injected dependencies.
        """
        self.logger.info(
            "creating_agent_from_definition",
            agent_id=definition.agent_id,
            source=definition.source.value,
            base_profile=definition.base_profile,
            specialist=definition.specialist,
            tools=definition.tools,
            has_mcp_servers=definition.has_mcp_servers,
            has_custom_prompt=definition.has_custom_prompt,
        )

        base_config = await self._resolve_base_config(definition, base_config_override)
        infra = self._build_infrastructure(base_config, definition)
        all_tools = await self._collect_tools_for_definition(
            definition, base_config, infra, user_context
        )

        system_prompt = self.prompt_assembler.assemble(
            all_tools,
            specialist=definition.specialist,
            custom_prompt=definition.system_prompt if definition.has_custom_prompt else None,
        )
        agent_settings = self._extract_agent_settings(
            base_config, definition, definition.planning_strategy, definition.planning_strategy_params
        )

        self.logger.debug(
            "agent_created",
            agent_id=definition.agent_id,
            tools_count=len(all_tools),
            tool_names=[t.name for t in all_tools],
            model_alias=agent_settings["model_alias"],
            planning_strategy=agent_settings["planning_strategy"].name,
        )

        agent = self._instantiate_agent(
            infra=infra,
            all_tools=all_tools,
            system_prompt=system_prompt,
            settings=agent_settings,
        )

        _set_mcp_contexts(agent, infra["mcp_contexts"])
        return self._apply_extensions(base_config, agent)

    async def _resolve_base_config(
        self,
        definition: AgentDefinition,
        base_config_override: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Resolve the base configuration for a definition."""
        if base_config_override:
            return base_config_override

        from taskforce.application.infrastructure_builder import InfrastructureBuilder

        infra_builder = InfrastructureBuilder(self.config_dir)
        return infra_builder.load_profile_safe(definition.base_profile)

    def _build_infrastructure(
        self,
        base_config: dict[str, Any],
        definition: AgentDefinition,
    ) -> dict[str, Any]:
        """Build core infrastructure components (state manager, LLM, runtime).

        Returns:
            Dict with keys: state_manager, llm_provider, context_policy,
            runtime_tracker, mcp_contexts (populated later).
        """
        from taskforce.application.infrastructure_builder import InfrastructureBuilder

        infra_builder = InfrastructureBuilder(self.config_dir)
        return {
            "state_manager": infra_builder.build_state_manager(
                base_config, work_dir_override=definition.work_dir
            ),
            "llm_provider": infra_builder.build_llm_provider(base_config),
            "context_policy": infra_builder.build_context_policy(base_config),
            "runtime_tracker": self._create_runtime_tracker(
                base_config, work_dir_override=definition.work_dir
            ),
            "model_alias": base_config.get("llm", {}).get("default_model", "main"),
            "mcp_contexts": [],
        }

    async def _collect_tools_for_definition(
        self,
        definition: AgentDefinition,
        base_config: dict[str, Any],
        infra: dict[str, Any],
        user_context: dict[str, Any] | None,
    ) -> list[ToolProtocol]:
        """Collect all tools (native, plugin, MCP, sub-agent) for a definition."""
        from taskforce.application.infrastructure_builder import InfrastructureBuilder
        from taskforce.application.tool_registry import ToolRegistry
        from taskforce.core.domain.agent_definition import AgentSource

        infra_builder = InfrastructureBuilder(self.config_dir)
        llm_provider = infra["llm_provider"]

        mcp_tools, mcp_contexts = await infra_builder.build_mcp_tools(
            definition.mcp_servers, tool_filter=definition.mcp_tool_filter
        )
        infra["mcp_contexts"] = mcp_contexts

        memory_store_dir = ToolBuilder.resolve_memory_store_dir(
            base_config, work_dir_override=definition.work_dir
        )
        tool_registry = ToolRegistry(
            llm_provider=llm_provider,
            user_context=user_context,
            memory_store_dir=memory_store_dir,
        )
        native_tools = tool_registry.resolve(definition.tools)
        self._add_orchestration_tool(native_tools, base_config)
        self._add_sub_agent_tools(native_tools, definition.sub_agent_specs)

        plugin_tools: list[ToolProtocol] = []
        if definition.source == AgentSource.PLUGIN and definition.plugin_path:
            plugin_tools = await self._load_plugin_tools_for_definition(
                definition, llm_provider
            )

        return plugin_tools + native_tools + mcp_tools

    def _add_orchestration_tool(
        self, tools: list[ToolProtocol], config: dict[str, Any]
    ) -> None:
        """Add orchestration tool to tool list if enabled and not duplicate."""
        orchestration_tool = self._tool_builder.build_orchestration_tool(config)
        if orchestration_tool and not any(
            t.name == orchestration_tool.name for t in tools
        ):
            tools.append(orchestration_tool)

    def _add_sub_agent_tools(
        self,
        tools: list[ToolProtocol],
        sub_agent_specs: list[dict[str, Any]],
    ) -> None:
        """Instantiate and add sub-agent tools from definition specs."""
        for spec in sub_agent_specs:
            sub_agent_tool = self._tool_builder.instantiate_sub_agent_tool(spec)
            if sub_agent_tool:
                tools.append(sub_agent_tool)

    def _extract_agent_settings(
        self,
        config: dict[str, Any],
        definition: AgentDefinition | None,
        planning_strategy: str | None,
        planning_strategy_params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Extract agent settings (max_steps, strategy, etc.) from config and definition."""
        agent_config = config.get("agent", {})
        def_max_steps = definition.max_steps if definition else None
        max_steps = def_max_steps or agent_config.get("max_steps")
        strategy_name = planning_strategy or agent_config.get("planning_strategy")
        strategy_params = planning_strategy_params or agent_config.get(
            "planning_strategy_params"
        )
        return {
            "max_steps": max_steps,
            "max_parallel_tools": agent_config.get("max_parallel_tools"),
            "planning_strategy": select_planning_strategy(strategy_name, strategy_params),
            "model_alias": config.get("llm", {}).get("default_model", "main"),
        }

    def _instantiate_agent(
        self,
        *,
        infra: dict[str, Any],
        all_tools: list[ToolProtocol],
        system_prompt: str,
        settings: dict[str, Any],
        skill_manager: Any | None = None,
        intent_router: Any | None = None,
        summary_threshold: int | None = None,
        compression_trigger: int | None = None,
        max_input_tokens: int | None = None,
    ) -> Agent:
        """Create an Agent instance from resolved infrastructure and settings."""
        agent_logger = structlog.get_logger().bind(component="agent")
        return Agent(
            state_manager=infra["state_manager"],
            llm_provider=infra["llm_provider"],
            tools=all_tools,
            logger=agent_logger,
            system_prompt=system_prompt,
            model_alias=settings["model_alias"],
            context_policy=infra["context_policy"],
            max_steps=settings["max_steps"],
            max_parallel_tools=settings["max_parallel_tools"],
            planning_strategy=settings["planning_strategy"],
            runtime_tracker=infra["runtime_tracker"],
            skill_manager=skill_manager,
            intent_router=intent_router,
            summary_threshold=summary_threshold,
            compression_trigger=compression_trigger,
            max_input_tokens=max_input_tokens,
        )

    async def _load_plugin_tools_for_definition(
        self,
        definition: AgentDefinition,
        llm_provider: LLMProviderProtocol,
    ) -> list[ToolProtocol]:
        """Load plugin tools for a plugin-source agent definition."""
        if not definition.plugin_path:
            return []

        plugin_loader = PluginLoader()
        manifest = plugin_loader.discover_plugin(definition.plugin_path)
        plugin_tools = plugin_loader.load_tools(
            manifest, tool_configs=[], llm_provider=llm_provider
        )
        self.logger.debug(
            "plugin_tools_loaded",
            plugin_path=definition.plugin_path,
            tools=[t.name for t in plugin_tools],
        )
        return plugin_tools

    # -------------------------------------------------------------------------
    # Legacy API (maintained for backwards compatibility)
    # -------------------------------------------------------------------------

    async def create_agent(
        self,
        *,
        profile: str | None = None,
        # Option 1: Config file path
        config: str | None = None,
        # Option 2: Inline parameters
        system_prompt: str | None = None,
        tools: list[str] | None = None,
        llm: dict[str, Any] | None = None,
        persistence: dict[str, Any] | None = None,
        mcp_servers: list[dict[str, Any]] | None = None,
        max_steps: int | None = None,
        planning_strategy: str | None = None,
        planning_strategy_params: dict[str, Any] | None = None,
        context_policy: dict[str, Any] | None = None,
        # Shared optional parameters
        work_dir: str | None = None,
        user_context: dict[str, Any] | None = None,
        specialist: str | None = None,
    ) -> Agent:
        """Create an Agent instance.

        Supports two mutually exclusive modes: config file (``config`` or
        ``profile``) **or** inline parameters.  Mixing both raises ``ValueError``.

        Args:
            profile: Profile name to load from configs/{profile}.yaml.
            config: Path to YAML configuration file.
            system_prompt: Custom system prompt for the agent.
            tools: List of tool names to enable.
            llm: LLM configuration dict.
            persistence: Persistence configuration.
            mcp_servers: List of MCP server configurations.
            max_steps: Maximum execution steps for the agent.
            planning_strategy: Planning strategy name.
            planning_strategy_params: Parameters for the planning strategy.
            context_policy: Context policy configuration dict.
            work_dir: Override for work directory (applies to both modes).
            user_context: User context for RAG tools.
            specialist: Specialist profile.

        Returns:
            Agent instance with injected dependencies.

        Raises:
            ValueError: If both config and inline parameters are provided.
            FileNotFoundError: If config file not found.
        """
        self._validate_create_agent_params(profile, config, system_prompt, tools,
                                           llm, persistence, mcp_servers, max_steps,
                                           context_policy)
        return await self._dispatch_create_agent(
            profile=profile, config=config, system_prompt=system_prompt,
            tools=tools, llm=llm, persistence=persistence,
            mcp_servers=mcp_servers, max_steps=max_steps,
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
            context_policy=context_policy, work_dir=work_dir,
            user_context=user_context, specialist=specialist,
        )

    @staticmethod
    def _validate_create_agent_params(
        profile: str | None,
        config: str | None,
        system_prompt: str | None,
        tools: list[str] | None,
        llm: dict[str, Any] | None,
        persistence: dict[str, Any] | None,
        mcp_servers: list[dict[str, Any]] | None,
        max_steps: int | None,
        context_policy: dict[str, Any] | None,
    ) -> None:
        """Validate mutually exclusive parameter groups for create_agent."""
        has_inline_params = any([
            system_prompt is not None,
            tools is not None,
            llm is not None,
            persistence is not None,
            mcp_servers is not None,
            max_steps is not None,
            context_policy is not None,
        ])

        if profile and config:
            raise ValueError(
                "Cannot use 'profile' with 'config'. "
                "Provide either a profile name or a config file path."
            )
        if profile and has_inline_params:
            raise ValueError(
                "Cannot use 'profile' with inline parameters. "
                "Provide either a profile name or inline parameters."
            )
        if config and has_inline_params:
            raise ValueError(
                "Cannot use 'config' with inline parameters. "
                "Either provide a config file path OR inline parameters, not both."
            )

    async def _dispatch_create_agent(
        self,
        *,
        profile: str | None,
        config: str | None,
        system_prompt: str | None,
        tools: list[str] | None,
        llm: dict[str, Any] | None,
        persistence: dict[str, Any] | None,
        mcp_servers: list[dict[str, Any]] | None,
        max_steps: int | None,
        planning_strategy: str | None,
        planning_strategy_params: dict[str, Any] | None,
        context_policy: dict[str, Any] | None,
        work_dir: str | None,
        user_context: dict[str, Any] | None,
        specialist: str | None,
    ) -> Agent:
        """Dispatch to the appropriate agent creation method based on params."""
        if profile:
            profile_config = self._load_profile(profile)
            return await self._create_agent_from_profile_config(
                profile=profile, config=profile_config, work_dir=work_dir,
                user_context=user_context, planning_strategy=planning_strategy,
                planning_strategy_params=planning_strategy_params,
            )

        if config:
            return await self._create_agent_from_config_file(
                config_path=config, work_dir=work_dir, user_context=user_context,
                planning_strategy=planning_strategy,
                planning_strategy_params=planning_strategy_params,
            )

        return await self._create_agent_from_inline_params(
            system_prompt=system_prompt, tools=tools, llm=llm,
            persistence=persistence, mcp_servers=mcp_servers,
            max_steps=max_steps, planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
            context_policy=context_policy, work_dir=work_dir,
            user_context=user_context, specialist=specialist,
        )

    def _extract_tool_names(self, tools_config: list[Any]) -> list[str]:
        """Extract tool names from mixed config entries (excludes sub_agent specs)."""
        from taskforce.core.domain.agent_definition import _class_name_to_tool_name

        tool_names: list[str] = []
        for tool_entry in tools_config:
            if isinstance(tool_entry, str):
                tool_names.append(tool_entry)
            elif isinstance(tool_entry, dict):
                name = self._resolve_dict_tool_name(tool_entry)
                if name:
                    tool_names.append(_class_name_to_tool_name(name)
                                      if (name.endswith("Tool") or any(c.isupper() for c in name))
                                      else name.lower())
        return tool_names

    @staticmethod
    def _resolve_dict_tool_name(tool_entry: dict[str, Any]) -> str | None:
        """Resolve a tool name from a dict config entry, skipping sub-agents."""
        if tool_entry.get("type") in {"sub_agent", "agent"}:
            return None
        name = tool_entry.get("name") or tool_entry.get("type", "")
        return name if name else None

    def _extract_sub_agent_specs(self, tools_config: list[Any]) -> list[dict[str, Any]]:
        """Extract sub-agent tool specs from mixed config entries."""
        return [
            entry for entry in tools_config
            if isinstance(entry, dict) and entry.get("type") in {"sub_agent", "agent"}
        ]

    def _build_definition_from_config(
        self,
        profile_name: str,
        config: dict[str, Any],
        work_dir: str | None,
        planning_strategy: str | None,
        planning_strategy_params: dict[str, Any] | None,
    ) -> AgentDefinition:
        """Build AgentDefinition from a loaded profile config."""
        from taskforce.core.domain.agent_definition import (
            AgentDefinition,
            AgentSource,
            MCPServerConfig,
        )

        tools_config = config.get("tools", [])
        mcp_servers_config = config.get("mcp_servers", [])
        agent_config = config.get("agent", {})

        return AgentDefinition(
            agent_id=f"config-{profile_name}",
            name=f"Config Agent ({profile_name})",
            source=AgentSource.PROFILE,
            specialist=config.get("specialist"),
            base_profile=profile_name,
            work_dir=work_dir,
            tools=self._extract_tool_names(tools_config),
            sub_agent_specs=self._extract_sub_agent_specs(tools_config),
            mcp_servers=[
                MCPServerConfig.from_dict(server) for server in mcp_servers_config
            ] if mcp_servers_config else [],
            planning_strategy=planning_strategy or agent_config.get("planning_strategy"),
            planning_strategy_params=(
                planning_strategy_params or agent_config.get("planning_strategy_params")
            ),
            max_steps=agent_config.get("max_steps"),
            system_prompt=config.get("system_prompt"),
        )

    async def _create_agent_from_profile_config(
        self,
        profile: str,
        config: dict[str, Any],
        work_dir: str | None,
        user_context: dict[str, Any] | None,
        planning_strategy: str | None,
        planning_strategy_params: dict[str, Any] | None,
    ) -> Agent:
        """Create Agent from an in-memory profile configuration."""
        self.logger.info("creating_agent_from_profile", profile=profile)
        definition = self._build_definition_from_config(
            profile_name=config.get("profile", profile),
            config=config,
            work_dir=work_dir,
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
        )
        return await self.create(
            definition,
            user_context=user_context,
            base_config_override=config,
        )

    async def _create_agent_from_config_file(
        self,
        config_path: str,
        work_dir: str | None = None,
        user_context: dict[str, Any] | None = None,
        planning_strategy: str | None = None,
        planning_strategy_params: dict[str, Any] | None = None,
    ) -> Agent:
        """Create Agent from a YAML configuration file."""
        config_path_obj = self._resolve_config_path(config_path)
        config = await self._load_yaml_config(config_path_obj)

        self.logger.info(
            "creating_agent_from_config_file",
            config_path=str(config_path_obj),
        )

        profile_name = config.get("profile", config_path_obj.stem)
        definition = self._build_definition_from_config(
            profile_name=profile_name,
            config=config,
            work_dir=work_dir,
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
        )
        return await self.create(definition, user_context=user_context)

    def _resolve_config_path(self, config_path: str) -> Path:
        """Resolve a config path to an absolute file path."""
        config_path_obj = Path(config_path)
        if not config_path_obj.is_absolute():
            for candidate in [
                self.config_dir / config_path,
                self.config_dir / f"{config_path}.yaml",
                Path(f"{config_path}.yaml"),
            ]:
                if candidate.exists():
                    config_path_obj = candidate
                    break

        if not config_path_obj.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        return config_path_obj

    async def _load_yaml_config(self, path: Path) -> dict[str, Any]:
        """Load and parse a YAML config file asynchronously."""
        try:
            async with aiofiles.open(path, mode="r") as f:
                content = await f.read()
            config = yaml.safe_load(content)
        except yaml.YAMLError as e:
            self.logger.error(
                "yaml_parse_failed",
                config_path=str(path),
                error=str(e),
            )
            raise ConfigError(
                f"Failed to parse YAML config file: {path}",
                details={"path": str(path), "error": str(e)},
            ) from e
        except OSError as e:
            self.logger.error(
                "config_file_read_failed",
                config_path=str(path),
                error=str(e),
            )
            raise ConfigError(
                f"Failed to read config file: {path}",
                details={"path": str(path), "error": str(e)},
            ) from e

        if not isinstance(config, dict):
            raise ConfigError(
                f"Config file must contain a YAML mapping, got {type(config).__name__}",
                details={"path": str(path)},
            )
        return config

    async def _create_agent_from_inline_params(
        self,
        system_prompt: str | None = None,
        tools: list[str] | None = None,
        llm: dict[str, Any] | None = None,
        persistence: dict[str, Any] | None = None,
        mcp_servers: list[dict[str, Any]] | None = None,
        max_steps: int | None = None,
        planning_strategy: str | None = None,
        planning_strategy_params: dict[str, Any] | None = None,
        context_policy: dict[str, Any] | None = None,
        work_dir: str | None = None,
        user_context: dict[str, Any] | None = None,
        specialist: str | None = None,
    ) -> Agent:
        """Create Agent from inline parameters."""
        from taskforce.application.infrastructure_builder import InfrastructureBuilder
        from taskforce.application.tool_registry import ToolRegistry
        from taskforce.core.domain.agent_definition import MCPServerConfig

        self.logger.info(
            "creating_agent_from_inline_params",
            has_system_prompt=system_prompt is not None,
            tools=tools,
            specialist=specialist,
        )

        # Build merged config from inline params and defaults
        default_config = self.profile_loader.get_defaults()

        effective_persistence = persistence or default_config.get(
            "persistence", {"type": "file", "work_dir": ".taskforce"}
        )
        if work_dir:
            effective_persistence = {**effective_persistence, "work_dir": work_dir}

        effective_llm = llm or default_config.get("llm", {
            "config_path": "src/taskforce_extensions/configs/llm_config.yaml",
            "default_model": "main",
        })

        merged_config: dict[str, Any] = {
            "persistence": effective_persistence,
            "llm": effective_llm,
            "context_policy": context_policy or default_config.get("context_policy"),
            "mcp_servers": mcp_servers or [],
        }

        # Build infrastructure
        infra_builder = InfrastructureBuilder(self.config_dir)
        infra: dict[str, Any] = {
            "state_manager": infra_builder.build_state_manager(
                merged_config, work_dir_override=work_dir
            ),
            "llm_provider": infra_builder.build_llm_provider(merged_config),
            "context_policy": self._create_context_policy(merged_config),
            "runtime_tracker": self._create_runtime_tracker(
                merged_config, work_dir_override=work_dir
            ),
            "mcp_contexts": [],
        }

        # Collect tools
        llm_provider = infra["llm_provider"]
        mcp_tools_list, mcp_contexts = await infra_builder.build_mcp_tools(
            [MCPServerConfig.from_dict(s) for s in (mcp_servers or [])],
            tool_filter=None,
        )
        infra["mcp_contexts"] = mcp_contexts

        tool_registry = ToolRegistry(
            llm_provider=llm_provider, user_context=user_context,
        )
        effective_tools = tools if tools is not None else list(DEFAULT_TOOL_NAMES)
        all_tools = tool_registry.resolve(effective_tools) + mcp_tools_list

        final_system_prompt = self.prompt_assembler.assemble(
            all_tools, specialist=specialist, custom_prompt=system_prompt,
        )

        # Build agent settings
        agent_defaults = default_config.get("agent", {})
        settings: dict[str, Any] = {
            "max_steps": max_steps or agent_defaults.get("max_steps", 30),
            "max_parallel_tools": agent_defaults.get("max_parallel_tools"),
            "planning_strategy": select_planning_strategy(
                planning_strategy, planning_strategy_params
            ),
            "model_alias": effective_llm.get("default_model", "main"),
        }

        self.logger.debug(
            "agent_created_from_inline",
            tools_count=len(all_tools),
            tool_names=[t.name for t in all_tools],
            model_alias=settings["model_alias"],
            planning_strategy=settings["planning_strategy"].name,
        )

        agent = self._instantiate_agent(
            infra=infra, all_tools=all_tools,
            system_prompt=final_system_prompt, settings=settings,
        )
        _set_mcp_contexts(agent, infra["mcp_contexts"])
        return self._apply_extensions(merged_config, agent)

    async def create_agent_with_plugin(
        self,
        plugin_path: str,
        profile: str = "dev",
        user_context: dict[str, Any] | None = None,
        planning_strategy: str | None = None,
        planning_strategy_params: dict[str, Any] | None = None,
    ) -> Agent:
        """Create Agent with external plugin tools.

        Args:
            plugin_path: Path to plugin directory (relative or absolute).
            profile: Base profile for infrastructure settings.
            user_context: Optional user context for RAG tools.
            planning_strategy: Optional planning strategy override.
            planning_strategy_params: Optional planning strategy parameters.

        Returns:
            Agent instance with plugin tools loaded.

        Raises:
            FileNotFoundError: If plugin path doesn't exist.
            PluginError: If plugin structure is invalid or tools fail validation.
        """
        plugin_loader = PluginLoader()
        manifest = plugin_loader.discover_plugin(plugin_path)

        # Load and merge configs
        base_config = self.profile_loader.load_safe(profile)
        plugin_config = plugin_loader.load_config(manifest)
        merged_config = self.profile_loader.merge_plugin_config(base_config, plugin_config)

        self.logger.info(
            "creating_agent_with_plugin",
            plugin=manifest.name,
            plugin_path=str(manifest.path),
            profile=profile,
            tool_classes=manifest.tool_classes,
            has_plugin_config=bool(plugin_config),
        )

        state_manager = self._create_state_manager(merged_config)
        llm_provider = self._create_llm_provider(merged_config)

        # Build tools: plugin + native + MCP
        tool_configs = plugin_config.get("tools", [])
        plugin_tools = plugin_loader.load_tools(
            manifest, tool_configs=tool_configs, llm_provider=llm_provider
        )
        native_tools = self._resolve_plugin_native_tools(tool_configs, llm_provider)
        all_tools = plugin_tools + native_tools

        mcp_tools, mcp_contexts = await self._tool_builder.create_mcp_tools(merged_config)
        all_tools.extend(mcp_tools)

        activate_skill_tool = self._maybe_add_skill_tool(manifest, all_tools)

        # Build system prompt and agent settings
        system_prompt = self.prompt_assembler.assemble(
            all_tools,
            specialist=plugin_config.get("specialist"),
            custom_prompt=plugin_config.get("system_prompt"),
        )
        agent_config = merged_config.get("agent", {})
        strategy_name = planning_strategy or agent_config.get("planning_strategy")
        strategy_params = planning_strategy_params or agent_config.get(
            "planning_strategy_params"
        )
        settings = {
            "max_steps": agent_config.get("max_steps"),
            "max_parallel_tools": agent_config.get("max_parallel_tools"),
            "planning_strategy": select_planning_strategy(strategy_name, strategy_params),
            "model_alias": merged_config.get("llm", {}).get("default_model", "main"),
        }
        infra = {
            "state_manager": state_manager,
            "llm_provider": llm_provider,
            "context_policy": self._create_context_policy(merged_config),
            "runtime_tracker": self._create_runtime_tracker(
                merged_config,
                work_dir_override=merged_config.get("persistence", {}).get("work_dir"),
            ),
            "mcp_contexts": [],
        }

        self.logger.debug(
            "plugin_agent_created",
            plugin=manifest.name,
            tools_count=len(all_tools),
            tool_names=[t.name for t in all_tools],
            mcp_tools=[t.name for t in mcp_tools],
            model_alias=settings["model_alias"],
            planning_strategy=settings["planning_strategy"].name,
        )

        # Build skill manager and intent router
        skill_manager = self._build_plugin_skill_manager(manifest, plugin_config)
        intent_router = None
        if skill_manager and skill_manager.has_skills:
            intent_router = create_intent_router_from_config(plugin_config)
            self.logger.info(
                "intent_router_created",
                plugin=manifest.name,
                intents=intent_router.list_intents(),
            )

        context_mgmt = merged_config.get("context_management", {})
        agent = self._instantiate_agent(
            infra=infra, all_tools=all_tools, system_prompt=system_prompt,
            settings=settings, skill_manager=skill_manager,
            intent_router=intent_router,
            summary_threshold=context_mgmt.get("summary_threshold"),
            compression_trigger=context_mgmt.get("compression_trigger"),
            max_input_tokens=context_mgmt.get("max_input_tokens"),
        )

        _set_mcp_contexts(agent, mcp_contexts)
        _set_plugin_manifest(agent, manifest)

        if activate_skill_tool is not None:
            activate_skill_tool.set_agent_ref(agent)
            self.logger.debug("activate_skill_tool_agent_ref_set", plugin=manifest.name)

        return self._apply_extensions(merged_config, agent)

    def _resolve_plugin_native_tools(
        self,
        tool_configs: list[Any],
        llm_provider: LLMProviderProtocol,
    ) -> list[ToolProtocol]:
        """Resolve native tools referenced in plugin tool configs."""
        native_tool_names: list[str] = []
        for tool_cfg in tool_configs:
            if isinstance(tool_cfg, str):
                native_tool_names.append(tool_cfg)
            elif isinstance(tool_cfg, dict) and "name" in tool_cfg:
                native_tool_names.append(tool_cfg["name"])

        if not native_tool_names:
            return []

        native_tools: list[ToolProtocol] = []
        for tool in self._tool_builder.get_all_native_tools(llm_provider):
            if tool.name in native_tool_names:
                native_tools.append(tool)
                self.logger.debug("native_tool_added_for_plugin", tool_name=tool.name)
        return native_tools

    def _maybe_add_skill_tool(
        self, manifest: Any, all_tools: list[ToolProtocol]
    ) -> Any:
        """Add ActivateSkillTool if plugin has skills. Returns the tool or None."""
        if not manifest.skills_path:
            return None

        from taskforce.infrastructure.tools.native.activate_skill_tool import (
            ActivateSkillTool,
        )

        activate_skill_tool = ActivateSkillTool()
        all_tools.append(activate_skill_tool)
        self.logger.debug("activate_skill_tool_added", plugin=manifest.name)
        return activate_skill_tool

    def _build_plugin_skill_manager(
        self, manifest: Any, plugin_config: dict[str, Any]
    ) -> SkillManager | None:
        """Build a SkillManager for a plugin if it has skills."""
        if not manifest.skills_path:
            return None

        skill_configs = plugin_config.get("skills", {}).get("available", [])
        skill_manager = create_skill_manager_from_manifest(
            manifest, skill_configs=skill_configs
        )
        if not (skill_manager and skill_manager.has_skills):
            return None

        self.logger.info(
            "plugin_skills_loaded",
            plugin=manifest.name,
            skills=skill_manager.list_skills(),
        )
        skills_config = plugin_config.get("skills", {})
        if skills_config.get("activation", {}).get("auto_switch", True):
            self._configure_skill_switch_conditions(
                skill_manager, manifest.skill_names
            )
        return skill_manager

    def _configure_skill_switch_conditions(
        self, skill_manager: SkillManager, skill_names: list[str]
    ) -> None:
        """Configure default skill switch conditions for smart-booking skills."""
        from taskforce.application.skill_manager import SkillSwitchCondition

        if "smart-booking-auto" not in skill_names:
            return
        if "smart-booking-hitl" not in skill_names:
            return

        skill_manager.add_switch_condition(
            SkillSwitchCondition(
                from_skill="smart-booking-auto",
                to_skill="smart-booking-hitl",
                trigger_tool="confidence_evaluator",
                condition_key="recommendation",
                condition_check=lambda v: v == "hitl_review",
            )
        )
        skill_manager.add_switch_condition(
            SkillSwitchCondition(
                from_skill="smart-booking-auto",
                to_skill="smart-booking-hitl",
                trigger_tool="confidence_evaluator",
                condition_key="triggered_hard_gates",
                condition_check=lambda v: bool(v) if isinstance(v, list) else False,
            )
        )
        self.logger.debug(
            "skill_switch_conditions_configured",
            pattern="smart-booking",
        )

    def _load_profile(self, profile: str) -> dict[str, Any]:
        """Delegates to :class:`ProfileLoader`."""
        return self.profile_loader.load(profile)

    def _create_context_policy(self, config: dict[str, Any]) -> ContextPolicy:
        """Create ContextPolicy from configuration."""
        context_config = config.get("context_policy")
        if context_config:
            return ContextPolicy.from_dict(context_config)
        return ContextPolicy.conservative_default()

    def _create_state_manager(self, config: dict[str, Any]) -> StateManagerProtocol:
        """Create state manager based on configuration."""
        from taskforce.application.infrastructure_builder import InfrastructureBuilder

        return InfrastructureBuilder(self.config_dir).build_state_manager(config)

    def _create_runtime_tracker(
        self,
        config: dict[str, Any],
        work_dir_override: str | None = None,
    ) -> AgentRuntimeTrackerProtocol | None:
        """Create runtime tracker based on configuration."""
        runtime_config = config.get("runtime", {})
        if not runtime_config.get("enabled", False):
            return None

        runtime_work_dir = (
            runtime_config.get("work_dir")
            or work_dir_override
            or config.get("persistence", {}).get("work_dir", ".taskforce")
        )
        store_type = runtime_config.get("store", "file")

        if store_type == "memory":
            from taskforce_extensions.infrastructure.runtime import (
                AgentRuntimeTracker,
                InMemoryCheckpointStore,
                InMemoryHeartbeatStore,
            )
            return AgentRuntimeTracker(
                heartbeat_store=InMemoryHeartbeatStore(),
                checkpoint_store=InMemoryCheckpointStore(),
            )
        if store_type == "file":
            from taskforce_extensions.infrastructure.runtime import (
                AgentRuntimeTracker,
                FileCheckpointStore,
                FileHeartbeatStore,
            )
            return AgentRuntimeTracker(
                heartbeat_store=FileHeartbeatStore(runtime_work_dir),
                checkpoint_store=FileCheckpointStore(runtime_work_dir),
            )
        raise ValueError(f"Unknown runtime store type: {store_type}")

    def _create_llm_provider(self, config: dict[str, Any]) -> LLMProviderProtocol:
        """Create LLM provider based on configuration."""
        from taskforce.application.infrastructure_builder import InfrastructureBuilder

        return InfrastructureBuilder(self.config_dir).build_llm_provider(config)
