"""
Tool Resolver Protocol

Defines the contract for resolving tool names to tool instances.
This protocol decouples tool consumers (e.g. ToolBuilder) from the
concrete ToolRegistry, enabling consistent dependency injection.
"""

from __future__ import annotations

from typing import Protocol

from taskforce.core.interfaces.tools import ToolProtocol


class ToolResolverProtocol(Protocol):
    """Protocol for resolving tool names to instantiated tool objects.

    Implementations handle dependency injection (LLM provider, user context,
    gateway, scheduler, etc.) transparently — callers only need to provide
    tool names.
    """

    def resolve(
        self,
        tool_names: list[str],
        plugin_tools: list[ToolProtocol] | None = None,
    ) -> list[ToolProtocol]:
        """Resolve a list of tool names to tool instances.

        Args:
            tool_names: Registry keys to resolve.
            plugin_tools: Optional pre-loaded plugin tools (have priority).

        Returns:
            List of instantiated tool objects.
        """
        ...

    def resolve_single(self, tool_name: str) -> ToolProtocol | None:
        """Resolve a single tool name to an instance.

        Args:
            tool_name: Registry key to resolve.

        Returns:
            Tool instance or None if resolution fails.
        """
        ...

    def get_available_tools(self) -> list[str]:
        """Get all available tool names.

        Returns:
            List of registered tool names.
        """
        ...
