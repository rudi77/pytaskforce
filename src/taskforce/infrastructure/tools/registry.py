"""
Tool registry for resolving tool names and types to module specifications.
"""

from __future__ import annotations

import copy
from typing import Any, Optional

ToolSpec = dict[str, Any]

_TOOL_REGISTRY: dict[str, ToolSpec] = {
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


def get_tool_definition(tool_name: str) -> Optional[ToolSpec]:
    """Return a deep-copied tool definition by short name."""
    definition = _TOOL_REGISTRY.get(tool_name)
    if not definition:
        return None
    return copy.deepcopy(definition)


def get_tool_name_for_type(tool_type: str) -> Optional[str]:
    """Return the short tool name for a given tool class name."""
    for name, definition in _TOOL_REGISTRY.items():
        if definition["type"] == tool_type:
            return name
    return None


def get_tool_definition_by_type(tool_type: str) -> Optional[ToolSpec]:
    """Return a deep-copied tool definition by tool class name."""
    tool_name = get_tool_name_for_type(tool_type)
    if not tool_name:
        return None
    return get_tool_definition(tool_name)


def resolve_tool_spec(tool_spec: str | ToolSpec) -> Optional[ToolSpec]:
    """
    Resolve a tool spec into a full definition with type, module, and params.

    Args:
        tool_spec: Either a short tool name (string) or a tool spec dict.

    Returns:
        Full tool spec dict or None if unresolved.
    """
    if isinstance(tool_spec, str):
        return get_tool_definition(tool_spec)

    tool_type = tool_spec.get("type")
    tool_module = tool_spec.get("module")
    tool_params = tool_spec.get("params", {})

    resolved = _resolve_partial_spec(tool_type, tool_module, tool_params)
    if resolved is None:
        return None
    return resolved


def _resolve_partial_spec(
    tool_type: str | None,
    tool_module: str | None,
    tool_params: dict[str, Any],
) -> Optional[ToolSpec]:
    """Resolve a partial spec using registry defaults."""
    if not tool_type:
        return None

    defaults = get_tool_definition_by_type(tool_type)
    merged_params = _merge_params(defaults, tool_params)
    resolved_module = tool_module or (defaults["module"] if defaults else None)
    if not resolved_module:
        return None

    return {
        "type": tool_type,
        "module": resolved_module,
        "params": merged_params,
    }


def _merge_params(
    defaults: Optional[ToolSpec],
    overrides: dict[str, Any],
) -> dict[str, Any]:
    """Merge default params with overrides, preferring overrides."""
    merged = {}
    if defaults:
        merged.update(defaults.get("params", {}))
    merged.update(overrides)
    return merged
