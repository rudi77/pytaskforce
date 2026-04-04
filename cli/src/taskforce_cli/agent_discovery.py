"""Discover and register configs/tools from installed agent packages.

This module provides two capabilities:

1. **Config directory discovery** — finds YAML config directories shipped by
   agent packages (``taskforce_butler``, ``taskforce_coding_agent``,
   ``taskforce_rag_agent``) and registers them with the framework's
   ``ProfileLoader`` so that ``--profile`` flags work seamlessly.

2. **Tool registration** — returns a mapping of short tool names to lazy
   import descriptors so the framework ``ToolRegistry`` can resolve tools
   contributed by agent packages without hard-coding them.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Known agent packages and the expected relative path (from the package
# ``__init__.py``) to their configs directory.
_AGENT_PACKAGES: list[tuple[str, str]] = [
    ("taskforce_butler", "configs"),
    ("taskforce_coding_agent", "configs"),
    ("taskforce_rag_agent", "configs"),
]


# ------------------------------------------------------------------
# Config directory discovery
# ------------------------------------------------------------------


def get_agent_config_dirs() -> list[Path]:
    """Return config directories from all installed agent packages.

    For each known agent package the function attempts to import it and
    locate a ``configs/`` directory relative to the package root.  Only
    directories that actually exist on disk are returned.

    Returns:
        List of absolute ``Path`` objects pointing to config directories.
    """
    dirs: list[Path] = []
    for package_name, config_rel in _AGENT_PACKAGES:
        try:
            mod = importlib.import_module(package_name)
            if mod.__file__ is None:
                continue
            package_dir = Path(mod.__file__).resolve().parent
            config_dir = package_dir / config_rel
            if config_dir.is_dir():
                dirs.append(config_dir)
                logger.debug(
                    "agent_config_dir_found",
                    package=package_name,
                    path=str(config_dir),
                )
            else:
                # Try one level up (src/taskforce_xxx/../configs)
                alt_config_dir = package_dir.parent / config_rel
                if alt_config_dir.is_dir():
                    dirs.append(alt_config_dir)
                    logger.debug(
                        "agent_config_dir_found",
                        package=package_name,
                        path=str(alt_config_dir),
                    )
        except ImportError:
            logger.debug("agent_package_not_installed", package=package_name)
    return dirs


def register_agent_config_dirs() -> None:
    """Discover agent config dirs and register them with the ProfileLoader.

    This is the main integration point called during CLI startup.  It uses
    :func:`get_agent_config_dirs` to find directories and then calls
    :func:`taskforce.application.profile_loader.register_config_dir` for
    each one so that profile resolution includes agent-shipped configs.
    """
    from taskforce.application.profile_loader import register_config_dir

    for config_dir in get_agent_config_dirs():
        register_config_dir(config_dir)
        logger.debug("registered_agent_config_dir", path=str(config_dir))


# ------------------------------------------------------------------
# Tool registration
# ------------------------------------------------------------------


def get_agent_tool_registrations() -> dict[str, dict[str, Any]]:
    """Return tool registrations from installed agent packages.

    Each entry maps a short tool name to a descriptor dict with keys:

    * ``type`` — class name of the tool implementation
    * ``module`` — fully-qualified module path for lazy import
    * ``params`` — default constructor kwargs (usually empty)

    Only tools whose parent package is importable are included.

    Returns:
        Mapping of ``{short_name: descriptor}``.
    """
    tools: dict[str, dict[str, Any]] = {}

    # Butler tools
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
        logger.debug("agent_tools_registered", package="taskforce_butler", count=5)
    except ImportError:
        pass

    # Coding agent tools
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
        logger.debug("agent_tools_registered", package="taskforce_coding_agent", count=1)
    except ImportError:
        pass

    # RAG agent tools
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
        logger.debug("agent_tools_registered", package="taskforce_rag_agent", count=4)
    except ImportError:
        pass

    return tools
