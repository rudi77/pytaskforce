"""Resolve the active deployment manifest from settings + YAML.

The deployment manifest is the allowlist of agent ids visible in
listings. Two sources can supply it:

1. The runtime **settings store** (UI-managed). When the
   ``visible_agents`` section is present and contains a non-empty
   ``agents`` list, it takes precedence — operators editing the list
   in the UI expect their changes to win immediately.
2. The shipped **deployment.yaml** under ``src/taskforce/configs/``.
   Used as the fallback when the settings store has nothing to say.

This module is the single seam where those two sources are merged.
The core ``load_deployment_manifest`` helper in
``taskforce.core.domain.deployment`` deliberately knows nothing about
the settings store — keeping the dependency from core into the
application layer one-way.
"""

from __future__ import annotations

from typing import Any

import structlog

from taskforce.core.domain.settings import VISIBLE_AGENTS

# ``DeploymentManifest`` is imported lazily inside the helpers so that
# tests can patch ``taskforce.core.domain.deployment.load_deployment_manifest``
# at the canonical location and still see the resolver pick the patched
# value up. Importing at module scope would freeze the bound name in the
# resolver's namespace.

logger = structlog.get_logger(__name__)


def _manifest_from_settings(store: Any):
    """Build a manifest from the ``visible_agents`` settings section."""
    from taskforce.core.domain.deployment import DeploymentManifest

    try:
        section = store.get(VISIBLE_AGENTS)
    except Exception:  # noqa: BLE001 — buggy plugin store must not break startup
        logger.warning("deployment_manifest.settings_read_failed", exc_info=True)
        return None
    if not isinstance(section, dict):
        return None
    agents = section.get("agents")
    if not isinstance(agents, list) or not agents:
        return None
    visible = frozenset(str(a).strip() for a in agents if str(a).strip())
    if not visible:
        return None
    logger.debug("deployment_manifest.from_settings", count=len(visible))
    return DeploymentManifest(visible_agents=visible)


def resolve_deployment_manifest(store: Any | None):
    """Return the active manifest, preferring the settings store.

    Args:
        store: Optional settings store. When ``None`` the resolver
            skips the settings path entirely (used by callers that have
            no store wired up).

    Returns:
        The first manifest that resolves, or ``None`` when neither
        source has one — the registry then falls back to its legacy
        unfiltered behaviour.
    """
    from taskforce.core.domain.deployment import load_deployment_manifest

    if store is not None:
        manifest = _manifest_from_settings(store)
        if manifest is not None:
            return manifest
    return load_deployment_manifest()
