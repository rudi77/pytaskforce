"""Tests for the Phase-6 ACP peer CRUD + test endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from taskforce.api.server import create_app


@pytest.fixture
def acp_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "acp"
    target.mkdir()
    monkeypatch.setenv("TASKFORCE_ACP_WORK_DIR", str(target))
    return target


@pytest.fixture
def client(acp_dir: Path) -> TestClient:
    return TestClient(create_app())


def _payload(**overrides: Any) -> dict[str, Any]:
    base = {
        "name": "remote-butler",
        "base_url": "http://remote.local:8800",
        "agent": "butler",
        "description": "Remote butler",
        "auth": {"type": "none"},
    }
    base.update(overrides)
    return base


def test_create_peer_persists_to_json(client: TestClient, acp_dir: Path) -> None:
    response = client.post("/api/v1/acp/peers", json=_payload())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "remote-butler"
    assert body["auth_type"] == "none"
    json_path = acp_dir / "acp_peers.json"
    assert json_path.is_file()


def test_create_peer_conflict(client: TestClient) -> None:
    first = client.post("/api/v1/acp/peers", json=_payload())
    assert first.status_code == 201
    second = client.post("/api/v1/acp/peers", json=_payload())
    assert second.status_code == 409
    assert second.json()["code"] == "peer_exists"


def test_list_returns_created_peer(client: TestClient) -> None:
    client.post(
        "/api/v1/acp/peers",
        json=_payload(name="alpha", base_url="http://a"),
    )
    client.post(
        "/api/v1/acp/peers",
        json=_payload(name="beta", base_url="http://b"),
    )
    response = client.get("/api/v1/acp/peers")
    assert response.status_code == 200
    names = {p["name"] for p in response.json()}
    assert names == {"alpha", "beta"}


def test_update_peer_replaces_fields(client: TestClient) -> None:
    client.post("/api/v1/acp/peers", json=_payload())
    response = client.put(
        "/api/v1/acp/peers/remote-butler",
        json={
            "base_url": "http://new.local:9000",
            "agent": "butler-v2",
            "description": "updated",
            "auth": {"type": "bearer", "token_env": "REMOTE_TOKEN"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["base_url"] == "http://new.local:9000"
    assert body["agent"] == "butler-v2"
    assert body["auth_type"] == "bearer"
    assert body["token_env"] == "REMOTE_TOKEN"


def test_delete_peer(client: TestClient) -> None:
    client.post("/api/v1/acp/peers", json=_payload())
    delete = client.delete("/api/v1/acp/peers/remote-butler")
    assert delete.status_code == 204
    after = client.get("/api/v1/acp/peers")
    assert after.json() == []


def test_delete_unknown_returns_404(client: TestClient) -> None:
    response = client.delete("/api/v1/acp/peers/never-existed")
    assert response.status_code == 404
    assert response.json()["code"] == "peer_not_found"


def test_test_peer_uses_ping(client: TestClient) -> None:
    client.post("/api/v1/acp/peers", json=_payload())
    fake = AsyncMock(
        return_value={
            "ok": True,
            "status_code": 200,
            "latency_ms": 42,
            "agent": "butler",
            "base_url": "http://remote.local:8800",
        }
    )
    with patch("taskforce.api.routes.acp.ping_peer", new=fake):
        response = client.post("/api/v1/acp/peers/remote-butler/test")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["status_code"] == 200
    assert body["latency_ms"] == 42
    fake.assert_awaited_once()


def test_test_peer_unknown_returns_404(client: TestClient) -> None:
    response = client.post("/api/v1/acp/peers/missing/test")
    assert response.status_code == 404
    assert response.json()["code"] == "peer_not_found"
