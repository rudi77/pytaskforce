"""Phase 1 (ADR-019) — REST endpoints for queue introspection and cancel."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taskforce.api.dependencies import (
    get_persistent_agent_service,
    set_persistent_agent_service,
)
from taskforce.api.routes import missions


@pytest.fixture()
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(missions.router, prefix="/api/v1")
    return app


@pytest.fixture(autouse=True)
def _cleanup_service():
    yield
    set_persistent_agent_service(None)


class _StubService:
    """Just enough surface for the routes to exercise."""

    def __init__(
        self,
        missions: list[dict[str, Any]] | None = None,
        cancel_result: dict[str, Any] | None = None,
    ) -> None:
        self._missions = missions or []
        self._cancel_result = cancel_result or {
            "request_id": "req-1",
            "session_id": None,
            "status": "cancelled",
        }
        self.cancel_calls: list[str] = []

    def list_missions(self) -> list[dict[str, Any]]:
        return list(self._missions)

    def cancel_request(self, request_id: str) -> dict[str, Any]:
        self.cancel_calls.append(request_id)
        return {**self._cancel_result, "request_id": request_id}


def test_list_missions_returns_503_when_no_service(app: FastAPI) -> None:
    set_persistent_agent_service(None)
    response = TestClient(app).get("/api/v1/missions")
    assert response.status_code == 503


def test_list_missions_returns_records(app: FastAPI) -> None:
    set_persistent_agent_service(
        _StubService(
            missions=[
                {
                    "request_id": "req-1",
                    "session_id": "session-1",
                    "channel": "rest",
                    "priority": 5,
                    "conversation_id": None,
                    "status": "queued",
                    "message_preview": "hello",
                }
            ]
        )
    )
    response = TestClient(app).get("/api/v1/missions")
    assert response.status_code == 200
    body = response.json()
    assert len(body["missions"]) == 1
    assert body["missions"][0]["request_id"] == "req-1"
    assert body["missions"][0]["status"] == "queued"


def test_cancel_returns_202_for_known_request(app: FastAPI) -> None:
    service = _StubService(
        cancel_result={
            "request_id": "req-1",
            "session_id": "session-1",
            "status": "interrupt_requested",
        }
    )
    set_persistent_agent_service(service)
    response = TestClient(app).post("/api/v1/missions/req-1/cancel")
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "interrupt_requested"
    assert body["session_id"] == "session-1"
    assert service.cancel_calls == ["req-1"]


def test_cancel_returns_404_for_unknown_request(app: FastAPI) -> None:
    set_persistent_agent_service(
        _StubService(
            cancel_result={
                "request_id": "req-1",
                "session_id": None,
                "status": "not_found",
            }
        )
    )
    response = TestClient(app).post("/api/v1/missions/req-1/cancel")
    assert response.status_code == 404


def test_get_persistent_agent_service_round_trip() -> None:
    """Sanity: register/unregister flips ``get_persistent_agent_service``."""
    assert get_persistent_agent_service() is None
    sentinel = object()
    set_persistent_agent_service(sentinel)
    assert get_persistent_agent_service() is sentinel
    set_persistent_agent_service(None)
    assert get_persistent_agent_service() is None
