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
    version: str = Field("", description="Plugin version for diagnostics")
    display_name: str = Field("", description="Human-readable plugin name")
    capabilities: list[str] = Field(
        default_factory=list,
        description="Capability flags this plugin reports as active",
    )
    npm_package: str | None = Field(
        None,
        description="Optional npm package name that ships matching React components",
    )
    min_ui_version: str | None = Field(
        None,
        description="Optional semver range for the host UI shell version",
    )


class UIManifestResponse(BaseModel):
    """Envelope returned by ``GET /api/v1/ui/manifest``."""

    plugins: list[UIManifestEntry] = Field(
        default_factory=list,
        description="UI manifests contributed by loaded backend plugins",
    )
    server_version: str = Field(
        "",
        description="Taskforce server version, useful for skew detection",
    )
