"""Tool Builder - Extracted from AgentFactory.

Handles all tool instantiation, resolution, and filtering logic:
- Native tool creation from config specs
- MCP tool creation via connection manager
- Specialist tool sets (coding)
- Memory tool hydration
"""

from __future__ import annotations

import importlib
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from taskforce.core.interfaces.llm import LLMProviderProtocol
from taskforce.core.interfaces.tool_resolver import ToolResolverProtocol
from taskforce.core.interfaces.tools import ToolProtocol

if TYPE_CHECKING:
    from taskforce.application.factory import AgentFactory

logger = structlog.get_logger(__name__)


class ToolBuilder:
    """Builds and resolves tools for agent creation.

    Extracted from AgentFactory to separate tool management concerns
    from the main dependency injection logic.

    Args:
        agent_factory: Reference to the parent factory (needed for
            sub-agent tool creation which requires the factory for
            spawning child agents).
        tool_resolver: Optional resolver for tool name → instance resolution.
            When provided, all tool resolution delegates to this resolver
            instead of creating ad-hoc ToolRegistry instances. This ensures
            consistent dependency injection across all code paths.
    """

    def __init__(
        self,
        agent_factory: AgentFactory,
        tool_resolver: ToolResolverProtocol | None = None,
    ) -> None:
        self._factory = agent_factory
        self._resolver = tool_resolver
        self._logger = logger.bind(component="tool_builder")

    def set_resolver(self, resolver: ToolResolverProtocol | None) -> None:
        """Set or update the tool resolver for subsequent operations.

        This allows the factory to wire a properly-configured resolver
        before each tool-building operation, since DI dependencies
        vary per agent creation context.
        """
        self._resolver = resolver

    # -------------------------------------------------------------------------
    # High-level builders
    # -------------------------------------------------------------------------

    async def build_tools(
        self,
        *,
        config: dict[str, Any],
        llm_provider: LLMProviderProtocol,
        user_context: dict[str, Any] | None = None,
        specialist: str | None = None,
        use_specialist_defaults: bool = False,
        include_mcp: bool = True,
    ) -> tuple[list[ToolProtocol], list[Any]]:
        """Build tool list and MCP contexts based on configuration."""
        tools_config = config.get("tools", [])
        has_config_tools = bool(tools_config)

        if has_config_tools:
            self._logger.debug(
                "using_config_tools",
                specialist=specialist,
                tool_count=len(tools_config),
            )
            tools = self.create_native_tools(
                config, llm_provider, user_context=user_context
            )
        elif use_specialist_defaults and specialist == "coding":
            self._logger.debug(
                "using_specialist_defaults", specialist=specialist
            )
            tools = self.create_specialist_tools(
                specialist, config, llm_provider, user_context=user_context
            )
        else:
            tools = self.create_default_tools(llm_provider)

        if not include_mcp:
            return tools, []

        mcp_tools, mcp_contexts = await self.create_mcp_tools(config)
        tools.extend(mcp_tools)
        return tools, mcp_contexts

    async def create_tools_from_allowlist(
        self,
        tool_allowlist: list[str],
        mcp_servers: list[dict[str, Any]],
        mcp_tool_allowlist: list[str],
        llm_provider: LLMProviderProtocol,
    ) -> list[ToolProtocol]:
        """Create tools filtered by allowlist.

        Only instantiates the tools in the allowlist instead of creating
        all 30+ tools and filtering afterwards.

        Args:
            tool_allowlist: List of allowed native tool names.
            mcp_servers: MCP server configurations.
            mcp_tool_allowlist: Allowed MCP tool names (empty = all).
            llm_provider: LLM provider for tools that need it.

        Returns:
            List of tool instances matching allowlists.
        """
        tools: list[ToolProtocol] = []

        if tool_allowlist:
            if self._resolver:
                tools = self._resolver.resolve(tool_allowlist)
            else:
                from taskforce.application.tool_registry import ToolRegistry

                registry = ToolRegistry(llm_provider=llm_provider)
                tools = registry.resolve(tool_allowlist)
            for tool in tools:
                self._logger.debug(
                    "native_tool_added",
                    tool_name=tool.name,
                    reason="in_tool_allowlist",
                )

        if mcp_servers:
            temp_config: dict[str, Any] = {"mcp_servers": mcp_servers}
            mcp_tools, _mcp_contexts = await self.create_mcp_tools(temp_config)

            if mcp_tool_allowlist:
                filtered = [
                    t for t in mcp_tools if t.name in mcp_tool_allowlist
                ]
                self._logger.debug(
                    "mcp_tools_filtered",
                    original_count=len(mcp_tools),
                    filtered_count=len(filtered),
                    allowlist=mcp_tool_allowlist,
                )
                tools.extend(filtered)
            else:
                tools.extend(mcp_tools)

        return tools

    # -------------------------------------------------------------------------
    # Native tools
    # -------------------------------------------------------------------------

    def create_native_tools(
        self,
        config: dict[str, Any],
        llm_provider: LLMProviderProtocol,
        user_context: dict[str, Any] | None = None,
    ) -> list[ToolProtocol]:
        """Create native tools from configuration.

        Args:
            config: Configuration dictionary.
            llm_provider: LLM provider for LLMTool.
            user_context: Optional user context.

        Returns:
            List of native tool instances.
        """
        tools_config = config.get("tools", [])

        if not tools_config:
            return self.create_default_tools(llm_provider)

        if self._resolver:
            tool_names = self._extract_tool_names(tools_config, config)
            tools = self._resolver.resolve(tool_names)
        else:
            tools = self._instantiate_tools_legacy(tools_config, config, llm_provider, user_context)

        include_llm_generate = config.get("agent", {}).get(
            "include_llm_generate", False
        )
        if not include_llm_generate:
            original_count = len(tools)
            tools = [t for t in tools if t.name != "llm_generate"]
            if len(tools) < original_count:
                self._logger.debug(
                    "llm_generate_filtered",
                    reason="include_llm_generate is False (default)",
                    remaining_tools=[t.name for t in tools],
                )

        return tools

    def _extract_tool_names(
        self,
        tools_config: list[Any],
        config: dict[str, Any],
    ) -> list[str]:
        """Extract tool names from config specs for resolver-based resolution."""
        names: list[str] = []
        for tool_spec in tools_config:
            if isinstance(tool_spec, str):
                names.append(tool_spec)
            elif isinstance(tool_spec, dict):
                name = tool_spec.get("name") or tool_spec.get("type", "")
                if name:
                    names.append(name)
        return names

    def _instantiate_tools_legacy(
        self,
        tools_config: list[Any],
        config: dict[str, Any],
        llm_provider: LLMProviderProtocol,
        user_context: dict[str, Any] | None,
    ) -> list[ToolProtocol]:
        """Legacy tool instantiation path (no resolver)."""
        tools: list[ToolProtocol] = []
        for tool_spec in tools_config:
            resolved_spec = self.hydrate_memory_tool_spec(tool_spec, config)
            tool = self.instantiate_tool(
                resolved_spec, llm_provider, user_context=user_context
            )
            if tool:
                tools.append(tool)
        return tools

    # Default tool names used by ``create_default_tools``.
    _DEFAULT_TOOL_NAMES: list[str] = [
        "web_search",
        "web_fetch",
        "python",
        "github",
        "git",
        "file_read",
        "file_write",
        "shell",
        "ask_user",
    ]

    def create_default_tools(
        self, llm_provider: LLMProviderProtocol
    ) -> list[ToolProtocol]:
        """Create default tool set (fallback when no config provided).

        Delegates to the injected resolver (preferred) or falls back
        to creating an ad-hoc ``ToolRegistry``.

        Args:
            llm_provider: LLM provider (unused when resolver is set).

        Returns:
            List of default tool instances.
        """
        if self._resolver:
            return self._resolver.resolve(self._DEFAULT_TOOL_NAMES)

        from taskforce.application.tool_registry import ToolRegistry

        registry = ToolRegistry(llm_provider=llm_provider)
        return registry.resolve(self._DEFAULT_TOOL_NAMES)

    def get_all_native_tools(
        self, llm_provider: LLMProviderProtocol
    ) -> list[ToolProtocol]:
        """Get all available native tools.

        Delegates to the injected resolver (preferred) or falls back
        to creating an ad-hoc ``ToolRegistry``.

        Args:
            llm_provider: LLM provider for tools that need it.

        Returns:
            List of all native tool instances.
        """
        if self._resolver:
            all_names = self._resolver.get_available_tools()
            return self._resolver.resolve(all_names)

        from taskforce.application.tool_registry import ToolRegistry

        registry = ToolRegistry(llm_provider=llm_provider)
        all_names = registry.get_available_tools()
        return registry.resolve(all_names)

    # Specialist tool name mappings for resolver-based resolution.
    _SPECIALIST_TOOLS: dict[str, list[str]] = {
        "coding": ["file_read", "file_write", "powershell", "ask_user"],
    }

    def create_specialist_tools(
        self,
        specialist: str,
        config: dict[str, Any],
        llm_provider: LLMProviderProtocol,
        user_context: dict[str, Any] | None = None,
    ) -> list[ToolProtocol]:
        """Create tools specific to a specialist profile.

        When a resolver is available, delegates to it for consistent DI.
        Otherwise falls back to direct instantiation.

        Args:
            specialist: Specialist profile (e.g. "coding").
            config: Configuration dictionary.
            llm_provider: LLM provider.
            user_context: Optional user context.

        Returns:
            List of specialist tool instances.

        Raises:
            ValueError: If specialist profile is unknown.
        """
        if specialist not in self._SPECIALIST_TOOLS:
            raise ValueError(f"Unknown specialist profile: {specialist}")

        if self._resolver:
            tool_names = self._SPECIALIST_TOOLS[specialist]
            self._logger.debug(
                "creating_specialist_tools",
                specialist=specialist,
                tools=tool_names,
                via="resolver",
            )
            return self._resolver.resolve(tool_names)

        return self._create_specialist_tools_legacy(
            specialist, user_context
        )

    def _create_specialist_tools_legacy(
        self,
        specialist: str,
        user_context: dict[str, Any] | None,
    ) -> list[ToolProtocol]:
        """Legacy specialist tool creation via direct imports."""
        from taskforce.infrastructure.tools.native.ask_user_tool import (
            AskUserTool,
        )

        if specialist == "coding":
            from taskforce.infrastructure.tools.native.file_tools import (
                FileReadTool,
                FileWriteTool,
            )
            from taskforce.infrastructure.tools.native.shell_tool import (
                PowerShellTool,
            )

            self._logger.debug(
                "creating_specialist_tools",
                specialist="coding",
                tools=["FileReadTool", "FileWriteTool", "PowerShellTool", "AskUserTool"],
            )
            return [FileReadTool(), FileWriteTool(), PowerShellTool(), AskUserTool()]

        # Unknown specialist - should not reach here due to validation in
        # create_specialist_tools, but return empty as a safeguard.
        self._logger.warning(
            "unknown_specialist_legacy",
            specialist=specialist,
        )
        return []

    # -------------------------------------------------------------------------
    # Tool instantiation
    # -------------------------------------------------------------------------

    def instantiate_tool(
        self,
        tool_spec: str | dict[str, Any],
        llm_provider: LLMProviderProtocol,
        user_context: dict[str, Any] | None = None,
        gateway: Any | None = None,
    ) -> ToolProtocol | None:
        """Instantiate a tool from configuration specification.

        .. deprecated::
            Use a ``ToolResolverProtocol`` (e.g. ``ToolRegistry``) instead.
            This method has incomplete DI compared to ToolRegistry and will
            be removed in a future release.

        Args:
            tool_spec: Tool specification dict or short tool name.
            llm_provider: LLM provider for tools that need it.
            user_context: Optional user context.
            gateway: Optional communication gateway for SendNotificationTool.

        Returns:
            Tool instance or None if instantiation fails.
        """
        warnings.warn(
            "ToolBuilder.instantiate_tool() is deprecated. "
            "Use a ToolResolverProtocol (e.g. ToolRegistry) instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        from taskforce.infrastructure.tools.registry import resolve_tool_spec

        # Orchestration tool types have been removed from the core framework.
        if isinstance(tool_spec, dict) and tool_spec.get("type") in {
            "sub_agent",
            "agent",
            "parallel_agent",
        }:
            self._logger.warning(
                "orchestration_tool_unavailable",
                tool_type=tool_spec.get("type"),
                hint="Orchestration tools have been removed from the core framework",
            )
            return None

        resolved_spec = resolve_tool_spec(tool_spec)
        if not resolved_spec:
            self._logger.warning(
                "invalid_tool_spec",
                tool_spec=tool_spec,
                hint="Tool spec must include 'type' or be a known tool name",
            )
            return None

        tool_type = resolved_spec.get("type")
        tool_module = resolved_spec.get("module")
        tool_params: dict[str, Any] = resolved_spec.get("params", {}).copy()

        try:
            module = importlib.import_module(tool_module)
            tool_class = getattr(module, tool_type)

            if tool_type == "LLMTool":
                tool_params["llm_service"] = llm_provider

            if tool_type == "SendNotificationTool" and gateway:
                tool_params["gateway"] = gateway

            tool_instance = tool_class(**tool_params)

            self._logger.debug(
                "tool_instantiated",
                tool_type=tool_type,
                tool_name=tool_instance.name,
            )

            return tool_instance

        except Exception as e:
            self._logger.error(
                "tool_instantiation_failed",
                tool_type=tool_type,
                tool_module=tool_module,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    # -------------------------------------------------------------------------
    # MCP tools
    # -------------------------------------------------------------------------

    async def create_mcp_tools(
        self, config: dict[str, Any]
    ) -> tuple[list[ToolProtocol], list[Any]]:
        """Create MCP tools from configuration.

        Args:
            config: Configuration dictionary containing mcp_servers list.

        Returns:
            Tuple of (MCP tool wrappers, client context managers).
        """
        from taskforce.core.domain.agent_definition import MCPServerConfig
        from taskforce.infrastructure.tools.mcp.connection_manager import (
            create_default_connection_manager,
        )

        mcp_servers_config = config.get("mcp_servers", [])

        if not mcp_servers_config:
            self._logger.debug("no_mcp_servers_configured")
            return [], []

        server_configs = [
            MCPServerConfig.from_dict(s) if isinstance(s, dict) else s
            for s in mcp_servers_config
        ]

        manager = create_default_connection_manager()
        return await manager.connect_all(server_configs)

    # -------------------------------------------------------------------------
    # Config helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def hydrate_memory_tool_spec(
        tool_spec: str | dict[str, Any], config: dict[str, Any]
    ) -> str | dict[str, Any]:
        """Hydrate memory tool spec with store directory from config."""
        if tool_spec != "memory":
            return tool_spec

        store_dir = ToolBuilder.resolve_memory_store_dir(config)
        return {"type": "MemoryTool", "params": {"store_dir": store_dir}}

    @staticmethod
    def resolve_memory_store_dir(
        config: dict[str, Any], work_dir_override: str | None = None
    ) -> str:
        """Resolve memory store path from config.

        Returns a path to the memory file (``memory.md``).  The
        ``FileMemoryStore`` accepts both file and directory paths.
        """
        memory_config = config.get("memory", {})
        store_dir = memory_config.get("store_dir")
        if store_dir:
            return str(store_dir)
        persistence_dir = work_dir_override or config.get(
            "persistence", {}
        ).get("work_dir", ".taskforce")
        return str(Path(persistence_dir) / "memory.md")
