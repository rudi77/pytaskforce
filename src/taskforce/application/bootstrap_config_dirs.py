"""
Bootstrap Config Directories
============================

Centralised registration of agent-package config directories with the
:class:`~taskforce.application.profile_loader.ProfileLoader`.

The CLI (``taskforce_cli``) and the FastAPI server both need profile
discovery to span the framework configs **and** any installed agent
packages (``taskforce_butler``, ``taskforce_coding_agent``,
``taskforce_rag_agent``). This module provides a single idempotent entry
point both call sites use.

Why a separate module:
    Previously this responsibility lived inside ``taskforce_cli`` and was
    only triggered on CLI startup, so the API server could not list or
    resolve agent-package profiles. Centralising it here lets the API
    lifespan hook into the same registration path without depending on
    ``taskforce_cli``.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_KNOWN_AGENT_PACKAGES: tuple[tuple[str, str], ...] = (
    ("taskforce_butler", "configs"),
    ("taskforce_coding_agent", "configs"),
    ("taskforce_rag_agent", "configs"),
)

# Subdirs of each agent-package ``configs/`` dir that also hold YAML
# profiles. Without registering these the framework's FileAgentRegistry
# only scans top-level YAMLs and silently hides every sub-agent (issue
# #235): butler's accountant / pc-agent / research_agent (custom),
# butler's accountant / personal_assistant role files (roles), and the
# entire coding sub-agent suite (custom).
_NESTED_PROFILE_SUBDIRS: tuple[str, ...] = ("custom", "roles")

_initialized = False


def _discover_agent_config_dirs() -> list[Path]:
    """Locate ``configs/`` directories shipped by installed agent packages.

    Walks up from the package ``__init__.py`` until a ``configs/`` sibling
    is found (or we run out of ancestors). This handles both flat layouts
    (``foo/configs/``) and src-layout (``agents/foo/src/foo/__init__.py``
    with ``agents/foo/configs/`` two levels up).

    Returns:
        List of absolute paths to existing config directories. Packages
        that are not importable are silently skipped.
    """
    dirs: list[Path] = []
    for package_name, config_rel in _KNOWN_AGENT_PACKAGES:
        try:
            mod = importlib.import_module(package_name)
        except ImportError:
            logger.debug("agent_package_not_installed", package=package_name)
            continue
        if mod.__file__ is None:
            continue
        package_dir = Path(mod.__file__).resolve().parent
        # Try the package dir and up to four ancestors so editable installs
        # that ship configs at the project root (sibling of ``src/``) work.
        candidates: list[Path] = [package_dir]
        candidates.extend(package_dir.parents[:4])
        found = None
        for base in candidates:
            candidate = base / config_rel
            if candidate.is_dir():
                found = candidate
                break
        if found is not None:
            dirs.append(found)
            logger.debug(
                "agent_config_dir_found",
                package=package_name,
                path=str(found),
            )
            for subdir_name in _NESTED_PROFILE_SUBDIRS:
                subdir = found / subdir_name
                if subdir.is_dir():
                    dirs.append(subdir)
                    logger.debug(
                        "agent_config_dir_found",
                        package=package_name,
                        path=str(subdir),
                        parent=str(found),
                    )
    return dirs


def bootstrap_config_dirs(force: bool = False) -> list[Path]:
    """Register agent-package config dirs with the global ProfileLoader.

    Idempotent — repeated calls are no-ops unless ``force=True``.

    Args:
        force: When ``True``, re-runs discovery even if the bootstrap was
            already performed in this process. Useful for tests.

    Returns:
        List of directories that were registered (or would be registered
        again if ``force`` was set).
    """
    global _initialized
    if _initialized and not force:
        return []

    from taskforce.application.profile_loader import register_config_dir

    registered: list[Path] = []
    for config_dir in _discover_agent_config_dirs():
        register_config_dir(config_dir)
        registered.append(config_dir)
        logger.debug("bootstrap_config_dir_registered", path=str(config_dir))

    _initialized = True
    return registered
