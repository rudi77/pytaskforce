"""
Tool Resolver Service

Resolves tool names to tool instances. This is the central service for
converting tool configuration (string names) into executable tool objects.

Part of Phase 1 refactoring: Unified Tool Configuration.
"""

from __future__ import annotations

import importlib
import structlog
from typing import TYPE_CHECKING, Any, Optional

from taskforce.core.interfaces.tools import ToolProtocol

if TYPE_CHECKING:
    from taskforce.core.interfaces.llm import LLMProviderProtocol


logger = structlog.get_logger(__name__)


class ToolResolver:
    """
    Resolves tool names to tool instances.

    This service handles:
    - Looking up tool definitions in the registry
    - Instantiating tools with correct parameters
    - Injecting dependencies (LLM provider, user context)
    - Supporting plugin tools that aren't in the standard registry
    """

    def __init__(
        self,
        llm_provider: Optional[LLMProviderProtocol] = None,
        user_context: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Initialize the tool resolver.

        Args:
            llm_provider: LLM provider for tools that need it (e.g., LLMTool)
            user_context: User context for RAG tools (user_id, org_id, scope)
        """
        self._llm_provider = llm_provider
        self._user_context = user_context
        self._logger = logger.bind(component="ToolResolver")

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
        from taskforce.infrastructure.tools.registry import get_all_tool_names

        return get_all_tool_names()

    def is_valid_tool(self, tool_name: str) -> bool:
        """
        Check if a tool name is valid (exists in registry).

        Args:
            tool_name: Tool name to check

        Returns:
            True if tool exists in registry
        """
        from taskforce.infrastructure.tools.registry import get_tool_definition

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
        from taskforce.infrastructure.tools.registry import resolve_tool_spec

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

        # Type guards for mypy
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

            # Instantiate the tool with params
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
