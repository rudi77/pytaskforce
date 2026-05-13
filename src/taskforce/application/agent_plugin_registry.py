"""Entry-point-based discovery of agent-package contributions.

This module reads ``importlib.metadata`` entry-points to discover three
kinds of contributions from any installed agent package (or external
plugin):

* ``taskforce.tools`` — tool short-names → ``"module.path:ClassName"``.
  Mapped to the descriptor shape the framework
  :data:`taskforce.infrastructure.tools.registry._BUILTIN_REGISTRY` already
  uses, so callers can merge the result on top of the hardcoded baseline.
* ``taskforce.cli_apps`` — subcommand name → ``"module.path:typer_app"``.
  Loaded eagerly and returned as ``{name: typer.Typer}`` for the unified
  CLI's ``add_typer`` call.
* ``taskforce.config_dirs`` — agent name → ``"package_module:relpath"``.
  Resolved to filesystem paths suitable for
  :func:`taskforce.application.profile_loader.register_config_dir`.

All entry-point loads are ImportError- and ValueError-tolerant: a
malformed or non-importable contribution emits a ``structlog`` warning
and is skipped, so a single broken plugin never breaks discovery for
the rest.

The module owns *no* state — callers cache the merged dicts themselves
(e.g. via ``functools.lru_cache`` in the tool registry). See
``docs/adr/adr-026-entry-point-plugin-discovery.md`` for the design.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# Entry-point group names. Public constants — agent packages reference
# these in their ``[project.entry-points.<group>]`` blocks.
GROUP_TOOLS = "taskforce.tools"
GROUP_CLI_APPS = "taskforce.cli_apps"
GROUP_CONFIG_DIRS = "taskforce.config_dirs"


def iter_entry_points(group: str) -> Iterator[EntryPoint]:
    """Yield entry points for ``group`` without raising on metadata errors.

    Wraps :func:`importlib.metadata.entry_points` so transient packaging
    issues (corrupt wheel metadata, partial installs) become a logged
    warning instead of a startup crash.
    """
    try:
        eps = entry_points(group=group)
    except Exception as exc:  # noqa: BLE001 — startup must never fail here
        logger.warning(
            "agent_plugin_registry.entry_points_failed",
            group=group,
            error=str(exc),
        )
        return
    yield from eps


def load_tool_descriptors() -> dict[str, dict[str, Any]]:
    """Return ``{short_name: descriptor}`` from ``taskforce.tools`` entry-points.

    Descriptor shape matches
    :data:`taskforce.infrastructure.tools.registry._BUILTIN_REGISTRY` so
    the result can be merged directly: ``{"type", "module", "params"}``.

    Entries whose target module fails to import are skipped (logged) so
    one missing dependency doesn't hide unrelated tools.
    """
    descriptors: dict[str, dict[str, Any]] = {}
    for ep in iter_entry_points(GROUP_TOOLS):
        module_path, _, class_name = ep.value.partition(":")
        if not module_path or not class_name:
            logger.warning(
                "agent_plugin_registry.malformed_tool_entry_point",
                name=ep.name,
                value=ep.value,
            )
            continue
        try:
            importlib.import_module(module_path)
        except ImportError as exc:
            logger.warning(
                "agent_plugin_registry.tool_module_missing",
                name=ep.name,
                module=module_path,
                error=str(exc),
            )
            continue
        descriptors[ep.name] = {
            "type": class_name,
            "module": module_path,
            "params": {},
        }
        logger.debug(
            "agent_plugin_registry.tool_registered",
            name=ep.name,
            module=module_path,
            cls=class_name,
        )
    return descriptors


def load_cli_apps() -> dict[str, Any]:
    """Return ``{subcommand_name: typer.Typer}`` from ``taskforce.cli_apps``.

    The return type is ``Any`` to avoid forcing the framework to import
    ``typer`` at module load — callers that pass these into
    ``typer.Typer.add_typer`` handle the typing implicitly.
    """
    apps: dict[str, Any] = {}
    for ep in iter_entry_points(GROUP_CLI_APPS):
        try:
            target = ep.load()
        except Exception as exc:  # noqa: BLE001 — log and skip
            logger.warning(
                "agent_plugin_registry.cli_app_load_failed",
                name=ep.name,
                value=ep.value,
                error=str(exc),
            )
            continue
        apps[ep.name] = target
        logger.debug(
            "agent_plugin_registry.cli_app_registered",
            name=ep.name,
            value=ep.value,
        )
    return apps


def load_config_dirs() -> dict[str, Path]:
    """Return ``{agent_name: Path}`` from ``taskforce.config_dirs`` entry-points.

    The entry-point value has the form ``"package_module:relpath"``.
    The package is imported, its filesystem location resolved, and
    three candidate paths are probed in order so editable installs
    (``src/<pkg>/configs``, ``../configs``, ``../../configs``) are all
    handled — the same probe sequence the legacy hardcoded discovery
    used.
    """
    dirs: dict[str, Path] = {}
    for ep in iter_entry_points(GROUP_CONFIG_DIRS):
        module_path, _, rel_path = ep.value.partition(":")
        if not module_path:
            logger.warning(
                "agent_plugin_registry.malformed_config_dirs_entry_point",
                name=ep.name,
                value=ep.value,
            )
            continue
        try:
            mod = importlib.import_module(module_path)
        except ImportError as exc:
            logger.warning(
                "agent_plugin_registry.config_dirs_module_missing",
                name=ep.name,
                module=module_path,
                error=str(exc),
            )
            continue
        if getattr(mod, "__file__", None) is None:
            logger.warning(
                "agent_plugin_registry.config_dirs_module_has_no_file",
                name=ep.name,
                module=module_path,
            )
            continue
        package_dir = Path(mod.__file__).resolve().parent
        candidates = [
            package_dir / rel_path,
            package_dir.parent / rel_path,
            package_dir.parent.parent / rel_path,
        ]
        for candidate in candidates:
            if candidate.is_dir():
                dirs[ep.name] = candidate
                logger.debug(
                    "agent_plugin_registry.config_dir_found",
                    name=ep.name,
                    path=str(candidate),
                )
                break
        else:
            logger.warning(
                "agent_plugin_registry.config_dir_not_found",
                name=ep.name,
                module=module_path,
                rel_path=rel_path,
                tried=[str(c) for c in candidates],
            )
    return dirs


__all__ = [
    "GROUP_CLI_APPS",
    "GROUP_CONFIG_DIRS",
    "GROUP_TOOLS",
    "iter_entry_points",
    "load_cli_apps",
    "load_config_dirs",
    "load_tool_descriptors",
]
