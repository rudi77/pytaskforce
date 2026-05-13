"""Discover and register configs/tools from installed agent packages.

This module provides two capabilities:

1. **Config directory discovery** — finds YAML config directories shipped by
   agent packages and registers them with the framework's
   ``ProfileLoader`` so that ``--profile`` flags work seamlessly.

2. **Tool registration** — returns a mapping of short tool names to lazy
   import descriptors so the framework ``ToolRegistry`` can resolve tools
   contributed by agent packages without hard-coding them.

Both lookups read Python entry-points first (groups ``taskforce.tools``
and ``taskforce.config_dirs`` — see
:mod:`taskforce.application.agent_plugin_registry`), then merge in any
legacy hardcoded entries from ``_AGENT_PACKAGES`` for packages that
haven't migrated yet. Fallback hits are logged as
``hardcoded_agent_fallback`` so they can be grepped out once every
agent has shipped entry-points.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import structlog

from taskforce.application.agent_plugin_registry import (
    load_config_dirs,
    load_tool_descriptors,
)

logger = structlog.get_logger(__name__)

# Legacy hardcoded fallback table. Used only for packages that don't yet
# declare entry-points. Removed in Phase 4 once every agent ships its own
# ``taskforce.config_dirs`` / ``taskforce.tools`` entries.
_AGENT_PACKAGES: list[tuple[str, str]] = [
    ("taskforce_butler", "configs"),
    ("taskforce_coding_agent", "configs"),
    ("taskforce_rag_agent", "configs"),
]


# ------------------------------------------------------------------
# Config directory discovery
# ------------------------------------------------------------------


def _legacy_config_dirs() -> dict[str, Path]:
    """Probe ``_AGENT_PACKAGES`` for installed packages without entry-points.

    Mirrors the original probe sequence (package_dir/, parent/, parent.parent/)
    so editable installs keep resolving. Logged at ``hardcoded_agent_fallback``
    level so the noise points at deletion candidates.
    """
    dirs: dict[str, Path] = {}
    for package_name, config_rel in _AGENT_PACKAGES:
        try:
            mod = importlib.import_module(package_name)
        except ImportError:
            logger.debug("agent_package_not_installed", package=package_name)
            continue
        if getattr(mod, "__file__", None) is None:
            continue
        package_dir = Path(mod.__file__).resolve().parent
        candidates = [
            package_dir / config_rel,
            package_dir.parent / config_rel,
            package_dir.parent.parent / config_rel,
        ]
        for candidate in candidates:
            if candidate.is_dir():
                dirs[package_name] = candidate
                logger.warning(
                    "hardcoded_agent_fallback",
                    component="config_dirs",
                    package=package_name,
                    path=str(candidate),
                    hint="declare [project.entry-points.\"taskforce.config_dirs\"] in this package's pyproject.toml",
                )
                break
    return dirs


def get_agent_config_dirs() -> list[Path]:
    """Return config directories discovered from all installed agent packages.

    Entry-point contributions (``taskforce.config_dirs``) take priority; any
    legacy ``_AGENT_PACKAGES`` entry not covered by an entry-point is added
    as a fallback (with a warning).

    Returns:
        Deduplicated list of absolute ``Path`` objects.
    """
    entry_point_dirs = load_config_dirs()  # {agent_name: Path}
    fallback_dirs = _legacy_config_dirs()  # {pkg_name: Path}

    # Build the deduplicated path list. Entry-points first (preferred);
    # then any fallback path not already in the set.
    seen: set[Path] = set()
    result: list[Path] = []
    for path in entry_point_dirs.values():
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(path)
    for path in fallback_dirs.values():
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(path)
    return result


_NESTED_SUBDIRS = ("custom", "roles")


def register_agent_config_dirs() -> None:
    """Discover agent config dirs and register them with the ProfileLoader.

    This is the main integration point called during CLI startup. For
    every discovered agent package it registers:

    - The top-level ``configs/`` dir (the agent's main profile lives here)
    - ``configs/custom/`` — Butler/coding sub-agents and butler custom roles
    - ``configs/roles/`` — Butler role specializations (accountant, …)

    Without the nested-subdir registration the framework's
    ``FileAgentRegistry`` scans only top-level YAMLs in extra dirs, which
    silently hides every sub-agent the user expects to see in
    ``GET /api/v1/agents`` (issue #235).
    """
    from taskforce.application.profile_loader import register_config_dir

    for config_dir in get_agent_config_dirs():
        register_config_dir(config_dir)
        logger.debug("registered_agent_config_dir", path=str(config_dir))
        for subdir_name in _NESTED_SUBDIRS:
            subdir = config_dir / subdir_name
            if subdir.is_dir():
                register_config_dir(subdir)
                logger.debug(
                    "registered_agent_config_dir",
                    path=str(subdir),
                    parent=str(config_dir),
                )


# ------------------------------------------------------------------
# Tool registration
# ------------------------------------------------------------------


def _legacy_tool_registrations() -> dict[str, dict[str, Any]]:
    """Hardcoded tool descriptors for packages that don't yet declare entry-points.

    Each block is gated on a package import so it disappears cleanly when
    the package is uninstalled. Logged at ``hardcoded_agent_fallback``
    level so the noise points at deletion candidates.
    """
    tools: dict[str, dict[str, Any]] = {}

    try:
        import taskforce_butler  # noqa: F401

        tools.update(
            {
                "calendar": {
                    "type": "CalendarTool",
                    "module": "taskforce_butler.infrastructure.tools.calendar_tool",
                    "params": {},
                },
                "gmail": {
                    "type": "GmailTool",
                    "module": "taskforce_butler.infrastructure.tools.email_tool",
                    "params": {},
                },
                "schedule": {
                    "type": "ScheduleTool",
                    "module": "taskforce_butler.infrastructure.tools.schedule_tool",
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
            }
        )
        logger.warning(
            "hardcoded_agent_fallback",
            component="tools",
            package="taskforce_butler",
            count=5,
            hint="declare [project.entry-points.\"taskforce.tools\"] in agents/butler/pyproject.toml",
        )
    except ImportError:
        pass

    try:
        import taskforce_coding_agent  # noqa: F401

        tools.update(
            {
                "call_agents_parallel": {
                    "type": "ParallelAgentTool",
                    "module": "taskforce_coding_agent.infrastructure.tools.parallel_agent_tool",
                    "params": {},
                },
            }
        )
        logger.warning(
            "hardcoded_agent_fallback",
            component="tools",
            package="taskforce_coding_agent",
            count=1,
            hint="declare [project.entry-points.\"taskforce.tools\"] in agents/coding-agent/pyproject.toml",
        )
    except ImportError:
        pass

    try:
        import taskforce_rag_agent  # noqa: F401

        tools.update(
            {
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
            }
        )
        logger.warning(
            "hardcoded_agent_fallback",
            component="tools",
            package="taskforce_rag_agent",
            count=4,
            hint="declare [project.entry-points.\"taskforce.tools\"] in agents/rag-agent/pyproject.toml",
        )
    except ImportError:
        pass

    return tools


def get_agent_tool_registrations() -> dict[str, dict[str, Any]]:
    """Return tool registrations from all installed agent packages.

    Entry-point contributions (``taskforce.tools``) win on name collision;
    any legacy hardcoded entry for a tool name not covered by an entry-point
    is merged in as a fallback (with a warning).
    """
    entry_point_tools = load_tool_descriptors()
    fallback_tools = _legacy_tool_registrations()
    merged: dict[str, dict[str, Any]] = dict(fallback_tools)
    merged.update(entry_point_tools)  # entry-points win on overlap
    return merged
