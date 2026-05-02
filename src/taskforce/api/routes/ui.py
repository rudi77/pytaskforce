"""
UI Manifest Route
=================

Exposes ``GET /api/v1/ui/manifest`` so the React management UI can
discover which optional plugins are loaded on the backend and which
capabilities they contribute. The shell uses the response to decide
which plugin nav items and routes to mount.

Plugins opt in to UI integration by implementing
``get_ui_manifest()`` on their plugin class (see
:class:`taskforce.application.plugin_loader.PluginProtocol`). Plugins
without the method are silently skipped, so this endpoint stays
compatible with existing plugins.
"""

from __future__ import annotations

from fastapi import APIRouter

from taskforce.api.schemas.ui_manifest import UIManifestEntry, UIManifestResponse
from taskforce.application.plugin_loader import collect_ui_manifests

router = APIRouter()


def _get_server_version() -> str:
    """Best-effort lookup of the installed taskforce package version."""
    try:
        from importlib.metadata import version

        return version("taskforce")
    except Exception:
        return "0.0.0-dev"


@router.get("/ui/manifest", response_model=UIManifestResponse, tags=["ui"])
async def get_ui_manifest() -> UIManifestResponse:
    """Return UI manifests contributed by all loaded backend plugins."""
    raw_manifests = collect_ui_manifests()
    entries = [UIManifestEntry.model_validate(dict(m)) for m in raw_manifests]
    return UIManifestResponse(plugins=entries, server_version=_get_server_version())
