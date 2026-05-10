"""Deployment manifest — declares which agents a deployment exposes.

A ``DeploymentManifest`` is a small allowlist of agent ids / profile
names that should appear in user-facing listings (``/api/v1/agents``,
``taskforce config profiles``). Agents *not* on the list remain
loadable by id (so a master agent can still extend a sub-agent), they
just stay out of the visible catalog.

The manifest is the seam through which an operator (or the enterprise
plugin, on a per-tenant basis) controls *what we ship*. The framework
ships a default manifest at ``src/taskforce/configs/deployment.yaml``;
the path can be overridden via the ``TASKFORCE_DEPLOYMENT_MANIFEST``
environment variable, by passing an explicit path to
:func:`load_deployment_manifest`, or — for tenant-scoped overrides —
via the ``set_deployment_manifest_override`` infrastructure hook.

When no manifest can be resolved the loader returns ``None`` and the
registry falls back to its legacy "show everything" behaviour, so
existing tests and embedded users that don't ship a manifest are
unaffected.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import structlog
import yaml

logger = structlog.get_logger(__name__)

DEPLOYMENT_MANIFEST_ENV = "TASKFORCE_DEPLOYMENT_MANIFEST"


@dataclass(frozen=True)
class DeploymentManifest:
    """Declares which agents are visible in user-facing listings.

    Attributes:
        visible_agents: Set of agent ids / profile names that appear
            in listings. Lookups by id (``get_agent``) are not affected.
    """

    visible_agents: frozenset[str]

    def is_visible(self, agent_id: str) -> bool:
        """Return True if ``agent_id`` should appear in user-facing listings."""
        return agent_id in self.visible_agents


def _default_manifest_path() -> Path:
    """Resolve the framework's shipped default deployment manifest path."""
    from taskforce.core.utils.paths import get_base_path

    return get_base_path() / "src" / "taskforce" / "configs" / "deployment.yaml"


def load_deployment_manifest(path: Path | str | None = None) -> DeploymentManifest | None:
    """Load a deployment manifest from disk.

    Resolution order:

    1. Explicit ``path`` argument.
    2. ``TASKFORCE_DEPLOYMENT_MANIFEST`` environment variable.
    3. Framework default at ``src/taskforce/configs/deployment.yaml``.

    Args:
        path: Optional explicit path to a manifest YAML file.

    Returns:
        Loaded :class:`DeploymentManifest`, or ``None`` if no manifest
        is available at any of the candidate locations (registry then
        falls back to its legacy unfiltered behaviour).
    """
    candidate: Path | None = None
    if path is not None:
        candidate = Path(path)
    elif env_path := os.getenv(DEPLOYMENT_MANIFEST_ENV):
        candidate = Path(env_path)
    else:
        default = _default_manifest_path()
        if default.exists():
            candidate = default

    if candidate is None or not candidate.exists():
        logger.debug("deployment_manifest.not_found", path=str(candidate) if candidate else None)
        return None

    try:
        with candidate.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("deployment_manifest.load_failed", path=str(candidate), error=str(exc))
        return None

    raw_visible = data.get("visible_agents", [])
    if not isinstance(raw_visible, list):
        logger.warning(
            "deployment_manifest.invalid_visible_agents",
            path=str(candidate),
            type=type(raw_visible).__name__,
        )
        return None

    visible = frozenset(str(item).strip() for item in raw_visible if str(item).strip())
    logger.debug(
        "deployment_manifest.loaded",
        path=str(candidate),
        count=len(visible),
    )
    return DeploymentManifest(visible_agents=visible)
