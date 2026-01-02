"""
Tool Mapper Service
===================

Maps tool names to full tool configuration definitions for YAML persistence.

This service bridges the gap between the simplified API format (tool_allowlist)
and the full profile config format (tools with type, module, params).

Story: 8.1 - Custom Agent Registry (CRUD + YAML Persistence)
"""

import copy
from typing import Any


class ToolMapper:
    """
    Maps tool names to full tool configuration definitions.

    Provides the mapping between simplified tool names (used in API)
    and full tool configurations (used in profile YAML configs).
    """

    # Tool name -> full tool definition mapping
    TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
        "web_search": {
            "type": "WebSearchTool",
            "module": "taskforce.infrastructure.tools.native.web_tools",
            "params": {},
        },
        "web_fetch": {
            "type": "WebFetchTool",
            "module": "taskforce.infrastructure.tools.native.web_tools",
            "params": {},
        },
        "python": {
            "type": "PythonTool",
            "module": "taskforce.infrastructure.tools.native.python_tool",
            "params": {},
        },
        "file_read": {
            "type": "FileReadTool",
            "module": "taskforce.infrastructure.tools.native.file_tools",
            "params": {},
        },
        "file_write": {
            "type": "FileWriteTool",
            "module": "taskforce.infrastructure.tools.native.file_tools",
            "params": {},
        },
        "git": {
            "type": "GitTool",
            "module": "taskforce.infrastructure.tools.native.git_tools",
            "params": {},
        },
        "github": {
            "type": "GitHubTool",
            "module": "taskforce.infrastructure.tools.native.git_tools",
            "params": {},
        },
        "powershell": {
            "type": "PowerShellTool",
            "module": "taskforce.infrastructure.tools.native.shell_tool",
            "params": {},
        },
        "ask_user": {
            "type": "AskUserTool",
            "module": "taskforce.infrastructure.tools.native.ask_user_tool",
            "params": {},
        },
        "llm": {
            "type": "LLMTool",
            "module": "taskforce.infrastructure.tools.native.llm_tool",
            "params": {
                "model_alias": "main",
            },
        },
    }

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
            if name in cls.TOOL_DEFINITIONS:
                # Deep copy to prevent shared references
                tools.append(copy.deepcopy(cls.TOOL_DEFINITIONS[name]))
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
        for name, definition in cls.TOOL_DEFINITIONS.items():
            if definition["type"] == tool_type:
                return name
        return None


# Singleton instance
_mapper = ToolMapper()


def get_tool_mapper() -> ToolMapper:
    """Get the singleton tool mapper instance."""
    return _mapper

