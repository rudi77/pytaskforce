"""
Tool Resolver Service (Compatibility Wrapper)
=============================================

This module provides backward compatibility for code using ToolResolver.
All functionality has been consolidated into ToolRegistry.

Deprecated: Use ToolRegistry instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from taskforce.core.interfaces.tools import ToolProtocol
from taskforce.application.tool_registry import ToolRegistry

if TYPE_CHECKING:
    from taskforce.core.interfaces.llm import LLMProviderProtocol


class ToolResolver:
    """
    Resolves tool names to tool instances.

    Deprecated: Use ToolRegistry instead. This class delegates to ToolRegistry.
    """

    def __init__(
        self,
        llm_provider: Optional[LLMProviderProtocol] = None,
        user_context: Optional[dict[str, Any]] = None,
    ) -> None:
        """Initialize the tool resolver (delegates to ToolRegistry)."""
        self._registry = ToolRegistry(
            llm_provider=llm_provider,
            user_context=user_context,
        )

    def resolve(
        self,
        tool_names: list[str],
        plugin_tools: list[ToolProtocol] | None = None,
    ) -> list[ToolProtocol]:
        """Resolve tool names to tool instances."""
        return self._registry.resolve(tool_names, plugin_tools)

    def resolve_single(self, tool_name: str) -> Optional[ToolProtocol]:
        """Resolve a single tool name to an instance."""
        return self._registry.resolve_single(tool_name)

    def get_available_tools(self) -> list[str]:
        """Get list of all available tool names in the registry."""
        return self._registry.get_available_tools()

    def is_valid_tool(self, tool_name: str) -> bool:
        """Check if a tool name is valid."""
        return self._registry.is_valid_tool(tool_name)

    def validate_tools(self, tool_names: list[str]) -> tuple[list[str], list[str]]:
        """Validate a list of tool names."""
        return self._registry.validate_tools(tool_names)
