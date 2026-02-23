"""Tool Builder - Extracted from AgentFactory.

Handles all tool instantiation, resolution, and filtering logic:
- Native tool creation from config specs
- MCP tool creation via connection manager
- Specialist tool sets (coding, rag)
- Sub-agent and orchestration tool instantiation
- Memory tool hydration
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from taskforce.core.interfaces.llm import LLMProviderProtocol
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
    """

    def __init__(self, agent_factory: AgentFactory) -> None:
        self._factory = agent_factory
        self._logger = logger.bind(component="tool_builder")

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
        elif use_specialist_defaults and specialist in ("coding", "rag"):
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
            available_native_tools = self.get_all_native_tools(llm_provider)
            for tool in available_native_tools:
                if tool.name in tool_allowlist:
                    tools.append(tool)
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
            user_context: Optional user context for RAG tools.

        Returns:
            List of native tool instances.
        """
        tools_config = config.get("tools", [])

        if not tools_config:
            return self.create_default_tools(llm_provider)

        tools: list[ToolProtocol] = []
        for tool_spec in tools_config:
            resolved_spec = self.hydrate_memory_tool_spec(tool_spec, config)
            tool = self.instantiate_tool(
                resolved_spec, llm_provider, user_context=user_context
            )
            if tool:
                tools.append(tool)

        orchestration_tool = self.build_orchestration_tool(config)
        if orchestration_tool:
            tools.append(orchestration_tool)

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

    # Default tool names used by ``create_default_tools``.
    _DEFAULT_TOOL_NAMES: list[str] = [
        "web_search",
        "web_fetch",
        "python",
        "github",
        "git",
        "file_read",
        "file_write",
        "powershell",
        "ask_user",
    ]

    def create_default_tools(
        self, llm_provider: LLMProviderProtocol
    ) -> list[ToolProtocol]:
        """Create default tool set (fallback when no config provided).

        Delegates to ``ToolRegistry.resolve()`` to avoid duplicating
        tool instantiation logic.

        Args:
            llm_provider: LLM provider (unused - kept for API compatibility).

        Returns:
            List of default tool instances.
        """
        from taskforce.application.tool_registry import ToolRegistry

        registry = ToolRegistry(llm_provider=llm_provider)
        return registry.resolve(self._DEFAULT_TOOL_NAMES)

    def get_all_native_tools(
        self, llm_provider: LLMProviderProtocol
    ) -> list[ToolProtocol]:
        """Get all available native tools.

        Delegates to ``ToolRegistry.resolve()`` to avoid duplicating
        tool instantiation logic.

        Args:
            llm_provider: LLM provider (unused but kept for consistency).

        Returns:
            List of all native tool instances.
        """
        from taskforce.application.tool_registry import ToolRegistry

        registry = ToolRegistry(llm_provider=llm_provider)
        all_names = registry.get_available_tools()
        return registry.resolve(all_names)

    def create_specialist_tools(
        self,
        specialist: str,
        config: dict[str, Any],
        llm_provider: LLMProviderProtocol,
        user_context: dict[str, Any] | None = None,
    ) -> list[ToolProtocol]:
        """Create tools specific to a specialist profile.

        Args:
            specialist: Specialist profile ("coding" or "rag").
            config: Configuration dictionary (for RAG tools).
            llm_provider: LLM provider.
            user_context: Optional user context for RAG tools.

        Returns:
            List of specialist tool instances.

        Raises:
            ValueError: If specialist profile is unknown.
        """
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
                tools=[
                    "FileReadTool",
                    "FileWriteTool",
                    "PowerShellTool",
                    "AskUserTool",
                ],
            )

            return [
                FileReadTool(),
                FileWriteTool(),
                PowerShellTool(),
                AskUserTool(),
            ]

        elif specialist == "rag":
            from taskforce.infrastructure.tools.rag.get_document_tool import (
                GetDocumentTool,
            )
            from taskforce.infrastructure.tools.rag.list_documents_tool import (
                ListDocumentsTool,
            )
            from taskforce.infrastructure.tools.rag.semantic_search_tool import (
                SemanticSearchTool,
            )

            self._logger.debug(
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

    # -------------------------------------------------------------------------
    # Tool instantiation
    # -------------------------------------------------------------------------

    def instantiate_tool(
        self,
        tool_spec: str | dict[str, Any],
        llm_provider: LLMProviderProtocol,
        user_context: dict[str, Any] | None = None,
    ) -> ToolProtocol | None:
        """Instantiate a tool from configuration specification.

        Args:
            tool_spec: Tool specification dict or short tool name.
            llm_provider: LLM provider for tools that need it.
            user_context: Optional user context for RAG tools.

        Returns:
            Tool instance or None if instantiation fails.
        """
        from taskforce.infrastructure.tools.registry import resolve_tool_spec

        if isinstance(tool_spec, dict) and tool_spec.get("type") in {
            "sub_agent",
            "agent",
        }:
            return self.instantiate_sub_agent_tool(tool_spec)

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

            if tool_type in [
                "SemanticSearchTool",
                "ListDocumentsTool",
                "GetDocumentTool",
            ]:
                if user_context:
                    tool_params["user_context"] = user_context

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

    def instantiate_sub_agent_tool(
        self,
        tool_spec: dict[str, Any],
    ) -> ToolProtocol | None:
        """Instantiate a sub-agent tool from configuration."""
        from taskforce.application.sub_agent_spawner import SubAgentSpawner
        from taskforce.infrastructure.tools.orchestration import AgentTool
        from taskforce.infrastructure.tools.orchestration.sub_agent_tool import (
            SubAgentTool,
        )

        tool_name = tool_spec.get("name")
        specialist = tool_spec.get("specialist") or tool_name
        if not tool_name:
            self._logger.warning(
                "invalid_sub_agent_tool_spec",
                tool_spec=tool_spec,
                hint="Sub-agent tool spec requires 'name'",
            )
            return None

        profile = tool_spec.get("profile", "dev")
        work_dir = tool_spec.get("work_dir")
        max_steps = tool_spec.get("max_steps")
        planning_strategy = tool_spec.get("planning_strategy")

        sub_agent_spawner = SubAgentSpawner(
            agent_factory=self._factory,
            profile=profile,
            work_dir=work_dir,
            max_steps=max_steps,
        )
        agent_tool = AgentTool(
            agent_factory=self._factory,
            sub_agent_spawner=sub_agent_spawner,
            profile=profile,
            work_dir=work_dir,
            max_steps=max_steps,
        )

        return SubAgentTool(
            agent_tool=agent_tool,
            specialist=specialist,
            name=tool_name,
            description=tool_spec.get("description"),
            planning_strategy=planning_strategy,
        )

    # -------------------------------------------------------------------------
    # Orchestration & MCP
    # -------------------------------------------------------------------------

    def build_orchestration_tool(
        self, config: dict[str, Any]
    ) -> ToolProtocol | None:
        """Build AgentTool when orchestration is enabled."""
        orchestration_config = config.get("orchestration", {})
        if not orchestration_config.get("enabled", False):
            return None

        from taskforce.application.sub_agent_spawner import SubAgentSpawner
        from taskforce.infrastructure.tools.orchestration import AgentTool

        sub_agent_spawner = SubAgentSpawner(
            agent_factory=self._factory,
            profile=orchestration_config.get("sub_agent_profile", "dev"),
            work_dir=orchestration_config.get("sub_agent_work_dir"),
            max_steps=orchestration_config.get("sub_agent_max_steps"),
        )
        agent_tool = AgentTool(
            agent_factory=self._factory,
            sub_agent_spawner=sub_agent_spawner,
            profile=orchestration_config.get("sub_agent_profile", "dev"),
            work_dir=orchestration_config.get("sub_agent_work_dir"),
            max_steps=orchestration_config.get("sub_agent_max_steps"),
            summarize_results=orchestration_config.get(
                "summarize_results", False
            ),
            summary_max_length=orchestration_config.get(
                "summary_max_length", 2000
            ),
        )

        self._logger.info(
            "orchestration_enabled",
            agent_tool_added=True,
            sub_agent_profile=orchestration_config.get(
                "sub_agent_profile", "dev"
            ),
            sub_agent_max_steps=orchestration_config.get(
                "sub_agent_max_steps"
            ),
        )
        return agent_tool

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

        memory_config = config.get("memory", {})
        store_dir = memory_config.get("store_dir")
        if not store_dir:
            persistence_dir = config.get("persistence", {}).get(
                "work_dir", ".taskforce"
            )
            store_dir = str(Path(persistence_dir) / "memory")
        return {"type": "MemoryTool", "params": {"store_dir": store_dir}}

    @staticmethod
    def resolve_memory_store_dir(
        config: dict[str, Any], work_dir_override: str | None = None
    ) -> str:
        """Resolve memory store directory from config."""
        memory_config = config.get("memory", {})
        store_dir = memory_config.get("store_dir")
        if store_dir:
            return str(store_dir)
        persistence_dir = work_dir_override or config.get(
            "persistence", {}
        ).get("work_dir", ".taskforce")
        return str(Path(persistence_dir) / "memory")
