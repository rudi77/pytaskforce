"""Spec-coverage tests for the OAuth connections REST routes.

Mounts ``oauth.router`` on a bare ``FastAPI()`` app (no ``create_app()``)
so the enterprise auth middleware is not involved and the tests are
deterministic locally and in CI.

Spec: docs/spec/auth.md — tests tagged @pytest.mark.spec("auth.*").
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from taskforce.api.dependencies import get_auth_manager
from taskforce.api.exception_handlers import taskforce_http_exception_handler
from taskforce.api.routes import oauth as oauth_route


def _build_app(*, auth_manager, user_permissions: set[str] | None = None) -> FastAPI:
    """Mount the oauth router; optionally inject a permissioned user."""
    app = FastAPI()
    app.add_exception_handler(HTTPException, taskforce_http_exception_handler)
    app.include_router(oauth_route.router, prefix="/api/v1")
    app.dependency_overrides[get_auth_manager] = lambda: auth_manager

    if user_permissions is not None:
        @app.middleware("http")
        async def _inject_user(request, call_next):  # type: ignore[no-untyped-def]
            request.state.user = SimpleNamespace(permissions=user_permissions)
            return await call_next(request)

    return app


@pytest.mark.spec("auth.oauth_connections_requires_tenant_manage")
def test_oauth_connections_requires_tenant_manage() -> None:
    """A caller without ``tenant:manage`` is rejected with 403."""
    app = _build_app(auth_manager=AsyncMock(), user_permissions=set())
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/v1/oauth/connections")
    assert response.status_code == 403

    # And a caller WITH the permission is allowed through.
    app_ok = _build_app(
        auth_manager=None, user_permissions={"tenant:manage"}
    )
    ok = TestClient(app_ok, raise_server_exceptions=False).get(
        "/api/v1/oauth/connections"
    )
    assert ok.status_code == 200


@pytest.mark.spec("auth.oauth_revoke_without_auth_manager_returns_503")
@pytest.mark.spec("settings-store.oauth_revoke_without_auth_manager_returns_503")
def test_oauth_revoke_without_auth_manager_returns_503() -> None:
    """DELETE on a connection returns 503 when no AuthManager is configured."""
    app = _build_app(auth_manager=None)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.delete("/api/v1/oauth/connections/google")
    assert response.status_code == 503
    assert response.json()["code"] == "auth_manager_unavailable"


@pytest.mark.spec("auth.oauth_connections_reports_unreadable_token_row")
def test_oauth_connections_reports_unreadable_token_row(monkeypatch) -> None:
    """A corrupt token row is listed with status='unreadable', not a 500."""
    store = AsyncMock()
    store.list_providers = AsyncMock(return_value=["google"])
    store.load_token = AsyncMock(return_value={"provider": "google"})
    auth_manager = SimpleNamespace(_token_store=store)

    # Simulate a token row the summariser cannot parse.
    def _boom(_provider, _raw):
        raise ValueError("corrupt token row")

    monkeypatch.setattr(oauth_route, "_summarise", _boom)

    app = _build_app(auth_manager=auth_manager)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/v1/oauth/connections")
    assert response.status_code == 200
    body = response.json()
    assert body["auth_manager_available"] is True
    assert len(body["connections"]) == 1
    assert body["connections"][0]["provider"] == "google"
    assert body["connections"][0]["status"] == "unreadable"
