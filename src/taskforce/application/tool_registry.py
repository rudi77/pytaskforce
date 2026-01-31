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
import structlog
from typing import TYPE_CHECKING, Any, Optional

from taskforce.core.interfaces.tools import ToolProtocol
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

    This service consolidates:
    - ToolCatalog: Native tool definitions and validation
    - ToolMapper: Name-to-definition mapping for YAML persistence
    - ToolResolver: Name-to-instance resolution with dependency injection

    Example:
        >>> registry = ToolRegistry()
        >>> # List all tools
        >>> tools = registry.list_native_tools()
        >>> # Validate allowlist
        >>> valid, invalid = registry.validate_tools(["python", "invalid_tool"])
        >>> # Resolve to instances
        >>> tool_instances = registry.resolve(["python", "file_read"])
    """

    def __init__(
        self,
        llm_provider: Optional[LLMProviderProtocol] = None,
        user_context: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Initialize the tool registry.

        Args:
            llm_provider: LLM provider for tools that need it (e.g., LLMTool)
            user_context: User context for RAG tools (user_id, org_id, scope)
        """
        self._llm_provider = llm_provider
        self._user_context = user_context
        self._logger = logger.bind(component="ToolRegistry")

        # Initialize native tools (for catalog functionality)
        self._native_tools = [
            WebSearchTool(),
            WebFetchTool(),
            FileReadTool(),
            FileWriteTool(),
            PythonTool(),
            GitTool(),
            GitHubTool(),
            PowerShellTool(),
            AskUserTool(),
        ]

    # -------------------------------------------------------------------------
    # Catalog functionality (from ToolCatalog)
    # -------------------------------------------------------------------------

    def list_native_tools(self) -> list[dict[str, Any]]:
        """
        Get all native tool definitions.

        Returns:
            List of tool definitions with name, description,
            parameters_schema, requires_approval, approval_risk_level,
            and origin fields.
        """
        tools = []
        for tool in self._native_tools:
            tools.append({
                "name": tool.name,
                "description": tool.description,
                "parameters_schema": tool.parameters_schema,
                "requires_approval": tool.requires_approval,
                "approval_risk_level": tool.approval_risk_level.value,
                "supports_parallelism": getattr(tool, "supports_parallelism", False),
                "origin": "native",
            })
        return tools

    def get_native_tool_names(self) -> set[str]:
        """
        Get set of all native tool names.

        Returns:
            Set of native tool names (case-sensitive).
        """
        return {tool.name for tool in self._native_tools}

    def validate_native_tools(
        self, tool_names: list[str]
    ) -> tuple[bool, list[str]]:
        """
        Validate that tool names are in the native catalog.

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

    def resolve_single(self, tool_name: str) -> Optional[ToolProtocol]:
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

    def _instantiate_tool(self, tool_name: str) -> Optional[ToolProtocol]:
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


# Singleton instance
_registry: Optional[ToolRegistry] = None


def get_tool_registry(
    llm_provider: Optional["LLMProviderProtocol"] = None,
    user_context: Optional[dict[str, Any]] = None,
) -> ToolRegistry:
    """
    Get the tool registry instance.

    For simple catalog/mapper operations, use without arguments.
    For resolver operations requiring dependency injection, pass the providers.

    Args:
        llm_provider: Optional LLM provider for tool instantiation
        user_context: Optional user context for RAG tools

    Returns:
        ToolRegistry instance
    """
    global _registry
    if _registry is None or llm_provider is not None or user_context is not None:
        _registry = ToolRegistry(
            llm_provider=llm_provider,
            user_context=user_context,
        )
    return _registry
