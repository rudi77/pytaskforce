"""Spec-coverage tests for the Settings Store REST routes.

Mounts ``settings.router`` on a bare ``FastAPI()`` app (no ``create_app()``)
so the enterprise auth middleware is not involved and the tests are
deterministic locally and in CI. A small per-test middleware injects a
``request.state.user`` when a test needs to exercise the permission gate.

Spec: docs/spec/settings-store.md — tests tagged @pytest.mark.spec("settings-store.*").
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi")

from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from taskforce.api.dependencies import get_settings_store
from taskforce.api.exception_handlers import taskforce_http_exception_handler
from taskforce.api.routes import settings as settings_route
from taskforce.core.domain.settings import (
    CHANNELS,
    BotConfig,
    BotOwnerKind,
    bots_to_section,
)
from taskforce.infrastructure.persistence.file_settings_store import FileSettingsStore


def _build_client(
    *,
    store: FileSettingsStore,
    user: SimpleNamespace | None = None,
) -> TestClient:
    """Mount the settings router on a bare app, optionally injecting a user."""
    app = FastAPI()
    app.add_exception_handler(HTTPException, taskforce_http_exception_handler)
    app.include_router(settings_route.router, prefix="/api/v1")
    app.dependency_overrides[get_settings_store] = lambda: store

    if user is not None:
        @app.middleware("http")
        async def _inject_user(request, call_next):  # type: ignore[no-untyped-def]
            request.state.user = user
            return await call_next(request)

    return TestClient(app, raise_server_exceptions=False)


def _store(tmp_path) -> FileSettingsStore:
    return FileSettingsStore(work_dir=tmp_path, key=Fernet.generate_key())


# ---------------------------------------------------------------------------
# Section CRUD
# ---------------------------------------------------------------------------


@pytest.mark.spec("settings-store.get_unknown_section_returns_404")
def test_get_unknown_section_returns_404(tmp_path) -> None:
    """GET on a section that was never written returns 404."""
    client = _build_client(store=_store(tmp_path))
    response = client.get("/api/v1/settings/never_written_section")
    assert response.status_code == 404


@pytest.mark.spec("settings-store.delete_unknown_section_is_204")
def test_delete_unknown_section_is_204(tmp_path) -> None:
    """DELETE on a section that was never written is an idempotent 204."""
    client = _build_client(store=_store(tmp_path))
    response = client.delete("/api/v1/settings/never_written_section")
    assert response.status_code == 204


@pytest.mark.spec("settings-store.put_channels_clears_gateway_cache")
def test_put_channels_clears_gateway_cache(tmp_path, monkeypatch) -> None:
    """Writing the channels section drops the cached gateway + components."""
    gateway_mock = MagicMock()
    components_mock = MagicMock()
    monkeypatch.setattr("taskforce.api.dependencies.get_gateway", gateway_mock)
    monkeypatch.setattr(
        "taskforce.api.dependencies.get_gateway_components", components_mock
    )

    client = _build_client(store=_store(tmp_path))
    response = client.put("/api/v1/settings/channels", json={"data": {}})
    assert response.status_code == 200

    gateway_mock.cache_clear.assert_called_once()
    components_mock.cache_clear.assert_called_once()


@pytest.mark.spec("settings-store.all_routes_require_tenant_manage")
def test_all_routes_require_tenant_manage(tmp_path) -> None:
    """A caller without ``tenant:manage`` is rejected from the settings list."""
    non_admin = SimpleNamespace(user_id="alice", permissions=set())
    client = _build_client(store=_store(tmp_path), user=non_admin)

    response = client.get("/api/v1/settings")
    assert response.status_code == 403

    # And an admin caller is allowed through.
    admin = SimpleNamespace(user_id="root", permissions={"tenant:manage"})
    ok = _build_client(store=_store(tmp_path), user=admin).get("/api/v1/settings")
    assert ok.status_code == 200


# ---------------------------------------------------------------------------
# Channel bots CRUD
# ---------------------------------------------------------------------------


def _seed_bots(store: FileSettingsStore, bots: list[BotConfig]) -> None:
    store.put(CHANNELS, bots_to_section(bots))


@pytest.mark.spec("settings-store.bot_list_masks_other_users_tokens_for_non_admin")
def test_bot_list_masks_other_users_tokens_for_non_admin(tmp_path) -> None:
    """A non-admin sees their own bot token, but masked tokens for bots they
    do not own."""
    store = _store(tmp_path)
    _seed_bots(
        store,
        [
            BotConfig(
                id="alice-bot",
                channel_type="telegram",
                bot_token="SECRET-ALICE",
                owner_kind=BotOwnerKind.USER,
                owner_user_id="alice",
            ),
            BotConfig(
                id="shared-bot",
                channel_type="telegram",
                bot_token="SECRET-TENANT",
                owner_kind=BotOwnerKind.TENANT,
            ),
        ],
    )
    alice = SimpleNamespace(user_id="alice", permissions=set())
    client = _build_client(store=store, user=alice)

    response = client.get("/api/v1/settings/channels/bots")
    assert response.status_code == 200
    bots = {b["id"]: b for b in response.json()["bots"]}

    # Alice owns alice-bot → token visible.
    assert bots["alice-bot"]["bot_token"] == "SECRET-ALICE"
    # The tenant-shared bot is not hers → token masked.
    assert bots["shared-bot"]["bot_token"] != "SECRET-TENANT"


@pytest.mark.spec("settings-store.bot_create_duplicate_id_returns_409")
def test_bot_create_duplicate_id_returns_409(tmp_path) -> None:
    """Creating a bot whose id already exists in the tenant returns 409."""
    admin = SimpleNamespace(user_id="root", permissions={"tenant:manage"})
    client = _build_client(store=_store(tmp_path), user=admin)

    payload = {
        "id": "dup-bot",
        "channel_type": "telegram",
        "bot_token": "tok",
        "owner_kind": "tenant",
    }
    first = client.post("/api/v1/settings/channels/bots", json=payload)
    assert first.status_code == 201

    second = client.post("/api/v1/settings/channels/bots", json=payload)
    assert second.status_code == 409
    assert second.json()["code"] == "bot_id_exists"


@pytest.mark.spec("settings-store.bot_create_tenant_owned_without_admin_returns_403")
def test_bot_create_tenant_owned_without_admin_returns_403(tmp_path) -> None:
    """A non-admin cannot create a tenant-owned bot."""
    non_admin = SimpleNamespace(user_id="alice", permissions=set())
    client = _build_client(store=_store(tmp_path), user=non_admin)

    response = client.post(
        "/api/v1/settings/channels/bots",
        json={
            "id": "tenant-bot",
            "channel_type": "telegram",
            "bot_token": "tok",
            "owner_kind": "tenant",
        },
    )
    assert response.status_code == 403


@pytest.mark.spec("settings-store.bot_crud_triggers_poller_reconcile")
def test_bot_crud_triggers_poller_reconcile(tmp_path, monkeypatch) -> None:
    """A successful bot create reconciles the BotPollerManager."""
    manager = MagicMock()
    manager.reconcile = AsyncMock()
    monkeypatch.setattr(
        "taskforce.api.dependencies.get_bot_poller_manager", lambda: manager
    )

    admin = SimpleNamespace(user_id="root", permissions={"tenant:manage"})
    client = _build_client(store=_store(tmp_path), user=admin)

    response = client.post(
        "/api/v1/settings/channels/bots",
        json={
            "id": "new-bot",
            "channel_type": "telegram",
            "bot_token": "tok",
            "owner_kind": "tenant",
        },
    )
    assert response.status_code == 201
    manager.reconcile.assert_awaited_once()
