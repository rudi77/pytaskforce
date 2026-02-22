"""
Application Layer - Agent Factory

This module provides dependency injection factory for creating Agent instances
with different infrastructure adapters based on configuration profiles.

Key Responsibilities:
- Load configuration profiles (dev/staging/prod)
- Instantiate infrastructure adapters (state managers, LLM providers, tools)
- Wire dependencies into core domain Agent
- Support specialist profiles (coding, rag) with layered prompts
- Inject appropriate toolsets based on specialist profile
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from taskforce.core.domain.agent_definition import AgentDefinition

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
from taskforce.core.domain.planning_strategy import PlanningStrategy
from taskforce.core.interfaces.llm import LLMProviderProtocol
from taskforce.core.interfaces.runtime import AgentRuntimeTrackerProtocol
from taskforce.core.interfaces.state import StateManagerProtocol
from taskforce.core.interfaces.tools import ToolProtocol
from taskforce.core.utils.paths import get_base_path


def _coerce_bool(value: Any, default: bool) -> bool:
    """Coerce config values into booleans with sane defaults."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


# Type for factory extension callbacks
FactoryExtensionCallback = Any  # Callable[[AgentFactory, dict, Agent], Agent]

# Global registry for factory extensions from plugins
_factory_extensions: list[FactoryExtensionCallback] = []


def register_factory_extension(extension: FactoryExtensionCallback) -> None:
    """Register a factory extension callback.

    Extensions are called after agent creation to allow plugins to
    modify or enhance agents.

    Args:
        extension: Callback function(factory, config, agent) -> agent
    """
    _factory_extensions.append(extension)


def unregister_factory_extension(extension: FactoryExtensionCallback) -> None:
    """Unregister a factory extension callback.

    Args:
        extension: The extension callback to remove
    """
    if extension in _factory_extensions:
        _factory_extensions.remove(extension)


def clear_factory_extensions() -> None:
    """Clear all registered factory extensions."""
    _factory_extensions.clear()


class AgentFactory:
    """
    Factory for creating Agent instances with dependency injection.

    Wires core domain objects with infrastructure adapters based on
    configuration profiles (dev/staging/prod).

    The factory follows Clean Architecture principles:
    - Reads YAML configuration profiles
    - Instantiates appropriate infrastructure adapters
    - Injects dependencies into Agent
    - Supports specialist profiles (coding, rag) and custom agent definitions
    """

    def __init__(self, config_dir: str | None = None):
        """
        Initialize AgentFactory with configuration directory.

        Args:
            config_dir: Path to directory containing profile YAML files.
                       If None, uses 'src/taskforce_extensions/configs/' relative to project root
                       (or _MEIPASS for frozen executables).
                       Falls back to 'configs/' for backward compatibility.
        """
        if config_dir is None:
            base_path = get_base_path()
            # Try new location first, then fall back to old location for compatibility
            new_config_dir = base_path / "src" / "taskforce_extensions" / "configs"
            old_config_dir = base_path / "configs"
            if new_config_dir.exists():
                self.config_dir = new_config_dir
            elif old_config_dir.exists():
                self.config_dir = old_config_dir
            else:
                # Default to new location even if it doesn't exist yet
                self.config_dir = new_config_dir
        else:
            self.config_dir = Path(config_dir)
        self.logger = structlog.get_logger().bind(component="agent_factory")
        self.profile_loader = ProfileLoader(self.config_dir)
        self.prompt_assembler = SystemPromptAssembler()
        self._tool_builder = ToolBuilder(self)

    def _apply_extensions(self, config: dict, agent: Agent) -> Agent:
        """Apply registered factory extensions to the agent.

        Extensions from plugins can modify or enhance agents after creation.

        Args:
            config: The configuration used to create the agent
            agent: The created agent instance

        Returns:
            The potentially modified agent
        """
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
        """
        Create an Agent from a unified AgentDefinition.

        This is the new unified factory method that replaces:
        - create_agent() - for profile-based agents
        - create_agent_from_definition() - for custom agents
        - create_agent_with_plugin() - for plugin agents
        - create_agent_for_command() - for slash command agents

        The AgentDefinition provides all configuration in a unified format.

        Args:
            definition: Unified agent definition containing all configuration
            user_context: Optional user context for RAG tools (user_id, org_id, scope)
            base_config_override: Optional pre-loaded base profile config.

        Returns:
            Agent instance with injected dependencies

        Example:
            >>> from taskforce.core.domain.agent_definition import AgentDefinition
            >>> factory = AgentFactory()
            >>> definition = AgentDefinition(
            ...     agent_id="my-agent",
            ...     name="My Agent",
            ...     tools=["web_search", "python"],
            ...     base_profile="dev",
            ... )
            >>> agent = await factory.create(definition)
            >>> result = await agent.execute("Do something", "session-123")
        """
        from taskforce.application.infrastructure_builder import InfrastructureBuilder
        from taskforce.application.tool_registry import ToolRegistry
        from taskforce.core.domain.agent_definition import AgentSource

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

        # Build infrastructure
        infra_builder = InfrastructureBuilder(self.config_dir)
        base_config = base_config_override or infra_builder.load_profile_safe(
            definition.base_profile
        )

        state_manager = infra_builder.build_state_manager(
            base_config, work_dir_override=definition.work_dir
        )
        llm_provider = infra_builder.build_llm_provider(base_config)

        # Build MCP tools
        mcp_tools, mcp_contexts = await infra_builder.build_mcp_tools(
            definition.mcp_servers,
            tool_filter=definition.mcp_tool_filter,
        )

        memory_store_dir = ToolBuilder.resolve_memory_store_dir(
            base_config, work_dir_override=definition.work_dir
        )

        # Resolve native tools
        tool_registry = ToolRegistry(
            llm_provider=llm_provider,
            user_context=user_context,
            memory_store_dir=memory_store_dir,
        )
        native_tools = tool_registry.resolve(definition.tools)
        orchestration_tool = self._tool_builder.build_orchestration_tool(base_config)
        if orchestration_tool and not any(
            tool.name == orchestration_tool.name for tool in native_tools
        ):
            native_tools.append(orchestration_tool)

        # Instantiate sub-agent tools from definition specs
        for sub_agent_spec in definition.sub_agent_specs:
            sub_agent_tool = self._tool_builder.instantiate_sub_agent_tool(sub_agent_spec)
            if sub_agent_tool:
                native_tools.append(sub_agent_tool)

        # Handle plugin tools if this is a plugin agent
        plugin_tools: list[ToolProtocol] = []
        if definition.source == AgentSource.PLUGIN and definition.plugin_path:
            plugin_tools = await self._load_plugin_tools_for_definition(definition, llm_provider)

        # Combine all tools
        all_tools = plugin_tools + native_tools + mcp_tools

        # Build system prompt
        system_prompt = self._build_system_prompt_for_definition(definition, all_tools)

        # Get model alias from config
        llm_config = base_config.get("llm", {})
        model_alias = llm_config.get("default_model", "main")

        # Build context policy
        context_policy = infra_builder.build_context_policy(base_config)
        runtime_tracker = self._create_runtime_tracker(
            base_config,
            work_dir_override=definition.work_dir,
        )

        # Get agent settings
        agent_config = base_config.get("agent", {})
        max_steps = definition.max_steps or agent_config.get("max_steps")
        max_parallel_tools = agent_config.get("max_parallel_tools")
        strategy_name = definition.planning_strategy or agent_config.get("planning_strategy")
        strategy_params = definition.planning_strategy_params or agent_config.get(
            "planning_strategy_params"
        )
        selected_strategy = select_planning_strategy(strategy_name, strategy_params)

        self.logger.debug(
            "agent_created",
            agent_id=definition.agent_id,
            tools_count=len(all_tools),
            tool_names=[t.name for t in all_tools],
            model_alias=model_alias,
            planning_strategy=selected_strategy.name,
        )

        # Create agent
        agent_logger = structlog.get_logger().bind(component="agent")
        agent = Agent(
            state_manager=state_manager,
            llm_provider=llm_provider,
            tools=all_tools,
            logger=agent_logger,
            system_prompt=system_prompt,
            model_alias=model_alias,
            context_policy=context_policy,
            max_steps=max_steps,
            max_parallel_tools=max_parallel_tools,
            planning_strategy=selected_strategy,
            runtime_tracker=runtime_tracker,
        )

        # Store MCP contexts for lifecycle management
        agent._mcp_contexts = mcp_contexts

        # Apply plugin extensions
        agent = self._apply_extensions(base_config, agent)

        return agent

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

        # Load plugin tools
        plugin_tools = plugin_loader.load_tools(
            manifest, tool_configs=[], llm_provider=llm_provider
        )

        self.logger.debug(
            "plugin_tools_loaded",
            plugin_path=definition.plugin_path,
            tools=[t.name for t in plugin_tools],
        )

        return plugin_tools

    def _build_system_prompt_for_definition(
        self,
        definition: AgentDefinition,
        tools: list[ToolProtocol],
    ) -> str:
        """Build system prompt for an agent definition."""
        return self.prompt_assembler.assemble(
            tools,
            specialist=definition.specialist,
            custom_prompt=definition.system_prompt if definition.has_custom_prompt else None,
        )

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
        """
        Create an Agent instance.

        Supports two mutually exclusive modes:

        **Option 1: Config file** - Load all settings from a YAML file:
            agent = await factory.create_agent(config="configs/dev.yaml")

        **Option 2: Inline parameters** - Specify settings programmatically:
            agent = await factory.create_agent(
                system_prompt="You are a helpful assistant.",
                tools=["python", "file_read"],
                persistence={"type": "file", "work_dir": ".taskforce"},
            )

        Args:
            config: Path to YAML configuration file. If provided, all other
                   agent settings are loaded from this file.
            profile: Profile name to load from configs/{profile}.yaml.

            system_prompt: Custom system prompt for the agent.
            tools: List of tool names to enable (e.g., ["python", "file_read"]).
            llm: LLM configuration dict (e.g., {"config_path": "...", "default_model": "main"}).
            persistence: Persistence configuration (e.g., {"type": "file", "work_dir": ".taskforce"}).
            mcp_servers: List of MCP server configurations.
            max_steps: Maximum execution steps for the agent.
            planning_strategy: Planning strategy ("native_react", "plan_and_execute", "plan_and_react", "spar").
            planning_strategy_params: Parameters for the planning strategy.
            context_policy: Context policy configuration dict.

            work_dir: Override for work directory (applies to both modes).
            user_context: User context for RAG tools (user_id, org_id, scope).
            specialist: Specialist profile ("coding", "rag", "wiki") - only used
                       when no system_prompt is provided.

        Returns:
            Agent instance with injected dependencies.

        Raises:
            ValueError: If both config and inline parameters are provided.
            FileNotFoundError: If config file not found.

        Examples:
            # Option 1: From config file
            agent = await factory.create_agent(config="configs/dev.yaml")

            # Option 1b: From profile name
            agent = await factory.create_agent(profile="dev")

            # Option 2: Inline parameters
            agent = await factory.create_agent(
                system_prompt="You are a coding assistant.",
                tools=["python", "file_read", "file_write"],
                persistence={"type": "file", "work_dir": ".taskforce_coding"},
            )

            # Minimal inline (uses defaults)
            agent = await factory.create_agent(
                tools=["python", "web_search"],
            )
        """

        # Check for mutually exclusive options
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

        if profile:
            profile_config = self._load_profile(profile)
            return await self._create_agent_from_profile_config(
                profile=profile,
                config=profile_config,
                work_dir=work_dir,
                user_context=user_context,
                planning_strategy=planning_strategy,
                planning_strategy_params=planning_strategy_params,
            )

        # Option 1: Load from config file
        if config:
            return await self._create_agent_from_config_file(
                config_path=config,
                work_dir=work_dir,
                user_context=user_context,
                planning_strategy=planning_strategy,
                planning_strategy_params=planning_strategy_params,
            )

        # Option 2: Inline parameters (or defaults)
        return await self._create_agent_from_inline_params(
            system_prompt=system_prompt,
            tools=tools,
            llm=llm,
            persistence=persistence,
            mcp_servers=mcp_servers,
            max_steps=max_steps,
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
            context_policy=context_policy,
            work_dir=work_dir,
            user_context=user_context,
            specialist=specialist,
        )

    def _extract_tool_names(self, tools_config: list[Any]) -> list[str]:
        """Extract tool names from mixed config entries (excludes sub_agent specs)."""
        from taskforce.core.domain.agent_definition import _class_name_to_tool_name

        tool_names: list[str] = []
        for tool_entry in tools_config:
            if isinstance(tool_entry, str):
                tool_names.append(tool_entry)
            elif isinstance(tool_entry, dict):
                # Skip sub_agent specs - they are handled separately
                if tool_entry.get("type") in {"sub_agent", "agent"}:
                    continue
                tool_name = tool_entry.get("name") or tool_entry.get("type", "")
                if tool_name and (tool_name.endswith("Tool") or any(c.isupper() for c in tool_name)):
                    tool_names.append(_class_name_to_tool_name(tool_name))
                elif tool_name:
                    tool_names.append(tool_name.lower())
        return tool_names

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
            planning_strategy=planning_strategy or config.get("agent", {}).get("planning_strategy"),
            planning_strategy_params=planning_strategy_params or config.get("agent", {}).get("planning_strategy_params"),
            max_steps=config.get("agent", {}).get("max_steps"),
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
        """
        Create Agent from a YAML configuration file.

        Args:
            config_path: Path to the YAML config file.
            work_dir: Optional override for work directory.
            user_context: Optional user context for RAG tools.
            planning_strategy: Optional planning strategy override.
            planning_strategy_params: Optional planning strategy parameters.

        Returns:
            Agent instance.
        """
        from pathlib import Path

        # Resolve config path
        config_path_obj = Path(config_path)
        if not config_path_obj.is_absolute():
            # Try relative to config_dir first, then current directory
            if (self.config_dir / config_path).exists():
                config_path_obj = self.config_dir / config_path
            elif (self.config_dir / f"{config_path}.yaml").exists():
                config_path_obj = self.config_dir / f"{config_path}.yaml"
            elif not config_path_obj.exists():
                # Try with .yaml extension
                if Path(f"{config_path}.yaml").exists():
                    config_path_obj = Path(f"{config_path}.yaml")

        if not config_path_obj.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        # Load config
        with open(config_path_obj) as f:
            config = yaml.safe_load(f)

        self.logger.info(
            "creating_agent_from_config_file",
            config_path=str(config_path_obj),
        )

        # Extract settings from config
        # Use profile name from config or derive from filename
        profile_name = config.get("profile", config_path_obj.stem)

        definition = self._build_definition_from_config(
            profile_name=profile_name,
            config=config,
            work_dir=work_dir,
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
        )
        return await self.create(definition, user_context=user_context)

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
        """
        Create Agent from inline parameters.

        Args:
            system_prompt: Custom system prompt.
            tools: List of tool names.
            llm: LLM configuration.
            persistence: Persistence configuration.
            mcp_servers: MCP server configurations.
            max_steps: Maximum execution steps.
            planning_strategy: Planning strategy.
            planning_strategy_params: Planning strategy parameters.
            context_policy: Context policy configuration.
            work_dir: Work directory override.
            user_context: User context for RAG tools.
            specialist: Specialist profile.

        Returns:
            Agent instance.
        """
        from taskforce.application.infrastructure_builder import InfrastructureBuilder
        from taskforce.application.tool_registry import ToolRegistry
        from taskforce.core.domain.agent_definition import (
            MCPServerConfig,
        )

        self.logger.info(
            "creating_agent_from_inline_params",
            has_system_prompt=system_prompt is not None,
            tools=tools,
            specialist=specialist,
        )

        # Build infrastructure using defaults or provided config
        infra_builder = InfrastructureBuilder(self.config_dir)

        # Load default config for infrastructure settings not provided
        default_config = self._get_default_config()

        # Merge provided settings with defaults
        effective_persistence = persistence or default_config.get("persistence", {"type": "file", "work_dir": ".taskforce"})
        if work_dir:
            effective_persistence = {**effective_persistence, "work_dir": work_dir}

        effective_llm = llm or default_config.get("llm", {
            "config_path": "src/taskforce_extensions/configs/llm_config.yaml",
            "default_model": "main",
        })

        effective_context_policy = context_policy or default_config.get("context_policy")

        # Build merged config for infrastructure
        merged_config = {
            "persistence": effective_persistence,
            "llm": effective_llm,
            "context_policy": effective_context_policy,
            "mcp_servers": mcp_servers or [],
        }

        # Create infrastructure
        state_manager = infra_builder.build_state_manager(merged_config, work_dir_override=work_dir)
        llm_provider = infra_builder.build_llm_provider(merged_config)

        # Build MCP tools
        mcp_tools_list, mcp_contexts = await infra_builder.build_mcp_tools(
            [MCPServerConfig.from_dict(s) for s in (mcp_servers or [])],
            tool_filter=None,
        )

        # Resolve native tools
        tool_registry = ToolRegistry(
            llm_provider=llm_provider,
            user_context=user_context,
        )

        # Use provided tools or default tools
        effective_tools = tools if tools is not None else self._get_default_tool_names()
        native_tools = tool_registry.resolve(effective_tools)

        # Combine all tools
        all_tools = native_tools + mcp_tools_list

        # Build system prompt
        final_system_prompt = self.prompt_assembler.assemble(
            all_tools,
            specialist=specialist,
            custom_prompt=system_prompt,
        )

        # Get model alias
        model_alias = effective_llm.get("default_model", "main")

        # Build context policy
        context_policy_obj = self._create_context_policy(merged_config)

        # Build runtime tracker
        runtime_tracker = self._create_runtime_tracker(merged_config, work_dir_override=work_dir)

        # Get agent settings
        effective_max_steps = max_steps or default_config.get("agent", {}).get("max_steps", 30)
        max_parallel_tools = default_config.get("agent", {}).get("max_parallel_tools")
        selected_strategy = self._select_planning_strategy(planning_strategy, planning_strategy_params)

        self.logger.debug(
            "agent_created_from_inline",
            tools_count=len(all_tools),
            tool_names=[t.name for t in all_tools],
            model_alias=model_alias,
            planning_strategy=selected_strategy.name,
        )

        # Create agent
        agent_logger = structlog.get_logger().bind(component="agent")
        agent = Agent(
            state_manager=state_manager,
            llm_provider=llm_provider,
            tools=all_tools,
            logger=agent_logger,
            system_prompt=final_system_prompt,
            model_alias=model_alias,
            context_policy=context_policy_obj,
            max_steps=effective_max_steps,
            max_parallel_tools=max_parallel_tools,
            planning_strategy=selected_strategy,
            runtime_tracker=runtime_tracker,
        )

        # Store MCP contexts for lifecycle management
        agent._mcp_contexts = mcp_contexts

        # Apply extensions
        agent = self._apply_extensions(merged_config, agent)

        return agent

    def _get_default_config(self) -> dict[str, Any]:
        """Get default configuration for inline agent creation."""
        return self.profile_loader.get_defaults()

    def _get_default_tool_names(self) -> list[str]:
        """Get default tool names for inline agent creation."""
        return list(DEFAULT_TOOL_NAMES)

    def _assemble_lean_system_prompt(
        self, specialist: str | None, tools: list[ToolProtocol]
    ) -> str:
        """Assemble system prompt for Agent.

        Delegates to :class:`SystemPromptAssembler`.
        """
        return self.prompt_assembler.assemble(tools, specialist=specialist)


    async def create_agent_with_plugin(
        self,
        plugin_path: str,
        profile: str = "dev",
        user_context: dict[str, Any] | None = None,
        planning_strategy: str | None = None,
        planning_strategy_params: dict[str, Any] | None = None,
    ) -> Agent:
        """
        Create Agent with external plugin tools.

        Loads tools from an external plugin directory and creates an agent
        with those tools. The plugin must follow the expected structure:

            {plugin_path}/
            ├── {package_name}/
            │   ├── __init__.py
            │   └── tools/
            │       └── __init__.py    # Exports tools via __all__
            ├── configs/
            │   └── {package_name}.yaml
            └── requirements.txt

        The base profile provides infrastructure settings (LLM, persistence),
        while the plugin config provides agent-specific settings (tools, specialist).

        Args:
            plugin_path: Path to plugin directory (relative or absolute)
            profile: Base profile for infrastructure settings (dev/staging/prod)
            user_context: Optional user context for RAG tools
            planning_strategy: Optional planning strategy override
            planning_strategy_params: Optional planning strategy parameters

        Returns:
            Agent instance with plugin tools loaded

        Raises:
            FileNotFoundError: If plugin path doesn't exist
            PluginError: If plugin structure is invalid or tools fail validation

        Example:
            >>> factory = AgentFactory()
            >>> agent = await factory.create_agent_with_plugin(
            ...     plugin_path="examples/accounting_agent",
            ...     profile="dev"
            ... )
            >>> result = await agent.execute("Prüfe diese Rechnung", "session-123")
        """
        # Load plugin manifest
        plugin_loader = PluginLoader()
        manifest = plugin_loader.discover_plugin(plugin_path)

        # Load base profile for infrastructure settings (with fallback to defaults)
        base_config = self.profile_loader.load_safe(profile)

        # Load plugin config and merge
        plugin_config = plugin_loader.load_config(manifest)
        merged_config = self._merge_plugin_config(base_config, plugin_config)

        self.logger.info(
            "creating_agent_with_plugin",
            plugin=manifest.name,
            plugin_path=str(manifest.path),
            profile=profile,
            tool_classes=manifest.tool_classes,
            has_plugin_config=bool(plugin_config),
        )

        # Instantiate infrastructure adapters from base config
        state_manager = self._create_state_manager(merged_config)
        llm_provider = self._create_llm_provider(merged_config)

        # Get tool configurations from plugin config
        # Can be list of strings or dicts with 'name' and 'params'
        tool_configs = plugin_config.get("tools", [])

        # Load plugin tools with config (supports params and ${PLUGIN_PATH})
        # Pass llm_provider for tools that require it (e.g., InvoiceExtractionTool)
        plugin_tools = plugin_loader.load_tools(
            manifest, tool_configs=tool_configs, llm_provider=llm_provider
        )

        # Optionally add native tools if specified in plugin config
        # Extract tool names from both simple strings and dict configs
        native_tool_names: list[str] = []
        for tool_cfg in tool_configs:
            if isinstance(tool_cfg, str):
                native_tool_names.append(tool_cfg)
            elif isinstance(tool_cfg, dict) and "name" in tool_cfg:
                native_tool_names.append(tool_cfg["name"])

        native_tools = []
        if native_tool_names:
            available_native = self._get_all_native_tools(llm_provider)
            for tool in available_native:
                if tool.name in native_tool_names:
                    native_tools.append(tool)
                    self.logger.debug(
                        "native_tool_added_for_plugin",
                        tool_name=tool.name,
                    )

        # Combine plugin tools with native tools
        all_tools = plugin_tools + native_tools

        # Optionally add MCP tools
        mcp_tools, mcp_contexts = await self._create_mcp_tools(merged_config)
        all_tools.extend(mcp_tools)

        # Create ActivateSkillTool if plugin has skills (will be configured later)
        activate_skill_tool = None
        if manifest.skills_path:
            from taskforce.infrastructure.tools.native.activate_skill_tool import (
                ActivateSkillTool,
            )

            activate_skill_tool = ActivateSkillTool()
            all_tools.append(activate_skill_tool)
            self.logger.debug("activate_skill_tool_added", plugin=manifest.name)

        # Build system prompt - check if plugin provides custom prompt
        custom_prompt = plugin_config.get("system_prompt")
        specialist = plugin_config.get("specialist")
        system_prompt = self.prompt_assembler.assemble(
            all_tools,
            specialist=specialist,
            custom_prompt=custom_prompt,
        )

        # Get model alias
        llm_config = merged_config.get("llm", {})
        model_alias = llm_config.get("default_model", "main")

        # Create context policy
        context_policy = self._create_context_policy(merged_config)
        runtime_tracker = self._create_runtime_tracker(
            merged_config,
            work_dir_override=merged_config.get("persistence", {}).get("work_dir"),
        )

        # Get agent settings
        agent_config = merged_config.get("agent", {})
        max_steps = agent_config.get("max_steps")
        max_parallel_tools = agent_config.get("max_parallel_tools")
        strategy_name = (
            planning_strategy
            if planning_strategy is not None
            else agent_config.get("planning_strategy")
        )
        strategy_params = (
            planning_strategy_params
            if planning_strategy_params is not None
            else agent_config.get("planning_strategy_params")
        )
        selected_strategy = select_planning_strategy(strategy_name, strategy_params)

        self.logger.debug(
            "plugin_agent_created",
            plugin=manifest.name,
            tools_count=len(all_tools),
            plugin_tools=[t.name for t in plugin_tools],
            native_tools=[t.name for t in native_tools],
            mcp_tools=[t.name for t in mcp_tools],
            model_alias=model_alias,
            planning_strategy=selected_strategy.name,
        )

        # Create skill manager if plugin has skills
        skill_manager = None
        if manifest.skills_path:
            skill_configs = plugin_config.get("skills", {}).get("available", [])
            skill_manager = create_skill_manager_from_manifest(
                manifest, skill_configs=skill_configs
            )
            if skill_manager and skill_manager.has_skills:
                self.logger.info(
                    "plugin_skills_loaded",
                    plugin=manifest.name,
                    skills=skill_manager.list_skills(),
                )

                # Add default switch conditions for known patterns
                skills_config = plugin_config.get("skills", {})
                if skills_config.get("activation", {}).get("auto_switch", True):
                    self._configure_skill_switch_conditions(
                        skill_manager, manifest.skill_names
                    )

        # Create intent router for fast intent classification (skip planning for well-defined intents)
        intent_router = None
        if skill_manager and skill_manager.has_skills:
            intent_router = create_intent_router_from_config(plugin_config)
            self.logger.info(
                "intent_router_created",
                plugin=manifest.name,
                intents=intent_router.list_intents(),
            )

        # Create logger for agent
        agent_logger = structlog.get_logger().bind(component="agent")

        # Extract context_management settings for aggressive compression
        context_mgmt = merged_config.get("context_management", {})
        summary_threshold = context_mgmt.get("summary_threshold")
        compression_trigger = context_mgmt.get("compression_trigger")
        max_input_tokens = context_mgmt.get("max_input_tokens")

        agent = Agent(
            state_manager=state_manager,
            llm_provider=llm_provider,
            tools=all_tools,
            system_prompt=system_prompt,
            model_alias=model_alias,
            context_policy=context_policy,
            max_steps=max_steps,
            max_parallel_tools=max_parallel_tools,
            planning_strategy=selected_strategy,
            logger=agent_logger,
            runtime_tracker=runtime_tracker,
            skill_manager=skill_manager,
            intent_router=intent_router,
            summary_threshold=summary_threshold,
            compression_trigger=compression_trigger,
            max_input_tokens=max_input_tokens,
        )

        # Store MCP contexts and plugin manifest for lifecycle management
        agent._mcp_contexts = mcp_contexts
        agent._plugin_manifest = manifest

        # Set agent reference on ActivateSkillTool if present
        if activate_skill_tool is not None:
            activate_skill_tool.set_agent_ref(agent)
            self.logger.debug("activate_skill_tool_agent_ref_set", plugin=manifest.name)

        # Apply plugin extensions
        agent = self._apply_extensions(merged_config, agent)

        return agent

    def _configure_skill_switch_conditions(
        self, skill_manager: SkillManager, skill_names: list[str]
    ) -> None:
        """
        Configure default skill switch conditions based on available skills.

        Args:
            skill_manager: The skill manager to configure
            skill_names: List of available skill names
        """
        from taskforce.application.skill_manager import SkillSwitchCondition

        # Auto-configure smart-booking workflow if both skills exist
        if "smart-booking-auto" in skill_names and "smart-booking-hitl" in skill_names:
            # Switch on recommendation = hitl_review
            skill_manager.add_switch_condition(
                SkillSwitchCondition(
                    from_skill="smart-booking-auto",
                    to_skill="smart-booking-hitl",
                    trigger_tool="confidence_evaluator",
                    condition_key="recommendation",
                    condition_check=lambda v: v == "hitl_review",
                )
            )
            # Switch on hard gates triggered
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

    def _merge_plugin_config(
        self, base_config: dict[str, Any], plugin_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Merge plugin config with base profile config.

        Delegates to :meth:`ProfileLoader.merge_plugin_config`.
        """
        return self.profile_loader.merge_plugin_config(base_config, plugin_config)

    def _select_planning_strategy(
        self, strategy_name: str | None, params: dict[str, Any] | None
    ) -> PlanningStrategy:
        """Delegates to :func:`select_planning_strategy`."""
        return select_planning_strategy(strategy_name, params)

    # -------------------------------------------------------------------------
    # Tool methods - delegate to ToolBuilder
    # -------------------------------------------------------------------------

    async def _create_tools_from_allowlist(
        self,
        tool_allowlist: list[str],
        mcp_servers: list[dict[str, Any]],
        mcp_tool_allowlist: list[str],
        llm_provider: LLMProviderProtocol,
    ) -> list[ToolProtocol]:
        """Delegates to :meth:`ToolBuilder.create_tools_from_allowlist`."""
        return await self._tool_builder.create_tools_from_allowlist(
            tool_allowlist, mcp_servers, mcp_tool_allowlist, llm_provider
        )

    def _get_all_native_tools(
        self, llm_provider: LLMProviderProtocol
    ) -> list[ToolProtocol]:
        """Delegates to :meth:`ToolBuilder.get_all_native_tools`."""
        return self._tool_builder.get_all_native_tools(llm_provider)

    def _load_profile(self, profile: str) -> dict[str, Any]:
        """Delegates to :class:`ProfileLoader`."""
        return self.profile_loader.load(profile)

    def _create_context_policy(self, config: dict[str, Any]) -> ContextPolicy:
        """Create ContextPolicy from configuration."""
        context_config = config.get("context_policy")
        if context_config:
            return ContextPolicy.from_dict(context_config)
        return ContextPolicy.conservative_default()

    def _create_state_manager(
        self, config: dict[str, Any]
    ) -> StateManagerProtocol:
        """Create state manager based on configuration."""
        from taskforce.application.infrastructure_builder import (
            InfrastructureBuilder,
        )

        return InfrastructureBuilder(self.config_dir).build_state_manager(
            config
        )

    def _create_runtime_tracker(
        self,
        config: dict[str, Any],
        work_dir_override: str | None = None,
    ) -> AgentRuntimeTrackerProtocol | None:
        """Create runtime tracker based on configuration."""
        runtime_config = config.get("runtime", {})
        enabled = runtime_config.get("enabled", False)
        if not enabled:
            return None

        runtime_work_dir = runtime_config.get("work_dir")
        if not runtime_work_dir:
            runtime_work_dir = work_dir_override
        if not runtime_work_dir:
            runtime_work_dir = config.get("persistence", {}).get(
                "work_dir", ".taskforce"
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

    def _create_llm_provider(
        self, config: dict[str, Any]
    ) -> LLMProviderProtocol:
        """Create LLM provider based on configuration."""
        from taskforce.application.infrastructure_builder import (
            InfrastructureBuilder,
        )

        return InfrastructureBuilder(self.config_dir).build_llm_provider(
            config
        )

    def _create_native_tools(
        self,
        config: dict[str, Any],
        llm_provider: LLMProviderProtocol,
        user_context: dict[str, Any] | None = None,
    ) -> list[ToolProtocol]:
        """Delegates to :meth:`ToolBuilder.create_native_tools`."""
        return self._tool_builder.create_native_tools(
            config, llm_provider, user_context=user_context
        )

    def _build_orchestration_tool(
        self, config: dict[str, Any]
    ) -> ToolProtocol | None:
        """Delegates to :meth:`ToolBuilder.build_orchestration_tool`."""
        return self._tool_builder.build_orchestration_tool(config)

    def _hydrate_memory_tool_spec(
        self, tool_spec: str | dict[str, Any], config: dict[str, Any]
    ) -> str | dict[str, Any]:
        """Delegates to :meth:`ToolBuilder.hydrate_memory_tool_spec`."""
        return ToolBuilder.hydrate_memory_tool_spec(tool_spec, config)

    def _resolve_memory_store_dir(
        self, config: dict[str, Any], work_dir_override: str | None = None
    ) -> str:
        """Delegates to :meth:`ToolBuilder.resolve_memory_store_dir`."""
        return ToolBuilder.resolve_memory_store_dir(
            config, work_dir_override=work_dir_override
        )

    async def _create_mcp_tools(
        self, config: dict[str, Any]
    ) -> tuple[list[ToolProtocol], list[Any]]:
        """Delegates to :meth:`ToolBuilder.create_mcp_tools`."""
        return await self._tool_builder.create_mcp_tools(config)

    async def _build_tools(
        self,
        *,
        config: dict[str, Any],
        llm_provider: LLMProviderProtocol,
        user_context: dict[str, Any] | None = None,
        specialist: str | None = None,
        use_specialist_defaults: bool = False,
        include_mcp: bool = True,
    ) -> tuple[list[ToolProtocol], list[Any]]:
        """Delegates to :meth:`ToolBuilder.build_tools`."""
        return await self._tool_builder.build_tools(
            config=config,
            llm_provider=llm_provider,
            user_context=user_context,
            specialist=specialist,
            use_specialist_defaults=use_specialist_defaults,
            include_mcp=include_mcp,
        )

    def _create_default_tools(
        self, llm_provider: LLMProviderProtocol
    ) -> list[ToolProtocol]:
        """Delegates to :meth:`ToolBuilder.create_default_tools`."""
        return self._tool_builder.create_default_tools(llm_provider)

    def _create_specialist_tools(
        self,
        specialist: str,
        config: dict[str, Any],
        llm_provider: LLMProviderProtocol,
        user_context: dict[str, Any] | None = None,
    ) -> list[ToolProtocol]:
        """Delegates to :meth:`ToolBuilder.create_specialist_tools`."""
        return self._tool_builder.create_specialist_tools(
            specialist, config, llm_provider, user_context=user_context
        )

    def _instantiate_tool(
        self,
        tool_spec: str | dict[str, Any],
        llm_provider: LLMProviderProtocol,
        user_context: dict[str, Any] | None = None,
    ) -> ToolProtocol | None:
        """Delegates to :meth:`ToolBuilder.instantiate_tool`."""
        return self._tool_builder.instantiate_tool(
            tool_spec, llm_provider, user_context=user_context
        )

    def _instantiate_sub_agent_tool(
        self,
        tool_spec: dict[str, Any],
    ) -> ToolProtocol | None:
        """Delegates to :meth:`ToolBuilder.instantiate_sub_agent_tool`."""
        return self._tool_builder.instantiate_sub_agent_tool(tool_spec)

