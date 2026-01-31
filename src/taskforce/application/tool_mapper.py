"""
Tool Mapper Service (Compatibility Wrapper)
===========================================

This module provides backward compatibility for code using ToolMapper.
All functionality has been consolidated into ToolRegistry.

Deprecated: Use ToolRegistry instead.
"""

from typing import Any

from taskforce.application.tool_registry import ToolRegistry


class ToolMapper:
    """
    Maps tool names to full tool configuration definitions.

    Deprecated: Use ToolRegistry instead. This class delegates to ToolRegistry.
    """

    def __init__(self) -> None:
        """Initialize the tool mapper (delegates to ToolRegistry)."""
        self._registry = ToolRegistry()

    @classmethod
    def map_tools(cls, tool_names: list[str]) -> list[dict[str, Any]]:
        """Map tool names to full tool definitions."""
        return ToolRegistry().map_tools(tool_names)

    @classmethod
    def get_tool_name(cls, tool_type: str) -> str | None:
        """Get tool name from tool type."""
        return ToolRegistry().get_tool_name(tool_type)


# Singleton instance
_mapper = ToolMapper()


def get_tool_mapper() -> ToolMapper:
    """Get the singleton tool mapper instance."""
    return _mapper
