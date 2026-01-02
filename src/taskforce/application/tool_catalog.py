"""
Tool Catalog Service
====================

Provides the service tool catalog for allowlist validation and API exposure.

Story: 8.2 - Tool Catalog + Allowlist Validation
"""

from typing import Any, Dict, List

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


class ToolCatalog:
    """
    Service tool catalog providing native tool definitions.

    This is the single source of truth for tool allowlist validation.
    """

    def __init__(self):
        """Initialize the tool catalog with all native tools."""
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

    def get_native_tools(self) -> List[Dict[str, Any]]:
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
                "origin": "native",
            })
        return tools

    def get_native_tool_names(self) -> set[str]:
        """
        Get set of all native tool names for validation.

        Returns:
            Set of native tool names (case-sensitive).
        """
        return {tool.name for tool in self._native_tools}

    def validate_native_tools(
        self, tool_names: List[str]
    ) -> tuple[bool, List[str]]:
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


# Singleton instance
_catalog = ToolCatalog()


def get_tool_catalog() -> ToolCatalog:
    """Get the singleton tool catalog instance."""
    return _catalog
