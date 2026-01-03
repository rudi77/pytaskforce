"""
Tool Mapper Service
===================

Maps tool names to full tool configuration definitions for YAML persistence.

This service bridges the gap between the simplified API format (tool_allowlist)
and the full profile config format (tools with type, module, params).

Story: 8.1 - Custom Agent Registry (CRUD + YAML Persistence)
"""

from typing import Any

from taskforce.infrastructure.tools.registry import (
    get_tool_definition,
    get_tool_name_for_type,
)


class ToolMapper:
    """
    Maps tool names to full tool configuration definitions.

    Provides the mapping between simplified tool names (used in API)
    and full tool configurations (used in profile YAML configs).
    """

    @classmethod
    def map_tools(cls, tool_names: list[str]) -> list[dict[str, Any]]:
        """
        Map tool names to full tool definitions.

        Args:
            tool_names: List of tool names (e.g., ["web_search", "python"])

        Returns:
            List of full tool definitions with type, module, params

        Example:
            >>> ToolMapper.map_tools(["web_search", "python"])
            [
                {
                    "type": "WebSearchTool",
                    "module": "taskforce.infrastructure.tools.native.web_tools",
                    "params": {}
                },
                {
                    "type": "PythonTool",
                    "module": "taskforce.infrastructure.tools.native.python_tool",
                    "params": {}
                }
            ]
        """
        tools = []
        for name in tool_names:
            definition = get_tool_definition(name)
            if definition:
                tools.append(definition)
        return tools

    @classmethod
    def get_tool_name(cls, tool_type: str) -> str | None:
        """
        Get tool name from tool type.

        Args:
            tool_type: Tool class name (e.g., "WebSearchTool")

        Returns:
            Tool name (e.g., "web_search") or None if not found

        Example:
            >>> ToolMapper.get_tool_name("WebSearchTool")
            "web_search"
        """
        return get_tool_name_for_type(tool_type)


# Singleton instance
_mapper = ToolMapper()


def get_tool_mapper() -> ToolMapper:
    """Get the singleton tool mapper instance."""
    return _mapper
