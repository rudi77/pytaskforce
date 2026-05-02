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

import structlog
from fastapi import APIRouter
from pydantic import ValidationError

from taskforce.api.schemas.ui_manifest import UIManifestEntry, UIManifestResponse
from taskforce.application.plugin_loader import collect_ui_manifests

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get("/ui/manifest", response_model=UIManifestResponse, tags=["ui"])
async def get_ui_manifest() -> UIManifestResponse:
    """Return UI manifests contributed by all loaded backend plugins.

    Each loaded plugin may implement
    :py:meth:`PluginProtocol.get_ui_manifest`; plugins without the
    method are silently skipped. Manifests that fail Pydantic
    validation (e.g. missing required fields, empty capabilities) are
    logged and dropped rather than failing the whole endpoint, so one
    misbehaving plugin can never blank out the UI.
    """
    raw_manifests = collect_ui_manifests()
    entries: list[UIManifestEntry] = []
    for manifest in raw_manifests:
        try:
            entries.append(UIManifestEntry.model_validate(dict(manifest)))
        except ValidationError as exc:
            logger.warning(
                "plugin.ui_manifest_invalid",
                plugin_id=manifest.get("id", "<unknown>"),
                errors=exc.errors(include_url=False),
            )
    return UIManifestResponse(plugins=entries)
