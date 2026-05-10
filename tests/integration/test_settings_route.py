"""Integration tests for ``/api/v1/settings``.

The framework ships ``require_permission`` as a no-op when no auth
middleware is attached (single-tenant default), so the TestClient
exercises the route handlers without needing a fake user. The tests
therefore focus on the route's contract: round-trip, list, 404 on
missing, delete, replacement semantics.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from taskforce.api.dependencies import get_settings_store  # noqa: E402
from taskforce.api.server import create_app  # noqa: E402
from taskforce.infrastructure.persistence.file_settings_store import (  # noqa: E402
    FileSettingsStore,
)


@pytest.fixture
def client(tmp_path):
    from cryptography.fernet import Fernet

    store = FileSettingsStore(work_dir=tmp_path, key=Fernet.generate_key())
    app = create_app()
    app.dependency_overrides[get_settings_store] = lambda: store
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_get_missing_section_returns_404(client):
    response = client.get("/api/v1/settings/llm_providers")
    assert response.status_code == 404


def test_put_then_get_round_trip(client):
    payload = {"data": {"openai": {"api_key": "sk-test"}}}
    put_response = client.put("/api/v1/settings/llm_providers", json=payload)
    assert put_response.status_code == 200
    body = put_response.json()
    assert body["name"] == "llm_providers"
    assert body["data"] == payload["data"]
    assert body["is_known"] is True

    get_response = client.get("/api/v1/settings/llm_providers")
    assert get_response.status_code == 200
    assert get_response.json()["data"] == payload["data"]


def test_put_unknown_section_marks_is_known_false(client):
    response = client.put(
        "/api/v1/settings/operator_custom",
        json={"data": {"foo": "bar"}},
    )
    assert response.status_code == 200
    assert response.json()["is_known"] is False


def test_list_returns_present_sections_and_catalogue(client):
    client.put("/api/v1/settings/llm_providers", json={"data": {"openai": {}}})
    client.put("/api/v1/settings/channels", json={"data": {"telegram": {}}})

    response = client.get("/api/v1/settings")
    assert response.status_code == 200
    body = response.json()
    assert set(body["sections"]) == {"llm_providers", "channels"}
    assert "llm_providers" in body["known_sections"]
    assert "channels" in body["known_sections"]


def test_put_replaces_section(client):
    client.put(
        "/api/v1/settings/channels",
        json={"data": {"telegram": "old", "teams": "kept"}},
    )
    client.put(
        "/api/v1/settings/channels",
        json={"data": {"telegram": "new"}},
    )
    body = client.get("/api/v1/settings/channels").json()
    assert body["data"] == {"telegram": "new"}


def test_delete_removes_section(client):
    client.put("/api/v1/settings/channels", json={"data": {"telegram": {}}})
    response = client.delete("/api/v1/settings/channels")
    assert response.status_code == 204
    assert client.get("/api/v1/settings/channels").status_code == 404


def test_delete_missing_section_is_idempotent(client):
    response = client.delete("/api/v1/settings/never_existed")
    assert response.status_code == 204
