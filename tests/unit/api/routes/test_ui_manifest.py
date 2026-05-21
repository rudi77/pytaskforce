"""Unit tests for the UI manifest route and ``collect_ui_manifests``."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from taskforce.api.server import create_app
from taskforce.application import plugin_loader
from taskforce.application.plugin_loader import (
    PluginInfo,
    PluginRegistry,
    collect_ui_manifests,
)


class _StubPlugin:
    """Minimal plugin double that mimics a loaded plugin instance."""

    def __init__(
        self,
        name: str,
        manifest: dict | None,
        *,
        raises: bool = False,
    ) -> None:
        self.name = name
        self.version = "1.0.0"
        self._manifest = manifest
        self._raises = raises

    def get_ui_manifest(self):
        if self._raises:
            raise RuntimeError("boom")
        return self._manifest


class _PluginWithoutUiManifest:
    """A plugin that does not implement ``get_ui_manifest`` at all."""

    name = "legacy"
    version = "1.0.0"


@pytest.fixture
def isolated_registry(monkeypatch):
    """Replace the global plugin registry with a fresh one for each test."""
    fresh = PluginRegistry()
    monkeypatch.setattr(plugin_loader, "_plugin_registry", fresh)
    yield fresh


def _register_loaded(registry: PluginRegistry, name: str, instance) -> None:
    info = PluginInfo(name=name, entry_point=f"{name}:plugin")
    info.plugin_class = instance.__class__
    info.instance = instance
    info.initialized = True
    registry.plugins[name] = info


def test_collect_ui_manifests_returns_empty_when_no_plugins(isolated_registry):
    assert collect_ui_manifests() == []


def test_collect_ui_manifests_returns_manifest_payload(isolated_registry):
    manifest = {
        "id": "enterprise",
        "version": "1.2.3",
        "display_name": "Taskforce Enterprise",
        "capabilities": ["admin.users", "admin.audit"],
        "npm_package": "@taskforce/enterprise-ui",
        "min_ui_version": ">=1.0.0",
    }
    _register_loaded(isolated_registry, "enterprise", _StubPlugin("enterprise", manifest))

    result = collect_ui_manifests()

    assert len(result) == 1
    assert result[0]["id"] == "enterprise"
    assert result[0]["capabilities"] == ["admin.users", "admin.audit"]


def test_collect_ui_manifests_skips_plugins_without_method(isolated_registry):
    _register_loaded(isolated_registry, "legacy", _PluginWithoutUiManifest())

    assert collect_ui_manifests() == []


@pytest.mark.spec("plugins.ui_manifest_invalid_payload_is_dropped")
def test_collect_ui_manifests_skips_plugin_returning_none(isolated_registry):
    _register_loaded(isolated_registry, "quiet", _StubPlugin("quiet", None))

    assert collect_ui_manifests() == []


@pytest.mark.spec("plugins.ui_manifest_getter_exception_is_skipped")
def test_collect_ui_manifests_swallows_plugin_errors(isolated_registry):
    """A buggy plugin must not break the manifest endpoint for everyone else."""
    _register_loaded(isolated_registry, "broken", _StubPlugin("broken", None, raises=True))
    _register_loaded(
        isolated_registry,
        "ok",
        _StubPlugin("ok", {"id": "ok", "capabilities": ["x"]}),
    )

    result = collect_ui_manifests()

    assert len(result) == 1
    assert result[0]["id"] == "ok"


@pytest.fixture
def client(isolated_registry):
    app = create_app()
    return TestClient(app)


def test_manifest_endpoint_empty_payload(client):
    response = client.get("/api/v1/ui/manifest")
    assert response.status_code == 200
    body = response.json()
    assert body["plugins"] == []
    # Endpoint deliberately does not expose the server version (info disclosure).
    assert "server_version" not in body


def test_manifest_endpoint_returns_registered_plugin(isolated_registry, client):
    manifest = {
        "id": "enterprise",
        "version": "1.0.0",
        "display_name": "Taskforce Enterprise",
        "capabilities": ["admin.users"],
        "npm_package": "@taskforce/enterprise-ui",
    }
    _register_loaded(isolated_registry, "enterprise", _StubPlugin("enterprise", manifest))

    response = client.get("/api/v1/ui/manifest")

    assert response.status_code == 200
    body = response.json()
    assert len(body["plugins"]) == 1
    plugin = body["plugins"][0]
    assert plugin["id"] == "enterprise"
    assert plugin["display_name"] == "Taskforce Enterprise"
    assert plugin["capabilities"] == ["admin.users"]
    assert plugin["npm_package"] == "@taskforce/enterprise-ui"
