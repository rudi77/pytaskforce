"""
UI Manifest API Schemas
=======================

Pydantic models for the management-UI plugin-manifest endpoint
(``GET /api/v1/ui/manifest``). The endpoint reports which optional
plugins are loaded on the backend so the React shell can decide which
nav items and routes to expose.

The contract intentionally mirrors :class:`taskforce.application.plugin_loader.UIManifest`
(a TypedDict) but adds Pydantic validation and an envelope with the
server version so the UI can detect version skew.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class UIManifestEntry(BaseModel):
    """One plugin's contribution to the UI manifest."""

    id: str = Field(..., description="Stable plugin identifier (e.g. 'enterprise')")
    capabilities: list[str] = Field(
        ...,
        description="Capability flags this plugin reports as active. Must be non-empty.",
        min_length=1,
    )
    version: str = Field("0.0.0", description="Plugin version for diagnostics")
    display_name: str = Field("", description="Human-readable plugin name")
    npm_package: str | None = Field(
        None,
        description="Optional npm package name that ships matching React components",
    )
    min_ui_version: str | None = Field(
        None,
        description="Optional semver range for the host UI shell version",
    )


class UIManifestResponse(BaseModel):
    """Envelope returned by ``GET /api/v1/ui/manifest``.

    The response is intentionally minimal: it lists which optional UI
    plugins are active so the React shell can decide which sidebar
    entries and routes to mount. We deliberately do **not** include
    the server version here — the endpoint is unauthenticated and
    server-version disclosure is reconnaissance gold for fingerprinting.
    Authenticated callers can use ``GET /health`` for that.
    """

    plugins: list[UIManifestEntry] = Field(
        default_factory=list,
        description="UI manifests contributed by loaded backend plugins",
    )
