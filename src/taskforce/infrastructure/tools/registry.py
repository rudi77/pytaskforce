"""
Tool registry for resolving tool names and types to module specifications.
"""

from __future__ import annotations

import copy
from typing import Any, Optional

ToolSpec = dict[str, Any]

_TOOL_REGISTRY: dict[str, ToolSpec] = {
    # Native tools - Skill activation
    "activate_skill": {
        "type": "ActivateSkillTool",
        "module": "taskforce.infrastructure.tools.native.activate_skill_tool",
        "params": {},
    },
    # Native tools - Web
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
    "browser": {
        "type": "BrowserTool",
        "module": "taskforce.infrastructure.tools.native.browser_tool",
        "params": {},
    },
    # Native tools - Code execution
    "python": {
        "type": "PythonTool",
        "module": "taskforce.infrastructure.tools.native.python_tool",
        "params": {},
    },
    # Native tools - File operations
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
    # Native tools - Git/GitHub
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
    # Native tools - Shell (platform-agnostic and Windows-specific)
    "shell": {
        "type": "ShellTool",
        "module": "taskforce.infrastructure.tools.native.shell_tool",
        "params": {},
    },
    "powershell": {
        "type": "PowerShellTool",
        "module": "taskforce.infrastructure.tools.native.shell_tool",
        "params": {},
    },
    # Native tools - User interaction
    "ask_user": {
        "type": "AskUserTool",
        "module": "taskforce.infrastructure.tools.native.ask_user_tool",
        "params": {},
    },
    # Native tools - LLM generation
    "llm": {
        "type": "LLMTool",
        "module": "taskforce.infrastructure.tools.native.llm_tool",
        "params": {
            "model_alias": "main",
        },
    },
    # RAG tools - Semantic search and document retrieval
    "rag_semantic_search": {
        "type": "SemanticSearchTool",
        "module": "taskforce.infrastructure.tools.rag.semantic_search_tool",
        "params": {},
    },
    "rag_list_documents": {
        "type": "ListDocumentsTool",
        "module": "taskforce.infrastructure.tools.rag.list_documents_tool",
        "params": {},
    },
    "rag_get_document": {
        "type": "GetDocumentTool",
        "module": "taskforce.infrastructure.tools.rag.get_document_tool",
        "params": {},
    },
    "global_document_analysis": {
        "type": "GlobalDocumentAnalysisTool",
        "module": "taskforce.infrastructure.tools.rag.global_document_analysis_tool",
        "params": {},
    },
    # Native tools - Search operations (Claude Code style)
    "grep": {
        "type": "GrepTool",
        "module": "taskforce.infrastructure.tools.native.search_tools",
        "params": {},
    },
    "glob": {
        "type": "GlobTool",
        "module": "taskforce.infrastructure.tools.native.search_tools",
        "params": {},
    },
    # Native tools - File editing (Claude Code style)
    "edit": {
        "type": "EditTool",
        "module": "taskforce.infrastructure.tools.native.edit_tool",
        "params": {},
    },
    # Native tools - Multimedia (Claude Code style)
    "multimedia": {
        "type": "MultimediaTool",
        "module": "taskforce.infrastructure.tools.native.multimedia_tool",
        "params": {},
    },
    # Native tools - Memory
    "memory": {
        "type": "MemoryTool",
        "module": "taskforce.infrastructure.tools.native.memory_tool",
        "params": {},
    },
    # Native tools - Communication
    "send_notification": {
        "type": "SendNotificationTool",
        "module": "taskforce.infrastructure.tools.native.send_notification_tool",
        "params": {},
    },
    # Butler tools - Calendar
    "calendar": {
        "type": "CalendarTool",
        "module": "taskforce.infrastructure.tools.native.calendar_tool",
        "params": {},
    },
    # Butler tools - Scheduling
    "schedule": {
        "type": "ScheduleTool",
        "module": "taskforce.infrastructure.tools.native.schedule_tool",
        "params": {},
    },
    "reminder": {
        "type": "ReminderTool",
        "module": "taskforce.infrastructure.tools.native.reminder_tool",
        "params": {},
    },
    # Butler tools - Rule management
    "rule_manager": {
        "type": "RuleManagerTool",
        "module": "taskforce.infrastructure.tools.native.rule_manager_tool",
        "params": {},
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


def get_all_tool_names() -> list[str]:
    """
    Get all registered tool names.

    Returns:
        List of all tool names in the registry.
    """
    return list(_TOOL_REGISTRY.keys())


def get_all_tool_definitions() -> dict[str, ToolSpec]:
    """
    Get all tool definitions.

    Returns:
        Deep copy of the entire registry.
    """
    return copy.deepcopy(_TOOL_REGISTRY)


def register_tool(
    name: str,
    tool_type: str,
    module: str,
    params: dict[str, Any] | None = None,
) -> None:
    """
    Register a new tool in the registry.

    This is used for dynamically registering plugin tools.

    Args:
        name: Short name for the tool (used in configs)
        tool_type: Class name of the tool
        module: Full module path to the tool class
        params: Default parameters for the tool

    Raises:
        ValueError: If tool name already exists in registry
    """
    if name in _TOOL_REGISTRY:
        raise ValueError(f"Tool '{name}' already registered in registry")

    _TOOL_REGISTRY[name] = {
        "type": tool_type,
        "module": module,
        "params": params or {},
    }


def unregister_tool(name: str) -> bool:
    """
    Remove a tool from the registry.

    Args:
        name: Tool name to remove

    Returns:
        True if tool was removed, False if not found
    """
    if name in _TOOL_REGISTRY:
        del _TOOL_REGISTRY[name]
        return True
    return False


def is_registered(name: str) -> bool:
    """
    Check if a tool name is registered.

    Args:
        name: Tool name to check

    Returns:
        True if tool is registered
    """
    return name in _TOOL_REGISTRY
