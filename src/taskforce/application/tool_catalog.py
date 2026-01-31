"""
Tool Catalog Service (Compatibility Wrapper)
=============================================

This module provides backward compatibility for code using ToolCatalog.
All functionality has been consolidated into ToolRegistry.

Deprecated: Use ToolRegistry instead.
"""

from typing import Any, Dict, List

from taskforce.application.tool_registry import ToolRegistry, get_tool_registry


class ToolCatalog:
    """
    Service tool catalog providing native tool definitions.

    Deprecated: Use ToolRegistry instead. This class delegates to ToolRegistry.
    """

    def __init__(self) -> None:
        """Initialize the tool catalog (delegates to ToolRegistry)."""
        self._registry = ToolRegistry()

    def get_native_tools(self) -> List[Dict[str, Any]]:
        """Get all native tool definitions."""
        return self._registry.list_native_tools()

    def get_native_tool_names(self) -> set[str]:
        """Get set of all native tool names for validation."""
        return self._registry.get_native_tool_names()

    def validate_native_tools(
        self, tool_names: List[str]
    ) -> tuple[bool, List[str]]:
        """Validate that tool names are in the native catalog."""
        return self._registry.validate_native_tools(tool_names)


# Singleton instance
_catalog = ToolCatalog()


def get_tool_catalog() -> ToolCatalog:
    """Get the singleton tool catalog instance."""
    return _catalog
