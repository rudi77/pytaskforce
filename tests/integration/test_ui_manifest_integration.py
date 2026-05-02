"""End-to-end integration tests for the UI manifest pipeline.

These tests exercise the full chain — `PluginProtocol.get_ui_manifest`
→ `collect_ui_manifests` → `GET /api/v1/ui/manifest` — through the
real FastAPI application, with a fake plugin registered in the
process-global registry. This complements the focused unit tests in
``tests/unit/api/routes/test_ui_manifest.py`` by checking that the
manifest endpoint plays nicely with the rest of ``create_app()``,
including the existing health endpoint and Pydantic validation.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from taskforce.api.server import create_app
from taskforce.application import plugin_loader
from taskforce.application.plugin_loader import PluginInfo, PluginRegistry


class _FakeEnterprisePlugin:
    """Stand-in for the real `taskforce_enterprise.EnterprisePlugin`.

    Returns the same manifest shape the actual plugin will return so
    the host UI can develop against the wire format without depending
    on the enterprise package being installed.
    """

    name = "enterprise"
    version = "1.0.0"

    def get_middleware(self):
        return []

    def get_routers(self):
        return []

    def get_ui_manifest(self):
        return {
            "id": "enterprise",
            "version": self.version,
            "display_name": "Taskforce Enterprise",
            "capabilities": [
                "admin.tenants",
                "admin.users",
                "admin.audit",
                "agents.catalog",
                "agents.approvals",
            ],
            "npm_package": "@taskforce/enterprise-ui",
            "min_ui_version": ">=0.1.0,<1.0.0",
        }


class _FakeBuggyPlugin:
    """Plugin whose `get_ui_manifest` raises — must not crash the endpoint."""

    name = "broken"
    version = "0.0.1"

    def get_middleware(self):
        return []

    def get_routers(self):
        return []

    def get_ui_manifest(self):
        raise RuntimeError("simulated plugin bug")


def _register(registry: PluginRegistry, name: str, instance) -> None:
    info = PluginInfo(name=name, entry_point=f"{name}:fake")
    info.plugin_class = instance.__class__
    info.instance = instance
    info.initialized = True
    registry.plugins[name] = info


@pytest.fixture
def isolated_registry(monkeypatch):
    fresh = PluginRegistry()
    monkeypatch.setattr(plugin_loader, "_plugin_registry", fresh)
    yield fresh


@pytest.fixture
def client(isolated_registry):
    app = create_app()
    return TestClient(app)


def test_manifest_pipeline_with_fake_enterprise_plugin(isolated_registry, client):
    """Full-stack happy path mirroring real-world enterprise install."""
    _register(isolated_registry, "enterprise", _FakeEnterprisePlugin())

    response = client.get("/api/v1/ui/manifest")
    assert response.status_code == 200
    body = response.json()

    assert "server_version" in body
    assert len(body["plugins"]) == 1

    plugin = body["plugins"][0]
    assert plugin["id"] == "enterprise"
    assert plugin["display_name"] == "Taskforce Enterprise"
    assert set(plugin["capabilities"]) == {
        "admin.tenants",
        "admin.users",
        "admin.audit",
        "agents.catalog",
        "agents.approvals",
    }
    assert plugin["npm_package"] == "@taskforce/enterprise-ui"
    assert plugin["min_ui_version"] == ">=0.1.0,<1.0.0"


def test_manifest_endpoint_isolates_buggy_plugins(isolated_registry, client):
    """One broken plugin must not take down manifest collection."""
    _register(isolated_registry, "broken", _FakeBuggyPlugin())
    _register(isolated_registry, "enterprise", _FakeEnterprisePlugin())

    response = client.get("/api/v1/ui/manifest")
    assert response.status_code == 200
    body = response.json()

    plugin_ids = [p["id"] for p in body["plugins"]]
    assert plugin_ids == ["enterprise"]


def test_manifest_endpoint_response_validates_with_extra_fields(isolated_registry, client):
    """A plugin returning unexpected fields must not crash Pydantic."""

    class _Verbose:
        name = "verbose"
        version = "1.0.0"

        def get_middleware(self):
            return []

        def get_routers(self):
            return []

        def get_ui_manifest(self):
            return {
                "id": "verbose",
                "capabilities": ["x"],
                "extra_field": "ignored",
                "another_extra": {"nested": True},
            }

    _register(isolated_registry, "verbose", _Verbose())

    response = client.get("/api/v1/ui/manifest")
    assert response.status_code == 200
    body = response.json()
    plugin = body["plugins"][0]
    assert plugin["id"] == "verbose"
    # Optional fields default appropriately
    assert plugin["display_name"] == ""
    assert plugin["capabilities"] == ["x"]


def test_manifest_endpoint_independent_of_health(isolated_registry, client):
    """Smoke: existing health endpoint still works alongside the new route."""
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
