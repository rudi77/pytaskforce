"""
Tool registry for resolving tool names and types to module specifications.

The framework ships a hardcoded baseline registry (``_BUILTIN_REGISTRY``)
for native tools and — during the Phase-1 transition — legacy agent-package
tools. Entry-point contributions from installed agent packages (via the
``taskforce.tools`` group, see
:mod:`taskforce.application.agent_plugin_registry`) are merged on top, so
external plugins can add tools without editing this file.

Resolution order:
1. Entry-point descriptors (``taskforce.tools`` group) — wins on overlap.
2. Built-in baseline (``_BUILTIN_REGISTRY``) — fallback, contains native
   tools + legacy hardcoded agent-package entries (removed in Phase 4).

The merge result is cached in ``_resolved_registry()`` so the entry-point
scan runs once per process. Tests that need a fresh scan can call
``_resolved_registry.cache_clear()``.

Performance notes:
- ``get_tool_definition`` returns a *shallow* copy (type/module are strings,
  params is shallow-copied).  Callers that mutate nested params should copy
  them explicitly — but all current callers already do ``params.copy()``.
- ``get_tool_name_for_type`` uses a pre-built reverse index instead of a
  linear scan, making it O(1) instead of O(n).
"""

from __future__ import annotations

import functools
from typing import Any

import structlog

ToolSpec = dict[str, Any]

logger = structlog.get_logger(__name__)

_BUILTIN_REGISTRY: dict[str, ToolSpec] = {
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
    # Native tools - Shell (platform-agnostic, bash-explicit, and Windows-specific)
    "shell": {
        "type": "ShellTool",
        "module": "taskforce.infrastructure.tools.native.shell_tool",
        "params": {},
    },
    "bash": {
        "type": "BashTool",
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
    # Native tools - Result Retrieval
    "fetch_result": {
        "type": "FetchResultTool",
        "module": "taskforce.infrastructure.tools.native.fetch_result_tool",
        "params": {},
    },
    # Native tools - Wiki (long-term memory)
    "wiki": {
        "type": "WikiTool",
        "module": "taskforce.infrastructure.tools.native.wiki_tool",
        "params": {},
    },
    # Native tools - Browser automation
    "browser": {
        "type": "BrowserTool",
        "module": "taskforce.infrastructure.tools.native.browser_tool",
        "params": {},
    },
    # Native tools - Multimedia
    "multimedia": {
        "type": "MultimediaTool",
        "module": "taskforce.infrastructure.tools.native.multimedia_tool",
        "params": {},
    },
    # Native tools - Office documents
    "docx": {
        "type": "DocxTool",
        "module": "taskforce.infrastructure.tools.native.docx_tool",
        "params": {},
    },
    "pptx": {
        "type": "PptxTool",
        "module": "taskforce.infrastructure.tools.native.pptx_tool",
        "params": {},
    },
    "excel": {
        "type": "ExcelTool",
        "module": "taskforce.infrastructure.tools.native.excel_tool",
        "params": {},
    },
    # Native tools - Accounting
    "accounting_validate": {
        "type": "AccountingValidateTool",
        "module": "taskforce.infrastructure.tools.native.accounting_validate_tool",
        "params": {},
    },
    "accounting_audit": {
        "type": "AccountingAuditTool",
        "module": "taskforce.infrastructure.tools.native.accounting_audit_tool",
        "params": {},
    },
    # Orchestration tools - Sub-agent execution
    "call_agents_parallel": {
        "type": "ParallelAgentTool",
        "module": "taskforce.infrastructure.tools.orchestration.parallel_agent_tool",
        "params": {},
    },
    "call_acp_agent": {
        "type": "AcpAgentTool",
        "module": "taskforce.infrastructure.tools.orchestration.acp_agent_tool",
        "params": {},
    },
    # RAG tools - Semantic search and document retrieval
    "rag_semantic_search": {
        "type": "SemanticSearchTool",
        "module": "taskforce_rag_agent.tools.semantic_search_tool",
        "params": {},
    },
    "rag_list_documents": {
        "type": "ListDocumentsTool",
        "module": "taskforce_rag_agent.tools.list_documents_tool",
        "params": {},
    },
    "rag_get_document": {
        "type": "GetDocumentTool",
        "module": "taskforce_rag_agent.tools.get_document_tool",
        "params": {},
    },
    "global_document_analysis": {
        "type": "GlobalDocumentAnalysisTool",
        "module": "taskforce_rag_agent.tools.global_document_analysis_tool",
        "params": {},
    },
    # Proactive push notifications (available to any agent; gateway is
    # injected at build time — see AgentFactory.set_gateway)
    "send_notification": {
        "type": "SendNotificationTool",
        "module": "taskforce.infrastructure.tools.native.send_notification_tool",
        "params": {},
    },
    # Butler agent tools

    "gmail": {
        "type": "GmailTool",
        "module": "taskforce_butler.infrastructure.tools.email_tool",
        "params": {},
    },
    "google_drive": {
        "type": "GoogleDriveTool",
        "module": "taskforce_butler.infrastructure.tools.google_drive_tool",
        "params": {},
    },
    "calendar": {
        "type": "CalendarTool",
        "module": "taskforce_butler.infrastructure.tools.calendar_tool",
        "params": {},
    },
    "schedule": {
        "type": "ScheduleTool",
        "module": "taskforce.infrastructure.tools.native.schedule_tool",
        "params": {},
    },
    "reminder": {
        "type": "ReminderTool",
        "module": "taskforce_butler.infrastructure.tools.reminder_tool",
        "params": {},
    },
    "rule_manager": {
        "type": "RuleManagerTool",
        "module": "taskforce_butler.infrastructure.tools.rule_manager_tool",
        "params": {},
    },
    "authenticate": {
        "type": "AuthTool",
        "module": "taskforce_butler.infrastructure.tools.auth_tool",
        "params": {},
    },
}

@functools.lru_cache(maxsize=1)
def _resolved_registry() -> dict[str, ToolSpec]:
    """Return ``_BUILTIN_REGISTRY`` merged with entry-point contributions.

    Entry-point tools override built-in entries on name collision so a
    plugin can re-home a tool (e.g. moving ``gmail`` from
    ``taskforce_butler`` to ``taskforce_google_workspace``) without
    requiring a framework release.
    """
    merged: dict[str, ToolSpec] = dict(_BUILTIN_REGISTRY)
    try:
        from taskforce.application.agent_plugin_registry import (
            load_tool_descriptors,
        )

        entry_point_tools = load_tool_descriptors()
    except Exception as exc:  # noqa: BLE001 — startup must never crash
        logger.warning(
            "tool_registry.entry_point_discovery_failed",
            error=str(exc),
        )
        entry_point_tools = {}
    overrides = [name for name in entry_point_tools if name in merged]
    if overrides:
        logger.debug(
            "tool_registry.entry_point_overrides",
            count=len(overrides),
            names=overrides,
        )
    merged.update(entry_point_tools)
    return merged


@functools.lru_cache(maxsize=1)
def _resolved_type_index() -> dict[str, str]:
    """Pre-built reverse index for the resolved (merged) registry."""
    return {spec["type"]: name for name, spec in _resolved_registry().items()}


def get_tool_definition(tool_name: str) -> ToolSpec | None:
    """Return a shallow-copied tool definition by short name.

    The returned dict has its own ``params`` dict so callers can safely
    mutate params without affecting the registry.  ``type`` and ``module``
    are immutable strings and are shared.
    """
    definition = _resolved_registry().get(tool_name)
    if not definition:
        return None
    # Shallow copy: type/module are strings (immutable), params is a new dict.
    return {
        "type": definition["type"],
        "module": definition["module"],
        "params": dict(definition.get("params", {})),
    }


def get_tool_name_for_type(tool_type: str) -> str | None:
    """Return the short tool name for a given tool class name (O(1))."""
    return _resolved_type_index().get(tool_type)


def get_tool_definition_by_type(tool_type: str) -> ToolSpec | None:
    """Return a shallow-copied tool definition by tool class name."""
    tool_name = _resolved_type_index().get(tool_type)
    if not tool_name:
        return None
    return get_tool_definition(tool_name)


def resolve_tool_spec(tool_spec: str | ToolSpec) -> ToolSpec | None:
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
) -> ToolSpec | None:
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
    defaults: ToolSpec | None,
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
    Get all registered tool names (built-in + entry-point contributions).

    Returns:
        List of all tool names in the resolved registry.
    """
    return list(_resolved_registry().keys())


def get_all_tool_definitions() -> dict[str, ToolSpec]:
    """
    Get all tool definitions (shallow copies, includes entry-point tools).

    Returns:
        Dict of tool names to shallow-copied specs.
    """
    return {name: get_tool_definition(name) for name in _resolved_registry()}  # type: ignore[misc]


def _invalidate_caches() -> None:
    """Clear the merged-registry caches.

    Called after :func:`register_tool` / :func:`unregister_tool` mutate the
    built-in baseline so subsequent lookups see the change. Tests that
    install fake entry-points also call this to force a re-scan.
    """
    _resolved_registry.cache_clear()
    _resolved_type_index.cache_clear()


def register_tool(
    name: str,
    tool_type: str,
    module: str,
    params: dict[str, Any] | None = None,
) -> None:
    """
    Register a new tool in the built-in baseline registry.

    Plugins distributed as installed packages should prefer the
    ``taskforce.tools`` entry-point group (see
    :mod:`taskforce.application.agent_plugin_registry`). Direct registration
    via this function remains supported for runtime-only contributions and
    tests.

    Args:
        name: Short name for the tool (used in configs)
        tool_type: Class name of the tool
        module: Full module path to the tool class
        params: Default parameters for the tool

    Raises:
        ValueError: If tool name already exists in the built-in baseline
            (entry-point overrides are ignored — they re-apply on cache reset).
    """
    if name in _BUILTIN_REGISTRY:
        raise ValueError(f"Tool '{name}' already registered in registry")

    _BUILTIN_REGISTRY[name] = {
        "type": tool_type,
        "module": module,
        "params": params or {},
    }
    _invalidate_caches()


def unregister_tool(name: str) -> bool:
    """
    Remove a tool from the built-in baseline.

    Note: entry-point-contributed tools cannot be unregistered through this
    function — uninstall the providing package or call
    :func:`_invalidate_caches` after monkey-patching for tests.

    Args:
        name: Tool name to remove

    Returns:
        True if tool was removed, False if not found in baseline.
    """
    if name in _BUILTIN_REGISTRY:
        del _BUILTIN_REGISTRY[name]
        _invalidate_caches()
        return True
    return False


def is_registered(name: str) -> bool:
    """
    Check if a tool name is registered (built-in or via entry-point).

    Args:
        name: Tool name to check

    Returns:
        True if tool is registered
    """
    return name in _resolved_registry()
