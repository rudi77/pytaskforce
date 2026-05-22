"""Spec-coverage tests for the Communication Gateway HTTP routes.

These mount ``gateway.router`` on a bare ``FastAPI()`` app (no
``create_app()``) so the enterprise auth middleware is not involved and
the tests are deterministic locally and in CI.

Spec: docs/spec/gateway.md — tests tagged @pytest.mark.spec("gateway.*").
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from taskforce.api.dependencies import (
    get_channel_link_registry,
    get_gateway,
    get_inbound_adapters,
)
from taskforce.api.exception_handlers import taskforce_http_exception_handler
from taskforce.api.routes import gateway as gateway_route
from taskforce.core.domain.gateway import GatewayResponse, NotificationResult
from taskforce.infrastructure.communication.channel_link_registry import (
    InMemoryChannelLinkRegistry,
)


def _mock_gateway() -> AsyncMock:
    """A CommunicationGateway stand-in with deterministic responses."""
    gw = AsyncMock()
    gw.handle_message = AsyncMock(
        return_value=GatewayResponse(
            session_id="sess-1",
            status="completed",
            reply="Hello!",
            history=[{"role": "user", "content": "Hi"}],
        )
    )
    gw.send_notification = AsyncMock(
        return_value=NotificationResult(
            success=True, channel="telegram", recipient_id="user-1", error=None
        )
    )
    gw.broadcast = AsyncMock(
        return_value=[
            NotificationResult(
                success=True, channel="telegram", recipient_id="u1", error=None
            ),
            NotificationResult(
                success=False, channel="telegram", recipient_id="u2", error="Not found"
            ),
            NotificationResult(
                success=True, channel="telegram", recipient_id="u3", error=None
            ),
        ]
    )
    # supported_channels returns an UNSORTED list to prove the route sorts it.
    gw.supported_channels = MagicMock(return_value=["telegram", "slack", "teams"])
    return gw


def _mock_adapter(*, signature_ok: bool = True, metadata: dict | None = None):
    """A channel InboundAdapter stand-in."""
    adapter = MagicMock()
    adapter.verify_signature = MagicMock(return_value=signature_ok)
    adapter.extract_message = MagicMock(
        return_value={
            "conversation_id": "conv-1",
            "message": "Webhook message",
            "sender_id": "sender-1",
            "metadata": metadata if metadata is not None else {},
        }
    )
    return adapter


def _build_client(
    *,
    gateway: AsyncMock | None = None,
    adapters: dict | None = None,
    link_registry: InMemoryChannelLinkRegistry | None = None,
) -> TestClient:
    """Mount the gateway router on a bare app with overridable dependencies."""
    app = FastAPI()
    app.add_exception_handler(HTTPException, taskforce_http_exception_handler)
    app.include_router(gateway_route.router, prefix="/api/v1")

    app.dependency_overrides[get_gateway] = lambda: gateway or _mock_gateway()
    app.dependency_overrides[get_inbound_adapters] = lambda: (
        adapters if adapters is not None else {"telegram": _mock_adapter()}
    )
    app.dependency_overrides[get_channel_link_registry] = lambda: (
        link_registry or InMemoryChannelLinkRegistry()
    )
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Webhook signature + routing
# ---------------------------------------------------------------------------


@pytest.mark.spec("gateway.webhook_invalid_signature_returns_401")
def test_webhook_invalid_signature_returns_401() -> None:
    """A failed channel signature verification returns 401; payload discarded."""
    client = _build_client(adapters={"telegram": _mock_adapter(signature_ok=False)})

    response = client.post(
        "/api/v1/gateway/telegram/webhook",
        json={"update_id": 1, "message": {"text": "Hi"}},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


@pytest.mark.spec("gateway.webhook_unknown_channel_returns_400")
def test_webhook_unknown_channel_returns_400() -> None:
    """A webhook for a channel with no registered adapter returns 400."""
    client = _build_client(adapters={"telegram": _mock_adapter()})

    response = client.post(
        "/api/v1/gateway/unknown_channel/webhook",
        json={"data": "test"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_request"


@pytest.mark.spec("gateway.webhook_telegram_attachments_downloaded")
def test_webhook_telegram_attachments_downloaded(monkeypatch) -> None:
    """Inbound Telegram attachment refs are auto-downloaded before agent run.

    The webhook handler resolves lightweight ``attachment_refs`` from the
    adapter metadata into full ``attachments`` via
    ``_download_telegram_attachments`` and passes them on the InboundMessage.
    """
    downloaded = [{"type": "image", "data_url": "data:image/png;base64,QUJD"}]

    async def _fake_download(refs):
        # Proves the refs from the adapter metadata reached the downloader.
        assert refs == [{"file_id": "f-1", "type": "image", "mime_type": "image/png"}]
        return downloaded

    monkeypatch.setattr(gateway_route, "_download_telegram_attachments", _fake_download)

    gw = _mock_gateway()
    adapter = _mock_adapter(
        metadata={
            "attachment_refs": [
                {"file_id": "f-1", "type": "image", "mime_type": "image/png"}
            ]
        }
    )
    client = _build_client(gateway=gw, adapters={"telegram": adapter})

    response = client.post(
        "/api/v1/gateway/telegram/webhook",
        json={"update_id": 1, "message": {"photo": [{"file_id": "f-1"}]}},
    )

    assert response.status_code == 200
    # The InboundMessage handed to the gateway carries the downloaded files.
    inbound = gw.handle_message.call_args.args[0]
    assert inbound.metadata["attachments"] == downloaded
    # The lightweight refs were consumed, not forwarded raw.
    assert "attachment_refs" not in inbound.metadata


# ---------------------------------------------------------------------------
# Notify / broadcast
# ---------------------------------------------------------------------------


@pytest.mark.spec("gateway.notify_empty_message_returns_400")
def test_notify_empty_message_returns_400() -> None:
    """POST /notify with a blank message returns 400 (semantic validation)."""
    client = _build_client()

    response = client.post(
        "/api/v1/gateway/notify",
        json={"channel": "telegram", "recipient_id": "user-1", "message": "   "},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_request"


@pytest.mark.spec("gateway.broadcast_partial_failure_reports_per_recipient")
def test_broadcast_partial_failure_reports_per_recipient() -> None:
    """A broadcast with mixed delivery reports total/sent/failed + per-recipient."""
    client = _build_client()

    response = client.post(
        "/api/v1/gateway/broadcast",
        json={"channel": "telegram", "message": "Broadcast"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["sent"] == 2
    assert body["failed"] == 1
    # Per-recipient breakdown is present, one entry per recipient.
    results = {r["recipient_id"]: r for r in body["results"]}
    assert results["u1"]["success"] is True
    assert results["u2"]["success"] is False
    assert results["u2"]["error"] == "Not found"


# ---------------------------------------------------------------------------
# Channels list
# ---------------------------------------------------------------------------


@pytest.mark.spec("gateway.channels_list_sorted")
def test_channels_list_sorted() -> None:
    """GET /channels returns the channel names in sorted order."""
    client = _build_client()

    response = client.get("/api/v1/gateway/channels")

    assert response.status_code == 200
    channels = response.json()["channels"]
    assert channels == sorted(channels)
    assert channels == ["slack", "teams", "telegram"]


# ---------------------------------------------------------------------------
# Link-code mint validation
# ---------------------------------------------------------------------------


@pytest.mark.spec("gateway.link_code_invalid_ttl_returns_400")
def test_link_code_invalid_ttl_returns_400() -> None:
    """A TTL outside 60–3600 must be rejected with 400 per the API surface."""
    client = _build_client()

    response = client.post(
        "/api/v1/gateway/telegram/link-codes",
        json={"ttl_seconds": 10},
    )

    assert response.status_code == 400
