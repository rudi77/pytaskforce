"""Phase 2 — generic /api/v1/events/{source_name} route."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taskforce.api.dependencies import (
    register_active_event_source,
    unregister_active_event_source,
)
from taskforce.api.routes import events
from taskforce.core.domain.agent_event import AgentEvent, AgentEventType
from taskforce.infrastructure.event_sources.github_webhook_source import (
    GitHubWebhookEventSource,
)


@pytest.fixture()
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(events.router, prefix="/api/v1")
    return app


@pytest.fixture(autouse=True)
def _cleanup_sources():
    yield
    for name in ("github", "test", "non-webhook", "ghbroken"):
        unregister_active_event_source(name)


class _MinimalSource:
    """Implements ``WebhookCapableEventSource`` without subclassing."""

    source_name = "test"
    is_running = True

    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], dict[str, str]]] = []

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def handle_inbound(
        self, payload: dict[str, Any], headers: dict[str, str] | None = None
    ) -> AgentEvent:
        self.calls.append((payload, dict(headers or {})))
        return AgentEvent(
            source=self.source_name,
            event_type=AgentEventType.WEBHOOK_RECEIVED,
            payload=payload,
        )


@pytest.mark.spec("events-scheduler.webhook_unknown_source_returns_404")
def test_unknown_source_returns_404(app: FastAPI) -> None:
    response = TestClient(app).post("/api/v1/events/missing", json={"x": 1})
    assert response.status_code == 404


@pytest.mark.spec("events-scheduler.webhook_non_json_returns_415")
def test_invalid_json_returns_415(app: FastAPI) -> None:
    register_active_event_source("test", _MinimalSource())
    response = TestClient(app).post(
        "/api/v1/events/test",
        data="not-json",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 415


def test_minimal_source_receives_payload(app: FastAPI) -> None:
    src = _MinimalSource()
    register_active_event_source("test", src)
    response = TestClient(app).post("/api/v1/events/test", json={"x": 1})
    assert response.status_code == 202
    assert src.calls == [({"x": 1}, src.calls[0][1])]
    body = response.json()
    assert body["status"] == "accepted"


@pytest.mark.spec("events-scheduler.webhook_invalid_signature_returns_401")
def test_github_webhook_invalid_signature_returns_401(app: FastAPI) -> None:
    register_active_event_source(
        "github",
        GitHubWebhookEventSource(secret="topsecret"),
    )
    payload = {"action": "opened"}
    response = TestClient(app).post(
        "/api/v1/events/github",
        json=payload,
        headers={
            "X-Hub-Signature-256": "sha256=deadbeef",
            "X-GitHub-Event": "pull_request",
        },
    )
    assert response.status_code == 401


class _NonCapableSource:
    """A registered source that cannot accept inbound HTTP — no handle_inbound."""

    source_name = "non-webhook"
    is_running = True

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


@pytest.mark.spec("events-scheduler.webhook_non_capable_source_returns_400")
def test_non_capable_source_returns_400(app: FastAPI) -> None:
    """A source that exists but has no handle_inbound returns HTTP 400."""
    register_active_event_source("non-webhook", _NonCapableSource())
    response = TestClient(app).post("/api/v1/events/non-webhook", json={"x": 1})
    assert response.status_code == 400


def test_github_webhook_valid_signature_returns_202(app: FastAPI) -> None:
    secret = "topsecret"
    register_active_event_source(
        "github",
        GitHubWebhookEventSource(secret=secret),
    )
    payload = {
        "action": "opened",
        "pull_request": {"number": 1, "title": "test"},
        "repository": {"full_name": "x/y"},
        "sender": {"login": "alice"},
    }
    body = json.dumps(payload).encode("utf-8")
    signature = "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()

    response = TestClient(app).post(
        "/api/v1/events/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature,
            "X-GitHub-Event": "pull_request",
        },
    )
    assert response.status_code == 202
    assert response.json()["source"] == "github"
