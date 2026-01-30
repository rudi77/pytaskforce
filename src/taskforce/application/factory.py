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

import os
import sys
from pathlib import Path
from typing import Any, Optional


def get_base_path() -> Path:
    """
    Get base path for resource files, handling frozen executables.

    When running as a PyInstaller executable, resources are extracted to
    a temporary directory (sys._MEIPASS). When running as a normal Python
    script, returns the project root directory.

    Returns:
        Path to the base directory containing configs and other resources
    """
    if getattr(sys, "frozen", False):
        # Running as PyInstaller executable
        # Resources are extracted to sys._MEIPASS
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        # Running as script - navigate from factory.py to project root
        # factory.py is at: src/taskforce/application/factory.py
        # Project root is 4 levels up
        return Path(__file__).parent.parent.parent.parent


import structlog
import yaml

from taskforce.core.domain.context_policy import ContextPolicy
from taskforce.core.domain.agent import Agent
from taskforce.core.domain.planning_strategy import (
    NativeReActStrategy,
    PlanAndExecuteStrategy,
    PlanAndReactStrategy,
    PlanningStrategy,
)
from taskforce.core.interfaces.llm import LLMProviderProtocol
from taskforce.core.interfaces.runtime import AgentRuntimeTrackerProtocol
from taskforce.core.interfaces.state import StateManagerProtocol
from taskforce.core.interfaces.tools import ToolProtocol
from taskforce.core.prompts import build_system_prompt, format_tools_description
from taskforce.application.plugin_loader import PluginLoader, PluginManifest


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
        definition: "AgentDefinition",
        user_context: Optional[dict[str, Any]] = None,
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
        from taskforce.core.domain.agent_definition import AgentDefinition, AgentSource
        from taskforce.application.tool_resolver import ToolResolver
        from taskforce.application.infrastructure_builder import InfrastructureBuilder

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
        base_config = infra_builder.load_profile_safe(definition.base_profile)

        state_manager = infra_builder.build_state_manager(
            base_config, work_dir_override=definition.work_dir
        )
        llm_provider = infra_builder.build_llm_provider(base_config)

        # Build MCP tools
        mcp_tools, mcp_contexts = await infra_builder.build_mcp_tools(
            definition.mcp_servers,
            tool_filter=definition.mcp_tool_filter,
        )

        # Resolve native tools
        tool_resolver = ToolResolver(
            llm_provider=llm_provider,
            user_context=user_context,
        )
        native_tools = tool_resolver.resolve(definition.tools)

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
        selected_strategy = self._select_planning_strategy(strategy_name, strategy_params)

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
        definition: "AgentDefinition",
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
        definition: "AgentDefinition",
        tools: list[ToolProtocol],
    ) -> str:
        """Build system prompt for an agent definition."""
        from taskforce.core.prompts.autonomous_prompts import LEAN_KERNEL_PROMPT

        # If definition has custom prompt, use it
        if definition.has_custom_prompt:
            base_prompt = LEAN_KERNEL_PROMPT + "\n\n" + definition.system_prompt
        else:
            # Use specialist-based prompt
            return self._assemble_lean_system_prompt(definition.specialist, tools)

        # Format tools and build final prompt
        tools_description = format_tools_description(tools) if tools else ""
        return build_system_prompt(
            base_prompt=base_prompt,
            tools_description=tools_description,
        )

    # -------------------------------------------------------------------------
    # Legacy API (maintained for backwards compatibility)
    # -------------------------------------------------------------------------

    async def create_agent(
        self,
        profile: str = "dev",
        specialist: Optional[str] = None,
        work_dir: Optional[str] = None,
        user_context: Optional[dict[str, Any]] = None,
        planning_strategy: Optional[str] = None,
        planning_strategy_params: Optional[dict[str, Any]] = None,
    ) -> Agent:
        """
        Create Agent with simplified ReAct loop.

        Creates an Agent instance using native tool calling and PlannerTool
        for dynamic plan management. This is the new simplified architecture
        that replaces TodoListManager and custom JSON parsing.

        Key differences from create_agent():
        - Uses Agent (native tool calling) instead of legacy agent flow
        - No TodoListManager (replaced by PlannerTool)
        - No QueryRouter/fast-path logic
        - Uses LEAN_KERNEL_PROMPT by default
        - Native tool calling (no JSON parsing)

        Args:
            profile: Configuration profile name (dev/staging/prod)
            specialist: Specialist profile override. If None, uses LEAN_KERNEL_PROMPT.
            work_dir: Optional override for work directory
            user_context: Optional user context for RAG tools (user_id, org_id, scope)
            planning_strategy: Optional planning strategy override
            planning_strategy_params: Optional planning strategy parameters

        Returns:
            Agent instance with injected dependencies

        Raises:
            FileNotFoundError: If profile YAML not found

        Example:
            >>> factory = AgentFactory()
            >>> agent = await factory.create_agent(profile="dev")
            >>> result = await agent.execute("Do something", "session-123")
        """
        config = self._load_profile(profile)

        # Override work_dir if provided
        if work_dir:
            config.setdefault("persistence", {})["work_dir"] = work_dir

        # Determine specialist: parameter > config > default (None = lean kernel)
        effective_specialist = specialist or config.get("specialist")

        self.logger.info(
            "creating_lean_agent",
            profile=profile,
            specialist=effective_specialist,
            work_dir=config.get("persistence", {}).get("work_dir", ".taskforce"),
            has_user_context=user_context is not None,
        )

        # Instantiate infrastructure adapters (reuse existing methods)
        state_manager = self._create_state_manager(config)
        llm_provider = self._create_llm_provider(config)

        tools, mcp_contexts = await self._build_tools(
            config=config,
            llm_provider=llm_provider,
            user_context=user_context,
            include_mcp=True,
        )

        # Build system prompt - use LEAN_KERNEL_PROMPT or specialist variant
        system_prompt = self._assemble_lean_system_prompt(effective_specialist, tools)

        # Get model_alias from config
        llm_config = config.get("llm", {})
        model_alias = llm_config.get("default_model", "main")

        # Create ContextPolicy from config (Story 9.2)
        context_policy = self._create_context_policy(config)
        runtime_tracker = self._create_runtime_tracker(
            config,
            work_dir_override=config.get("persistence", {}).get("work_dir"),
        )
        runtime_tracker = self._create_runtime_tracker(
            config,
            work_dir_override=config.get("persistence", {}).get("work_dir"),
        )

        # Get max_steps from config (defaults to Agent.DEFAULT_MAX_STEPS if not specified)
        agent_config = config.get("agent", {})
        max_steps = agent_config.get("max_steps")  # None means use agent default
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
        selected_strategy = self._select_planning_strategy(strategy_name, strategy_params)

        self.logger.debug(
            "lean_agent_created",
            tools_count=len(tools),
            tool_names=[t.name for t in tools],
            model_alias=model_alias,
            context_policy_max_items=context_policy.max_items,
            max_steps=max_steps or "default",
            max_parallel_tools=max_parallel_tools or "default",
            planning_strategy=selected_strategy.name,
        )

        # Create logger for agent
        agent_logger = structlog.get_logger().bind(component="agent")

        agent = Agent(
            state_manager=state_manager,
            llm_provider=llm_provider,
            tools=tools,
            logger=agent_logger,
            system_prompt=system_prompt,
            model_alias=model_alias,
            context_policy=context_policy,
            max_steps=max_steps,
            max_parallel_tools=max_parallel_tools,
            planning_strategy=selected_strategy,
            runtime_tracker=runtime_tracker,
        )

        # Store MCP contexts on agent for lifecycle management
        agent._mcp_contexts = mcp_contexts

        # Apply plugin extensions
        agent = self._apply_extensions(config, agent)

        return agent

    def _assemble_lean_system_prompt(
        self, specialist: Optional[str], tools: list[ToolProtocol]
    ) -> str:
        """
        Assemble system prompt for Agent.

        Uses LEAN_KERNEL_PROMPT as base, optionally adding specialist instructions.
        The LEAN_KERNEL_PROMPT includes planning behavior rules that work with
        the PlannerTool for dynamic context injection.

        Args:
            specialist: Optional specialist profile ("coding", "rag", None)
            tools: List of available tools

        Returns:
            Assembled system prompt string
        """
        from taskforce.core.prompts.autonomous_prompts import (
            CODING_SPECIALIST_PROMPT,
            LEAN_KERNEL_PROMPT,
            RAG_SPECIALIST_PROMPT,
            WIKI_SYSTEM_PROMPT,
        )

        # Start with LEAN_KERNEL_PROMPT
        base_prompt = LEAN_KERNEL_PROMPT

        # Optionally add specialist instructions
        if specialist == "coding":
            base_prompt += "\n\n" + CODING_SPECIALIST_PROMPT
        elif specialist == "rag":
            base_prompt += "\n\n" + RAG_SPECIALIST_PROMPT
        elif specialist == "wiki":
            base_prompt += "\n\n" + WIKI_SYSTEM_PROMPT

        # Format tools description and inject
        tools_description = format_tools_description(tools) if tools else ""
        system_prompt = build_system_prompt(
            base_prompt=base_prompt,
            tools_description=tools_description,
        )

        self.logger.debug(
            "lean_system_prompt_assembled",
            specialist=specialist,
            tools_count=len(tools),
            prompt_length=len(system_prompt),
        )

        return system_prompt

    async def create_agent_from_definition(
        self,
        agent_definition: dict[str, Any],
        profile: str = "dev",
        work_dir: Optional[str] = None,
        planning_strategy: Optional[str] = None,
        planning_strategy_params: Optional[dict[str, Any]] = None,
    ) -> Agent:
        """
        Create Agent from custom agent definition.

        This method is used by Story 8.3 to create agents from stored
        custom agent definitions (loaded from configs/custom/{agent_id}.yaml).

        The agent_definition provides:
        - system_prompt: Custom prompt for the agent
        - tool_allowlist: List of allowed native tool names
        - mcp_servers: Optional MCP server configurations
        - mcp_tool_allowlist: Optional list of allowed MCP tool names

        The profile parameter controls infrastructure settings:
        - LLM config, logging, persistence work_dir
        - Does NOT override the custom agent's prompt/toolset

        Args:
            agent_definition: Agent definition dict with system_prompt,
                            tool_allowlist, mcp_servers, mcp_tool_allowlist
            profile: Configuration profile for infrastructure settings
            work_dir: Optional override for work directory
            planning_strategy: Optional planning strategy override
            planning_strategy_params: Optional planning strategy parameters

        Returns:
            Agent instance configured from definition

        Raises:
            FileNotFoundError: If profile YAML not found
            ValueError: If agent_definition is invalid

        Example:
            >>> factory = AgentFactory()
            >>> definition = {
            ...     "system_prompt": "You are a helpful assistant",
            ...     "tool_allowlist": ["web_search", "python"],
            ...     "mcp_servers": [],
            ...     "mcp_tool_allowlist": []
            ... }
            >>> agent = await factory.create_agent_from_definition(
            ...     definition, profile="dev"
            ... )
        """
        # Load profile for infrastructure settings
        # _load_profile() will handle fallback if profile doesn't exist
        # (checks configs/custom/ as fallback)
        config = self._load_profile(profile)

        # Override work_dir if provided
        if work_dir:
            config.setdefault("persistence", {})["work_dir"] = work_dir

        self.logger.info(
            "creating_lean_agent_from_definition",
            profile=profile,
            work_dir=config.get("persistence", {}).get("work_dir", ".taskforce"),
            tool_allowlist=agent_definition.get("tool_allowlist", []),
            has_mcp_servers=bool(agent_definition.get("mcp_servers", [])),
        )

        # Instantiate infrastructure adapters
        state_manager = self._create_state_manager(config)
        llm_provider = self._create_llm_provider(config)

        # Create tools filtered by allowlist
        tools = await self._create_tools_from_allowlist(
            tool_allowlist=agent_definition.get("tool_allowlist", []),
            mcp_servers=agent_definition.get("mcp_servers", []),
            mcp_tool_allowlist=agent_definition.get("mcp_tool_allowlist", []),
            llm_provider=llm_provider,
        )

        # Use custom system prompt from definition
        system_prompt = agent_definition.get("system_prompt", "")
        if not system_prompt:
            raise ValueError("agent_definition must include 'system_prompt'")

        # Get model_alias from config
        llm_config = config.get("llm", {})
        model_alias = llm_config.get("default_model", "main")

        # Create ContextPolicy from config (Story 9.2)
        context_policy = self._create_context_policy(config)

        # Get max_steps from config (defaults to Agent.DEFAULT_MAX_STEPS if not specified)
        agent_config = config.get("agent", {})
        max_steps = agent_config.get("max_steps")  # None means use agent default
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
        selected_strategy = self._select_planning_strategy(strategy_name, strategy_params)

        self.logger.debug(
            "lean_agent_from_definition_created",
            tools_count=len(tools),
            tool_names=[t.name for t in tools],
            model_alias=model_alias,
            prompt_length=len(system_prompt),
            context_policy_max_items=context_policy.max_items,
            max_steps=max_steps or "default",
            max_parallel_tools=max_parallel_tools or "default",
            planning_strategy=selected_strategy.name,
        )

        # Create logger for agent
        agent_logger = structlog.get_logger().bind(component="agent")

        agent = Agent(
            state_manager=state_manager,
            llm_provider=llm_provider,
            tools=tools,
            logger=agent_logger,
            system_prompt=system_prompt,
            model_alias=model_alias,
            context_policy=context_policy,
            max_steps=max_steps,
            max_parallel_tools=max_parallel_tools,
            planning_strategy=selected_strategy,
            runtime_tracker=runtime_tracker,
        )

        # Store MCP contexts on agent for lifecycle management
        # (contexts are stored in tools list, no separate tracking needed)
        agent._mcp_contexts = []

        # Apply plugin extensions
        agent = self._apply_extensions(config, agent)

        return agent

    async def create_agent_with_plugin(
        self,
        plugin_path: str,
        profile: str = "dev",
        user_context: Optional[dict[str, Any]] = None,
        planning_strategy: Optional[str] = None,
        planning_strategy_params: Optional[dict[str, Any]] = None,
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
        try:
            base_config = self._load_profile(profile)
        except FileNotFoundError:
            self.logger.debug(
                "base_profile_not_found_using_defaults",
                profile=profile,
                hint="Using minimal defaults for infrastructure settings",
            )
            # Minimal defaults when no base profile exists
            base_config = {
                "persistence": {"type": "file", "work_dir": ".taskforce"},
                "llm": {
                    "config_path": "src/taskforce_extensions/configs/llm_config.yaml",
                    "default_model": "main",
                },
                "logging": {"level": "WARNING"},
            }

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

        # Build system prompt - check if plugin provides custom prompt
        custom_prompt = plugin_config.get("system_prompt")
        if custom_prompt:
            # LEAN_KERNEL + Plugin-Prompt (ergänzen, nicht ersetzen)
            from taskforce.core.prompts.autonomous_prompts import LEAN_KERNEL_PROMPT

            base_prompt = LEAN_KERNEL_PROMPT + "\n\n" + custom_prompt
            tools_description = format_tools_description(all_tools) if all_tools else ""
            system_prompt = build_system_prompt(
                base_prompt=base_prompt,
                tools_description=tools_description,
            )
            self.logger.debug(
                "plugin_custom_prompt_assembled",
                plugin=manifest.name,
                prompt_length=len(system_prompt),
            )
        else:
            # Fallback to specialist-based prompt
            specialist = plugin_config.get("specialist")
            system_prompt = self._assemble_lean_system_prompt(specialist, all_tools)

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
        selected_strategy = self._select_planning_strategy(strategy_name, strategy_params)

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

        # Create logger for agent
        agent_logger = structlog.get_logger().bind(component="agent")

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
        )

        # Store MCP contexts and plugin manifest for lifecycle management
        agent._mcp_contexts = mcp_contexts
        agent._plugin_manifest = manifest

        # Apply plugin extensions
        agent = self._apply_extensions(merged_config, agent)

        return agent

    def _merge_plugin_config(
        self, base_config: dict[str, Any], plugin_config: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Merge plugin config with base profile config.

        Priority (highest to lowest):
        1. Plugin config values (for agent settings)
        2. Base profile values (for infrastructure)

        Infrastructure settings (LLM, persistence type) always come from base
        for security reasons. Plugin can override:
        - agent settings (max_steps, planning_strategy)
        - context_policy
        - persistence work_dir
        - specialist

        Args:
            base_config: Base profile configuration
            plugin_config: Plugin-specific configuration

        Returns:
            Merged configuration dictionary
        """
        import copy

        merged = copy.deepcopy(base_config)

        # Agent settings from plugin
        if "agent" in plugin_config:
            merged.setdefault("agent", {}).update(plugin_config["agent"])

        # Context policy from plugin
        if "context_policy" in plugin_config:
            merged["context_policy"] = plugin_config["context_policy"]

        # Specialist from plugin
        if "specialist" in plugin_config:
            merged["specialist"] = plugin_config["specialist"]

        # Work dir from plugin (allows plugin-specific workspace)
        if plugin_config.get("persistence", {}).get("work_dir"):
            merged.setdefault("persistence", {})["work_dir"] = plugin_config["persistence"][
                "work_dir"
            ]

        # MCP servers from plugin (additive)
        if "mcp_servers" in plugin_config:
            base_mcp = merged.get("mcp_servers", [])
            plugin_mcp = plugin_config["mcp_servers"]
            merged["mcp_servers"] = base_mcp + plugin_mcp

        return merged

    def _select_planning_strategy(
        self, strategy_name: str | None, params: dict[str, Any] | None
    ) -> PlanningStrategy:
        """
        Select and instantiate planning strategy for Agent.

        Args:
            strategy_name: Strategy name (native_react, plan_and_execute, plan_and_react)
            params: Optional strategy parameters

        Returns:
            PlanningStrategy instance

        Raises:
            ValueError: If strategy name is invalid or params are malformed
        """
        normalized = (strategy_name or "native_react").strip().lower().replace("-", "_")
        params = params or {}
        if not isinstance(params, dict):
            raise ValueError("planning_strategy_params must be a dictionary")

        # Create logger for strategy injection
        logger = structlog.get_logger().bind(component=f"{normalized}_strategy")

        if normalized == "native_react":
            return NativeReActStrategy()
        if normalized == "plan_and_execute":
            max_step_iterations_value = params.get("max_step_iterations")
            max_plan_steps_value = params.get("max_plan_steps")
            return PlanAndExecuteStrategy(
                max_step_iterations=(
                    int(max_step_iterations_value) if max_step_iterations_value is not None else 4
                ),
                max_plan_steps=(
                    int(max_plan_steps_value) if max_plan_steps_value is not None else 12
                ),
                logger=logger,
            )
        if normalized == "plan_and_react":
            max_plan_steps_value = params.get("max_plan_steps")
            return PlanAndReactStrategy(
                max_plan_steps=(
                    int(max_plan_steps_value) if max_plan_steps_value is not None else 12
                ),
                logger=logger,
            )

        raise ValueError(
            "Invalid planning_strategy. Supported values: native_react, plan_and_execute, "
            "plan_and_react"
        )

    async def _create_tools_from_allowlist(
        self,
        tool_allowlist: list[str],
        mcp_servers: list[dict[str, Any]],
        mcp_tool_allowlist: list[str],
        llm_provider: LLMProviderProtocol,
    ) -> list[ToolProtocol]:
        """
        Create tools filtered by allowlist.

        Creates native tools and MCP tools, filtering by their respective allowlists.

        Args:
            tool_allowlist: List of allowed native tool names
            mcp_servers: MCP server configurations
            mcp_tool_allowlist: List of allowed MCP tool names (empty = all allowed)
            llm_provider: LLM provider for tools that need it

        Returns:
            List of tool instances matching allowlists
        """
        tools = []

        # Create native tools filtered by allowlist
        if tool_allowlist:
            available_native_tools = self._get_all_native_tools(llm_provider)
            for tool in available_native_tools:
                if tool.name in tool_allowlist:
                    tools.append(tool)
                    self.logger.debug(
                        "native_tool_added",
                        tool_name=tool.name,
                        reason="in_tool_allowlist",
                    )

        # Create MCP tools if configured
        if mcp_servers:
            # Temporarily inject mcp_servers into a config dict
            temp_config = {"mcp_servers": mcp_servers}
            mcp_tools, mcp_contexts = await self._create_mcp_tools(temp_config)

            # Filter MCP tools by allowlist if specified
            if mcp_tool_allowlist:
                filtered_mcp_tools = [t for t in mcp_tools if t.name in mcp_tool_allowlist]
                self.logger.debug(
                    "mcp_tools_filtered",
                    original_count=len(mcp_tools),
                    filtered_count=len(filtered_mcp_tools),
                    allowlist=mcp_tool_allowlist,
                )
                tools.extend(filtered_mcp_tools)
            else:
                # No allowlist = all MCP tools allowed
                tools.extend(mcp_tools)

        return tools

    def _get_all_native_tools(self, llm_provider: LLMProviderProtocol) -> list[ToolProtocol]:
        """
        Get all available native tools.

        Returns the complete set of native tools that can be filtered
        by allowlist.

        Args:
            llm_provider: LLM provider (unused but kept for consistency)

        Returns:
            List of all native tool instances
        """
        from taskforce.infrastructure.tools.native.ask_user_tool import AskUserTool
        from taskforce.infrastructure.tools.native.file_tools import (
            FileReadTool,
            FileWriteTool,
        )
        from taskforce.infrastructure.tools.native.git_tools import GitHubTool, GitTool
        from taskforce.infrastructure.tools.native.python_tool import PythonTool
        from taskforce.infrastructure.tools.native.shell_tool import PowerShellTool
        from taskforce.infrastructure.tools.native.web_tools import (
            WebFetchTool,
            WebSearchTool,
        )

        return [
            WebSearchTool(),
            WebFetchTool(),
            PythonTool(),
            GitHubTool(),
            GitTool(),
            FileReadTool(),
            FileWriteTool(),
            PowerShellTool(),
            AskUserTool(),
        ]

    def _load_profile(self, profile: str) -> dict:
        """
        Load configuration profile from YAML file.

        Searches in:
        1. configs/{profile}.yaml (standard profiles)
        2. configs/custom/{profile}.yaml (custom agents as fallback)

        Args:
            profile: Profile name (dev/staging/prod) or custom agent ID

        Returns:
            Configuration dictionary

        Raises:
            FileNotFoundError: If profile YAML not found in either location
        """
        # First try standard profile location
        profile_path = self.config_dir / f"{profile}.yaml"

        if not profile_path.exists():
            # Fallback: check if it's a custom agent
            custom_path = self.config_dir / "custom" / f"{profile}.yaml"
            if custom_path.exists():
                self.logger.debug(
                    "profile_using_custom_agent",
                    profile=profile,
                    custom_path=str(custom_path),
                )
                # Custom agents have complete configuration, use directly
                profile_path = custom_path
            else:
                # Don't log error here - let caller decide how to handle
                # (e.g., create_agent_with_plugin uses defaults as fallback)
                raise FileNotFoundError(f"Profile not found: {profile_path} or {custom_path}")

        with open(profile_path) as f:
            config = yaml.safe_load(f)

        self.logger.debug("profile_loaded", profile=profile, config_keys=list(config.keys()))
        return config

    def _create_context_policy(self, config: dict) -> ContextPolicy:
        """
        Create ContextPolicy from configuration.

        Reads context_policy section from config YAML and creates a
        ContextPolicy instance. Falls back to conservative default if
        no policy is configured.

        Args:
            config: Configuration dictionary

        Returns:
            ContextPolicy instance
        """
        context_config = config.get("context_policy")

        if context_config:
            self.logger.debug("creating_context_policy_from_config", config=context_config)
            return ContextPolicy.from_dict(context_config)
        else:
            self.logger.debug("using_conservative_default_context_policy")
            return ContextPolicy.conservative_default()

    def _create_state_manager(self, config: dict) -> StateManagerProtocol:
        """
        Create state manager based on configuration.

        Args:
            config: Configuration dictionary

        Returns:
            StateManager implementation (file-based or database)
        """
        persistence_config = config.get("persistence", {})
        persistence_type = persistence_config.get("type", "file")

        if persistence_type == "file":
            from taskforce.infrastructure.persistence.file_state_manager import FileStateManager

            work_dir = persistence_config.get("work_dir", ".taskforce")
            return FileStateManager(work_dir=work_dir)

        elif persistence_type == "database":
            from taskforce.infrastructure.persistence.db_state import DbStateManager

            # Get database URL from config or environment
            db_url_env = persistence_config.get("db_url_env", "DATABASE_URL")
            db_url = os.getenv(db_url_env)

            if not db_url:
                raise ValueError(f"Database URL not found in environment variable: {db_url_env}")

            return DbStateManager(db_url=db_url)

        else:
            raise ValueError(f"Unknown persistence type: {persistence_type}")

    def _create_runtime_tracker(
        self,
        config: dict,
        work_dir_override: str | None = None,
    ) -> AgentRuntimeTrackerProtocol | None:
        runtime_config = config.get("runtime", {})
        enabled = runtime_config.get("enabled", False)
        if not enabled:
            return None

        runtime_work_dir = runtime_config.get("work_dir")
        if not runtime_work_dir:
            runtime_work_dir = work_dir_override
        if not runtime_work_dir:
            runtime_work_dir = config.get("persistence", {}).get("work_dir", ".taskforce")

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

    def _create_llm_provider(self, config: dict) -> LLMProviderProtocol:
        """
        Create LLM provider based on configuration.

        Args:
            config: Configuration dictionary

        Returns:
            LLM provider implementation (OpenAI)
        """
        from taskforce.infrastructure.llm.openai_service import OpenAIService

        llm_config = config.get("llm", {})
        config_path = llm_config.get(
            "config_path", "src/taskforce_extensions/configs/llm_config.yaml"
        )

        # Resolve relative paths against base path (handles frozen executables)
        config_path_obj = Path(config_path)
        if not config_path_obj.is_absolute():
            resolved_path = get_base_path() / config_path

            # Backward compatibility: if old path doesn't exist, try new location
            if not resolved_path.exists() and config_path.startswith("configs/"):
                # Try new location: src/taskforce_extensions/configs/...
                new_path = get_base_path() / "src" / "taskforce_extensions" / config_path
                if new_path.exists():
                    resolved_path = new_path
                    self.logger.debug(
                        "llm_config_path_migrated",
                        old_path=config_path,
                        new_path=str(new_path),
                    )

            config_path = str(resolved_path)

        return OpenAIService(config_path=config_path)

    def _create_native_tools(
        self,
        config: dict,
        llm_provider: LLMProviderProtocol,
        user_context: Optional[dict[str, Any]] = None,
    ) -> list[ToolProtocol]:
        """
        Create native tools from configuration.

        Args:
            config: Configuration dictionary
            llm_provider: LLM provider for LLMTool
            user_context: Optional user context for RAG tools

        Returns:
            List of native tool instances

        Note:
            LLMTool (llm_generate) is filtered out unless `agent.include_llm_generate: true`
            is set in the config. This is intentional - the agent should use its internal
            LLM capabilities for text generation rather than calling a tool.
        """
        tools_config = config.get("tools", [])

        if not tools_config:
            # Fallback to default tool set if no config provided
            return self._create_default_tools(llm_provider)

        tools = []
        for tool_spec in tools_config:
            tool = self._instantiate_tool(tool_spec, llm_provider, user_context=user_context)
            if tool:
                tools.append(tool)

        # Add AgentTool if orchestration is enabled (Feature: Multi-Agent Orchestration)
        orchestration_config = config.get("orchestration", {})
        if orchestration_config.get("enabled", False):
            from taskforce.application.sub_agent_spawner import SubAgentSpawner
            from taskforce.infrastructure.tools.orchestration import AgentTool

            sub_agent_spawner = SubAgentSpawner(
                agent_factory=self,
                profile=orchestration_config.get("sub_agent_profile", "dev"),
                work_dir=orchestration_config.get("sub_agent_work_dir"),
                max_steps=orchestration_config.get("sub_agent_max_steps"),
            )
            agent_tool = AgentTool(
                agent_factory=self,
                sub_agent_spawner=sub_agent_spawner,
                profile=orchestration_config.get("sub_agent_profile", "dev"),
                work_dir=orchestration_config.get("sub_agent_work_dir"),
                max_steps=orchestration_config.get("sub_agent_max_steps"),
                summarize_results=orchestration_config.get("summarize_results", False),
                summary_max_length=orchestration_config.get("summary_max_length", 2000),
            )
            tools.append(agent_tool)

            self.logger.info(
                "orchestration_enabled",
                agent_tool_added=True,
                sub_agent_profile=orchestration_config.get("sub_agent_profile", "dev"),
                sub_agent_max_steps=orchestration_config.get("sub_agent_max_steps"),
            )

        # Filter out LLMTool unless explicitly enabled in config
        include_llm_generate = config.get("agent", {}).get("include_llm_generate", False)
        if not include_llm_generate:
            original_count = len(tools)
            tools = [t for t in tools if t.name != "llm_generate"]
            if len(tools) < original_count:
                self.logger.debug(
                    "llm_generate_filtered",
                    reason="include_llm_generate is False (default)",
                    remaining_tools=[t.name for t in tools],
                )

        return tools

    async def _create_mcp_tools(self, config: dict) -> tuple[list[ToolProtocol], list[Any]]:
        """
        Create MCP tools from configuration.

        Connects to configured MCP servers (stdio or SSE), fetches available tools,
        and wraps them in MCPToolWrapper to conform to ToolProtocol.

        IMPORTANT: Returns both tools and client context managers that must be kept alive.
        The caller is responsible for managing the lifecycle of these connections.

        Args:
            config: Configuration dictionary containing mcp_servers list

        Returns:
            Tuple of (list of MCP tool wrappers, list of client context managers)

        Example config:
            mcp_servers:
              - type: stdio
                command: python
                args: ["server.py"]
                env: {"API_KEY": "value"}
              - type: sse
                url: http://localhost:8000/sse
        """
        from taskforce.core.domain.agent_definition import MCPServerConfig
        from taskforce.infrastructure.tools.mcp.connection_manager import (
            create_default_connection_manager,
        )

        mcp_servers_config = config.get("mcp_servers", [])

        if not mcp_servers_config:
            self.logger.debug("no_mcp_servers_configured")
            return [], []

        # Convert dict configs to MCPServerConfig objects
        server_configs = [
            MCPServerConfig.from_dict(s) if isinstance(s, dict) else s for s in mcp_servers_config
        ]

        # Use centralized connection manager
        manager = create_default_connection_manager()
        return await manager.connect_all(server_configs)

    async def _build_tools(
        self,
        *,
        config: dict,
        llm_provider: LLMProviderProtocol,
        user_context: Optional[dict[str, Any]] = None,
        specialist: Optional[str] = None,
        use_specialist_defaults: bool = False,
        include_mcp: bool = True,
    ) -> tuple[list[ToolProtocol], list[Any]]:
        """Build tool list and MCP contexts based on configuration."""
        tools_config = config.get("tools", [])
        has_config_tools = bool(tools_config)

        if has_config_tools:
            self.logger.debug(
                "using_config_tools",
                specialist=specialist,
                tool_count=len(tools_config),
            )
            tools = self._create_native_tools(config, llm_provider, user_context=user_context)
        elif use_specialist_defaults and specialist in ("coding", "rag"):
            self.logger.debug("using_specialist_defaults", specialist=specialist)
            tools = self._create_specialist_tools(
                specialist, config, llm_provider, user_context=user_context
            )
        else:
            tools = self._create_default_tools(llm_provider)

        if not include_mcp:
            return tools, []

        mcp_tools, mcp_contexts = await self._create_mcp_tools(config)
        tools.extend(mcp_tools)
        return tools, mcp_contexts

    def _create_default_tools(self, llm_provider: LLMProviderProtocol) -> list[ToolProtocol]:
        """
        Create default tool set (fallback when no config provided).

        NOTE: LLMTool is intentionally EXCLUDED from default tools.
        The agent's internal LLM capabilities should be used for text generation.
        LLMTool can be added explicitly via config if needed for specialized use cases.

        Args:
            llm_provider: LLM provider (unused - kept for API compatibility)

        Returns:
            List of default tool instances
        """
        from taskforce.infrastructure.tools.native.ask_user_tool import AskUserTool
        from taskforce.infrastructure.tools.native.file_tools import (
            FileReadTool,
            FileWriteTool,
        )
        from taskforce.infrastructure.tools.native.git_tools import GitHubTool, GitTool

        # REMOVED: LLMTool - Agent uses internal LLM for text generation
        from taskforce.infrastructure.tools.native.python_tool import PythonTool
        from taskforce.infrastructure.tools.native.shell_tool import PowerShellTool
        from taskforce.infrastructure.tools.native.web_tools import (
            WebFetchTool,
            WebSearchTool,
        )

        # Standard tool set - LLMTool intentionally excluded for efficiency
        return [
            WebSearchTool(),
            WebFetchTool(),
            PythonTool(),
            GitHubTool(),
            GitTool(),
            FileReadTool(),
            FileWriteTool(),
            PowerShellTool(),
            # LLMTool excluded - Agent uses internal LLM capabilities
            AskUserTool(),
        ]

    def _create_specialist_tools(
        self,
        specialist: str,
        config: dict,
        llm_provider: LLMProviderProtocol,
        user_context: Optional[dict[str, Any]] = None,
    ) -> list[ToolProtocol]:
        """
        Create tools specific to a specialist profile.

        Each specialist profile has a focused toolset:
        - coding: FileReadTool, FileWriteTool, PowerShellTool, AskUserTool
        - rag: SemanticSearchTool, ListDocumentsTool, GetDocumentTool, AskUserTool

        Args:
            specialist: Specialist profile ("coding" or "rag")
            config: Configuration dictionary (for RAG tools configuration)
            llm_provider: LLM provider (unused for specialist tools currently)
            user_context: Optional user context for RAG tools

        Returns:
            List of specialist tool instances

        Raises:
            ValueError: If specialist profile is unknown
        """
        from taskforce.infrastructure.tools.native.ask_user_tool import AskUserTool

        if specialist == "coding":
            from taskforce.infrastructure.tools.native.file_tools import (
                FileReadTool,
                FileWriteTool,
            )
            from taskforce.infrastructure.tools.native.shell_tool import PowerShellTool

            self.logger.debug(
                "creating_specialist_tools",
                specialist="coding",
                tools=["FileReadTool", "FileWriteTool", "PowerShellTool", "AskUserTool"],
            )

            return [
                FileReadTool(),
                FileWriteTool(),
                PowerShellTool(),
                AskUserTool(),
            ]

        elif specialist == "rag":
            from taskforce.infrastructure.tools.rag.get_document_tool import GetDocumentTool
            from taskforce.infrastructure.tools.rag.list_documents_tool import (
                ListDocumentsTool,
            )
            from taskforce.infrastructure.tools.rag.semantic_search_tool import (
                SemanticSearchTool,
            )

            self.logger.debug(
                "creating_specialist_tools",
                specialist="rag",
                tools=[
                    "SemanticSearchTool",
                    "ListDocumentsTool",
                    "GetDocumentTool",
                    "AskUserTool",
                ],
                has_user_context=user_context is not None,
            )

            return [
                SemanticSearchTool(user_context=user_context),
                ListDocumentsTool(user_context=user_context),
                GetDocumentTool(user_context=user_context),
                AskUserTool(),
            ]

        else:
            raise ValueError(f"Unknown specialist profile: {specialist}")

    def _instantiate_tool(
        self,
        tool_spec: str | dict[str, Any],
        llm_provider: LLMProviderProtocol,
        user_context: Optional[dict[str, Any]] = None,
    ) -> Optional[ToolProtocol]:
        """
        Instantiate a tool from configuration specification.

        Args:
            tool_spec: Tool specification dict or short tool name
            llm_provider: LLM provider for tools that need it
            user_context: Optional user context for RAG tools

        Returns:
            Tool instance or None if instantiation fails
        """
        import importlib
        from taskforce.infrastructure.tools.registry import resolve_tool_spec

        resolved_spec = resolve_tool_spec(tool_spec)
        if not resolved_spec:
            self.logger.warning(
                "invalid_tool_spec",
                tool_spec=tool_spec,
                hint="Tool spec must include 'type' or be a known tool name",
            )
            return None

        tool_type = resolved_spec.get("type")
        tool_module = resolved_spec.get("module")
        tool_params = resolved_spec.get("params", {}).copy()

        try:
            # Import the module
            module = importlib.import_module(tool_module)

            # Get the tool class
            tool_class = getattr(module, tool_type)

            # Special handling for LLMTool - inject llm_service
            if tool_type == "LLMTool":
                tool_params["llm_service"] = llm_provider

            # Special handling for RAG tools - inject user_context
            if tool_type in ["SemanticSearchTool", "ListDocumentsTool", "GetDocumentTool"]:
                if user_context:
                    tool_params["user_context"] = user_context

            # Instantiate the tool with params
            tool_instance = tool_class(**tool_params)

            self.logger.debug(
                "tool_instantiated",
                tool_type=tool_type,
                tool_name=tool_instance.name,
            )

            return tool_instance

        except Exception as e:
            self.logger.error(
                "tool_instantiation_failed",
                tool_type=tool_type,
                tool_module=tool_module,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    # Backwards-compatible aliases (deprecated)
    async def create_lean_agent(self, *args, **kwargs) -> Agent:
        """Deprecated: Use create_agent instead."""
        return await self.create_agent(*args, **kwargs)

    async def create_lean_agent_from_definition(self, *args, **kwargs) -> Agent:
        """Deprecated: Use create_agent_from_definition instead."""
        return await self.create_agent_from_definition(*args, **kwargs)
