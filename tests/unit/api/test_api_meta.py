"""Cross-cutting REST transport contract — error envelope, health probes,
SPA mount, CORS, OpenAPI.

These mount routers / install handlers on bare ``FastAPI()`` apps (no
``create_app()``) wherever possible so the enterprise auth middleware is
not involved and the tests are deterministic locally and in CI. The CORS
test constructs ``create_app()`` but inspects middleware without issuing
a request.

Spec: docs/spec/api.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from taskforce.api.errors import http_exception
from taskforce.api.exception_handlers import taskforce_http_exception_handler
from taskforce.api.routes import health as health_route


# ---------------------------------------------------------------------------
# Error envelope + exception handler
# ---------------------------------------------------------------------------


def _app_with_handler() -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(HTTPException, taskforce_http_exception_handler)

    @app.get("/tagged")
    def _tagged():
        raise http_exception(
            status_code=404, code="not_found", message="thing is missing"
        )

    @app.get("/plain")
    def _plain():
        raise HTTPException(status_code=404, detail="plain detail")

    return app


@pytest.mark.spec("api.error_envelope_has_code_and_message")
def test_error_envelope_has_code_and_message() -> None:
    """A taskforce-thrown error serialises the {code, message, detail} envelope."""
    client = TestClient(_app_with_handler(), raise_server_exceptions=False)
    response = client.get("/tagged")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "not_found"
    assert body["message"] == "thing is missing"
    assert body["detail"] == "thing is missing"


@pytest.mark.spec("api.error_envelope_marked_with_x_taskforce_error_header")
@pytest.mark.xfail(
    reason="#428 — taskforce_http_exception_handler drops the X-Taskforce-Error "
    "response header (consumed for the decision, not propagated to the response)",
    strict=True,
)
def test_error_envelope_marked_with_x_taskforce_error_header() -> None:
    """A taskforce error response carries the X-Taskforce-Error: 1 header so
    middleware can distinguish it from FastAPI defaults."""
    client = TestClient(_app_with_handler(), raise_server_exceptions=False)
    response = client.get("/tagged")

    assert response.headers.get("X-Taskforce-Error") == "1"


@pytest.mark.spec("api.untagged_http_exception_falls_through_to_fastapi_default")
def test_untagged_http_exception_falls_through_to_fastapi_default() -> None:
    """A plain HTTPException is not rewritten — it keeps FastAPI's default
    {detail} shape, not the taskforce envelope."""
    client = TestClient(_app_with_handler(), raise_server_exceptions=False)
    response = client.get("/plain")

    assert response.status_code == 404
    body = response.json()
    assert body == {"detail": "plain detail"}
    assert "code" not in body


# ---------------------------------------------------------------------------
# Health probes
# ---------------------------------------------------------------------------


@pytest.mark.spec("api.health_returns_200_with_version_and_default_profile")
def test_health_returns_200_with_version_and_default_profile() -> None:
    app = FastAPI()
    app.include_router(health_route.router)
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["version"]
    assert body["default_profile"]


@pytest.mark.spec("api.health_ready_returns_503_when_tool_registry_unavailable")
def test_health_ready_returns_503_when_tool_registry_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the tool registry cannot be built, /health/ready returns 503 with
    the `not_ready` error code."""

    def _boom():
        raise RuntimeError("registry build failed")

    monkeypatch.setattr(
        "taskforce.application.tool_registry.get_tool_registry", _boom
    )

    app = FastAPI()
    app.add_exception_handler(HTTPException, taskforce_http_exception_handler)
    app.include_router(health_route.router)
    response = TestClient(app, raise_server_exceptions=False).get("/health/ready")

    assert response.status_code == 503
    assert response.json()["code"] == "not_ready"


# ---------------------------------------------------------------------------
# OpenAPI
# ---------------------------------------------------------------------------


@pytest.mark.spec("api.openapi_schema_served_at_openapi_json")
def test_openapi_schema_served_at_openapi_json() -> None:
    """The app serves a valid OpenAPI document at /openapi.json covering its
    mounted routes."""
    app = FastAPI(title="probe")
    app.include_router(health_route.router)
    response = TestClient(app).get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["openapi"].startswith("3.")
    assert "/health" in schema["paths"]


# ---------------------------------------------------------------------------
# SPA catch-all
# ---------------------------------------------------------------------------


@pytest.mark.spec("api.spa_catchall_does_not_shadow_api_routes")
def test_spa_catchall_does_not_shadow_api_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The SPA catch-all serves index.html for unknown UI paths but never
    shadows /api/ — an unknown API path 404s instead of returning the SPA."""
    from taskforce.api.server import _mount_ui

    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<!doctype html><title>SPA</title>", "utf-8")
    monkeypatch.setenv("TASKFORCE_UI_DIR", str(ui_dir))

    app = FastAPI()

    @app.get("/api/v1/known")
    def _known():
        return {"ok": True}

    _mount_ui(app)
    client = TestClient(app)

    # Known API route still wins.
    assert client.get("/api/v1/known").json() == {"ok": True}
    # Unknown API path → 404, NOT the SPA index.html.
    unknown_api = client.get("/api/v1/does-not-exist")
    assert unknown_api.status_code == 404
    assert "<title>SPA</title>" not in unknown_api.text
    # Unknown non-API path → SPA fallback.
    spa = client.get("/some/client-side/route")
    assert spa.status_code == 200
    assert "<title>SPA</title>" in spa.text


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------


def _cors_allow_credentials(app: FastAPI) -> bool:
    for mw in app.user_middleware:
        if mw.cls is CORSMiddleware:
            return bool(mw.kwargs.get("allow_credentials"))
    raise AssertionError("CORSMiddleware is not installed on the app")


@pytest.mark.spec("api.cors_wildcard_disables_allow_credentials")
def test_cors_wildcard_disables_allow_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the wildcard origin default, allow_credentials must be False;
    an explicit origin list re-enables it."""
    from taskforce.api.server import create_app

    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert _cors_allow_credentials(create_app()) is False

    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    assert _cors_allow_credentials(create_app()) is True
