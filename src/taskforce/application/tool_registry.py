"""
Unified Tool Registry Service
==============================

Consolidates tool discovery, mapping, validation, and resolution into a
single service. Replaces the separate ToolCatalog, ToolMapper, and ToolResolver.

Responsibilities:
- List available tools (native and plugin)
- Map tool names to definitions
- Validate tool allowlists
- Resolve tool names to instances

Part of code simplification: Unified Tool Registry.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

import structlog

from taskforce.core.interfaces.tools import ToolProtocol
from taskforce.infrastructure.tools.registry import (
    get_all_tool_names,
    get_tool_definition,
    get_tool_name_for_type,
    resolve_tool_spec,
)

if TYPE_CHECKING:
    from taskforce.core.interfaces.llm import LLMProviderProtocol


logger = structlog.get_logger(__name__)


class ToolRegistry:
    """
    Unified registry for tool discovery, mapping, validation, and resolution.

    Delegates to the infrastructure-level tool registry
    (``infrastructure.tools.registry``) as single source of truth for tool
    definitions, while providing dependency injection for tools that need
    runtime context (LLM provider, user context, memory store).

    Example:
        >>> registry = ToolRegistry()
        >>> # List all registered tools
        >>> tools = registry.list_native_tools()
        >>> # Validate allowlist
        >>> valid, invalid = registry.validate_tools(["python", "invalid_tool"])
        >>> # Resolve to instances
        >>> tool_instances = registry.resolve(["python", "file_read"])
    """

    def __init__(
        self,
        llm_provider: LLMProviderProtocol | None = None,
        user_context: dict[str, Any] | None = None,
        memory_store_dir: str | None = None,
        gateway: Any | None = None,
    ) -> None:
        """
        Initialize the tool registry.

        Args:
            llm_provider: LLM provider for tools that need it (e.g., LLMTool)
            user_context: User context for RAG tools (user_id, org_id, scope)
            memory_store_dir: Directory for file-based memory storage
            gateway: Communication gateway for SendNotificationTool
        """
        self._llm_provider = llm_provider
        self._user_context = user_context
        self._memory_store_dir = memory_store_dir
        self._gateway = gateway
        self._logger = logger.bind(component="ToolRegistry")

    # -------------------------------------------------------------------------
    # Catalog functionality
    # -------------------------------------------------------------------------

    def list_native_tools(self) -> list[dict[str, Any]]:
        """
        Get all registered tool definitions.

        Instantiates each tool from the infrastructure registry and returns
        its metadata. This ensures the list is always in sync with the
        single source of truth.

        Returns:
            List of tool definitions with name, description,
            parameters_schema, requires_approval, approval_risk_level,
            and origin fields.
        """
        tools = []
        for tool_name in get_all_tool_names():
            tool = self._instantiate_tool(tool_name)
            if tool is None:
                continue
            risk_level = getattr(tool, "approval_risk_level", None)
            tools.append({
                "name": tool.name,
                "description": tool.description,
                "parameters_schema": tool.parameters_schema,
                "requires_approval": getattr(tool, "requires_approval", False),
                "approval_risk_level": risk_level.value if risk_level else "low",
                "supports_parallelism": getattr(tool, "supports_parallelism", False),
                "origin": "native",
            })
        return tools

    def get_native_tool_names(self) -> set[str]:
        """
        Get set of all registered tool names.

        Returns:
            Set of tool names (case-sensitive).
        """
        return set(get_all_tool_names())

    def validate_native_tools(
        self, tool_names: list[str]
    ) -> tuple[bool, list[str]]:
        """
        Validate that tool names exist in the registry.

        Args:
            tool_names: List of tool names to validate

        Returns:
            Tuple of (is_valid, invalid_tool_names)
        """
        available_tools = self.get_native_tool_names()
        invalid_tools = [
            name for name in tool_names if name not in available_tools
        ]
        return len(invalid_tools) == 0, invalid_tools

    # -------------------------------------------------------------------------
    # Mapper functionality (from ToolMapper)
    # -------------------------------------------------------------------------

    def map_tools(self, tool_names: list[str]) -> list[dict[str, Any]]:
        """
        Map tool names to full tool definitions.

        Args:
            tool_names: List of tool names (e.g., ["web_search", "python"])

        Returns:
            List of full tool definitions with type, module, params

        Example:
            >>> registry.map_tools(["web_search", "python"])
            [
                {
                    "type": "WebSearchTool",
                    "module": "taskforce.infrastructure.tools.native.web_tools",
                    "params": {}
                },
                ...
            ]
        """
        tools = []
        for name in tool_names:
            definition = get_tool_definition(name)
            if definition:
                tools.append(definition)
        return tools

    def get_tool_name(self, tool_type: str) -> str | None:
        """
        Get tool name from tool type class name.

        Args:
            tool_type: Tool class name (e.g., "WebSearchTool")

        Returns:
            Tool name (e.g., "web_search") or None if not found
        """
        return get_tool_name_for_type(tool_type)

    # -------------------------------------------------------------------------
    # Resolver functionality (from ToolResolver)
    # -------------------------------------------------------------------------

    def resolve(
        self,
        tool_names: list[str],
        plugin_tools: list[ToolProtocol] | None = None,
    ) -> list[ToolProtocol]:
        """
        Resolve tool names to tool instances.

        Args:
            tool_names: List of tool names (registry keys) to resolve
            plugin_tools: Optional list of pre-loaded plugin tools to include

        Returns:
            List of instantiated tool objects
        """
        tools: list[ToolProtocol] = []

        # Add plugin tools first (they have priority)
        if plugin_tools:
            tools.extend(plugin_tools)
            plugin_names = {t.name for t in plugin_tools}
            self._logger.debug(
                "plugin_tools_added",
                count=len(plugin_tools),
                names=list(plugin_names),
            )
        else:
            plugin_names = set()

        # Resolve registry tools
        for tool_name in tool_names:
            # Skip if plugin already provides this tool
            if tool_name in plugin_names:
                self._logger.debug(
                    "tool_skipped_plugin_override",
                    tool_name=tool_name,
                )
                continue

            tool = self._instantiate_tool(tool_name)
            if tool:
                tools.append(tool)

        self._logger.info(
            "tools_resolved",
            requested=len(tool_names),
            resolved=len(tools),
            tool_names=[t.name for t in tools],
        )

        return tools

    def resolve_single(self, tool_name: str) -> ToolProtocol | None:
        """
        Resolve a single tool name to an instance.

        Args:
            tool_name: Tool name (registry key) to resolve

        Returns:
            Tool instance or None if resolution fails
        """
        return self._instantiate_tool(tool_name)

    def get_available_tools(self) -> list[str]:
        """
        Get list of all available tool names in the registry.

        Returns:
            List of registered tool names
        """
        return get_all_tool_names()

    def is_valid_tool(self, tool_name: str) -> bool:
        """
        Check if a tool name is valid (exists in registry).

        Args:
            tool_name: Tool name to check

        Returns:
            True if tool exists in registry
        """
        return get_tool_definition(tool_name) is not None

    def validate_tools(self, tool_names: list[str]) -> tuple[list[str], list[str]]:
        """
        Validate a list of tool names.

        Args:
            tool_names: List of tool names to validate

        Returns:
            Tuple of (valid_tools, invalid_tools)
        """
        valid = []
        invalid = []

        for name in tool_names:
            if self.is_valid_tool(name):
                valid.append(name)
            else:
                invalid.append(name)

        return valid, invalid

    def _instantiate_tool(self, tool_name: str) -> ToolProtocol | None:
        """
        Instantiate a tool from its registry name.

        Args:
            tool_name: Registry name of the tool

        Returns:
            Tool instance or None if instantiation fails
        """
        resolved_spec = resolve_tool_spec(tool_name)
        if not resolved_spec:
            self._logger.warning(
                "tool_not_found",
                tool_name=tool_name,
                hint="Tool name must be a registered tool in the registry",
            )
            return None

        tool_type = resolved_spec.get("type")
        tool_module = resolved_spec.get("module")
        tool_params = resolved_spec.get("params", {}).copy()

        # Type guards
        if not isinstance(tool_type, str) or not isinstance(tool_module, str):
            self._logger.warning(
                "tool_spec_invalid",
                tool_name=tool_name,
                tool_type=tool_type,
                tool_module=tool_module,
            )
            return None

        try:
            # Import the module
            module = importlib.import_module(tool_module)

            # Get the tool class
            tool_class = getattr(module, tool_type)

            # Special handling for LLMTool - inject llm_service
            if tool_type == "LLMTool" and self._llm_provider:
                tool_params["llm_service"] = self._llm_provider

            # Special handling for RAG tools - inject user_context
            if tool_type in [
                "SemanticSearchTool",
                "ListDocumentsTool",
                "GetDocumentTool",
            ]:
                if self._user_context:
                    tool_params["user_context"] = self._user_context

            # Special handling for MemoryTool - inject store_dir
            if tool_type == "MemoryTool" and self._memory_store_dir:
                tool_params.setdefault("store_dir", self._memory_store_dir)

            # Special handling for SendNotificationTool - inject gateway
            if tool_type == "SendNotificationTool" and self._gateway:
                tool_params["gateway"] = self._gateway

            # Instantiate the tool
            tool_instance: ToolProtocol = tool_class(**tool_params)

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


# Lightweight catalog-only instance (no LLM/user context required).
# Lazily created on first call to ``get_tool_registry()`` *without*
# parameters and reused for catalog/mapper lookups.
_catalog_registry: ToolRegistry | None = None


def get_tool_registry(
    llm_provider: LLMProviderProtocol | None = None,
    user_context: dict[str, Any] | None = None,
    memory_store_dir: str | None = None,
    gateway: Any | None = None,
) -> ToolRegistry:
    """Get a tool registry instance.

    **Without arguments** — returns a shared, lightweight registry suitable
    for catalog/mapper operations (listing tools, validating names, etc.).

    **With arguments** — returns a *new* registry wired with the provided
    dependencies. This avoids the previous issue where passing parameters
    mutated shared global state and leaked context across requests.

    Args:
        llm_provider: Optional LLM provider for tool instantiation.
        user_context: Optional user context for RAG tools.
        memory_store_dir: Optional memory store directory.
        gateway: Optional communication gateway for SendNotificationTool.

    Returns:
        ToolRegistry instance.
    """
    has_params = (
        llm_provider is not None
        or user_context is not None
        or memory_store_dir is not None
        or gateway is not None
    )
    if has_params:
        # Always return a fresh, request-scoped instance when DI params given.
        return ToolRegistry(
            llm_provider=llm_provider,
            user_context=user_context,
            memory_store_dir=memory_store_dir,
            gateway=gateway,
        )

    # Catalog-only path: reuse a shared lightweight instance.
    global _catalog_registry
    if _catalog_registry is None:
        _catalog_registry = ToolRegistry()
    return _catalog_registry


def reset_tool_registry() -> None:
    """Reset the cached catalog registry (useful in tests)."""
    global _catalog_registry
    _catalog_registry = None
