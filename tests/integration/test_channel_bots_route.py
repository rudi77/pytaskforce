"""Integration tests for /api/v1/settings/channels/bots CRUD.

Covers:
- Anonymous single-user mode (no auth middleware) — all operations
  succeed (require_permission is a no-op without ``request.state.user``).
- Owner-aware authorization: legacy framework-only mode is permissive
  (no middleware attaches a user → all operations are admin-grade).
- Round-trip via the settings store using a real file-based store.
- Token masking returns the full token to the owner / admin only —
  but without an auth middleware the route treats everyone as admin
  (full token returned). The masking semantics with a real auth
  middleware live in enterprise plugin tests.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from taskforce.api.dependencies import get_settings_store  # noqa: E402
from taskforce.api.server import create_app  # noqa: E402
from taskforce.infrastructure.persistence.file_settings_store import (  # noqa: E402
    FileSettingsStore,
)


@pytest.fixture
def client(tmp_path):
    store = FileSettingsStore(work_dir=tmp_path, key=Fernet.generate_key())
    app = create_app()
    app.dependency_overrides[get_settings_store] = lambda: store
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_list_empty_when_no_bots(client):
    response = client.get("/api/v1/settings/channels/bots")
    assert response.status_code == 200
    assert response.json() == {"bots": []}


def test_create_and_list_personal_bot(client):
    payload = {
        "id": "my-butler",
        "channel_type": "telegram",
        "bot_token": "123:abc",
        "owner_kind": "user",
        "owner_user_id": "user-1",
        "default_agent": "butler",
        "pairing_mode": None,  # auto-default to implicit
        "enabled": True,
    }
    create = client.post("/api/v1/settings/channels/bots", json=payload)
    assert create.status_code == 201
    body = create.json()
    assert body["id"] == "my-butler"
    assert body["pairing_mode"] == "implicit"  # auto-defaulted

    listing = client.get("/api/v1/settings/channels/bots").json()
    assert len(listing["bots"]) == 1
    assert listing["bots"][0]["id"] == "my-butler"


def test_duplicate_id_conflicts(client):
    payload = {
        "id": "dup",
        "channel_type": "telegram",
        "bot_token": "t",
        "owner_kind": "user",
        "owner_user_id": "user-1",
    }
    assert client.post("/api/v1/settings/channels/bots", json=payload).status_code == 201
    resp = client.post("/api/v1/settings/channels/bots", json=payload)
    assert resp.status_code == 409


def test_invalid_id_rejected(client):
    resp = client.post(
        "/api/v1/settings/channels/bots",
        json={
            "id": "Bad ID!",
            "channel_type": "telegram",
            "bot_token": "t",
            "owner_kind": "user",
            "owner_user_id": "user-1",
        },
    )
    assert resp.status_code == 400


def test_update_bot(client):
    payload = {
        "id": "b1",
        "channel_type": "telegram",
        "bot_token": "old",
        "owner_kind": "user",
        "owner_user_id": "user-1",
    }
    client.post("/api/v1/settings/channels/bots", json=payload)
    payload["bot_token"] = "new"
    resp = client.patch("/api/v1/settings/channels/bots/b1", json=payload)
    assert resp.status_code == 200
    assert resp.json()["bot_token"] == "new"


def test_update_path_id_mismatch(client):
    client.post(
        "/api/v1/settings/channels/bots",
        json={
            "id": "b1",
            "channel_type": "telegram",
            "bot_token": "t",
            "owner_kind": "user",
            "owner_user_id": "user-1",
        },
    )
    resp = client.patch(
        "/api/v1/settings/channels/bots/b1",
        json={
            "id": "b2",
            "channel_type": "telegram",
            "bot_token": "t",
            "owner_kind": "user",
            "owner_user_id": "user-1",
        },
    )
    assert resp.status_code == 400


def test_delete_is_idempotent(client):
    # Delete-before-create: idempotent
    assert client.delete("/api/v1/settings/channels/bots/never").status_code == 204
    client.post(
        "/api/v1/settings/channels/bots",
        json={
            "id": "b1",
            "channel_type": "telegram",
            "bot_token": "t",
            "owner_kind": "user",
            "owner_user_id": "user-1",
        },
    )
    assert client.delete("/api/v1/settings/channels/bots/b1").status_code == 204
    # Delete again is still 204
    assert client.delete("/api/v1/settings/channels/bots/b1").status_code == 204
    assert client.get("/api/v1/settings/channels/bots").json() == {"bots": []}


def test_legacy_section_visible_via_list(client, tmp_path):
    """A pre-existing flat CHANNELS section is exposed as a 'legacy-*' bot."""
    # Write a legacy-shape section directly to the store
    store = FileSettingsStore(work_dir=tmp_path / "legacy", key=Fernet.generate_key())
    store.put("channels", {"telegram": {"bot_token": "legacy-t"}})

    app = create_app()
    app.dependency_overrides[get_settings_store] = lambda: store
    try:
        c = TestClient(app)
        body = c.get("/api/v1/settings/channels/bots").json()
        ids = [b["id"] for b in body["bots"]]
        assert "legacy-telegram" in ids
    finally:
        app.dependency_overrides.clear()
