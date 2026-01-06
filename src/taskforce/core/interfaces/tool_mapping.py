"""
Tool Mapping Protocol

Defines the interface for tool name-to-definition mapping.
This allows infrastructure to use tool mapping without importing from application layer.
"""

from typing import Any, Protocol


class ToolMapperProtocol(Protocol):
    """
    Protocol for mapping tool names to full tool definitions.

    This abstraction allows infrastructure components to request tool
    mapping without directly importing from the application layer,
    maintaining proper layer boundaries.
    """

    def map_tools(self, tool_names: list[str]) -> list[dict[str, Any]]:
        """
        Map tool names to full tool definitions.

        Args:
            tool_names: List of tool names (e.g., ["web_search", "python"])

        Returns:
            List of full tool definitions with type, module, params
        """
        ...

    def get_tool_name(self, tool_type: str) -> str | None:
        """
        Get tool name from tool type class name.

        Args:
            tool_type: Tool class name (e.g., "WebSearchTool")

        Returns:
            Tool name (e.g., "web_search") or None if not found
        """
        ...
