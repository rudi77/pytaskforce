"""Unit tests for the gateway routes."""

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi")

from datetime import UTC

from fastapi.testclient import TestClient

from taskforce.api.server import create_app
from taskforce.core.domain.gateway import GatewayResponse, NotificationResult


def _mock_gateway():
    """Create a mock CommunicationGateway."""
    gw = AsyncMock()
    gw.handle_message = AsyncMock(
        return_value=GatewayResponse(
            session_id="sess-1",
            status="completed",
            reply="Hello!",
            history=[
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello!"},
            ],
        )
    )
    gw.send_notification = AsyncMock(
        return_value=NotificationResult(
            success=True,
            channel="telegram",
            recipient_id="user-1",
            error=None,
        )
    )
    gw.broadcast = AsyncMock(
        return_value=[
            NotificationResult(
                success=True,
                channel="telegram",
                recipient_id="u1",
                error=None,
            ),
            NotificationResult(
                success=False,
                channel="telegram",
                recipient_id="u2",
                error="Not found",
            ),
        ]
    )
    gw.supported_channels = MagicMock(return_value=["telegram", "teams"])
    return gw


def _mock_adapters():
    """Create mock inbound adapters."""
    adapter = MagicMock()
    adapter.verify_signature = MagicMock(return_value=True)
    adapter.extract_message = MagicMock(
        return_value={
            "conversation_id": "conv-1",
            "message": "Webhook message",
            "sender_id": "sender-1",
            "metadata": {},
        }
    )
    return {"telegram": adapter}


@pytest.fixture
def client():
    from taskforce.api.dependencies import get_gateway, get_inbound_adapters

    app = create_app()
    app.dependency_overrides[get_gateway] = _mock_gateway
    app.dependency_overrides[get_inbound_adapters] = _mock_adapters
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestHandleMessage:
    """Tests for POST /api/v1/gateway/{channel}/messages."""

    def test_handle_message_success(self, client):
        response = client.post(
            "/api/v1/gateway/telegram/messages",
            json={
                "conversation_id": "conv-1",
                "message": "Hello",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["session_id"] == "sess-1"
        assert body["status"] == "completed"
        assert body["reply"] == "Hello!"
        assert body["history_length"] == 2

    def test_handle_message_empty_message(self, client):
        response = client.post(
            "/api/v1/gateway/telegram/messages",
            json={
                "conversation_id": "conv-1",
                "message": "   ",
            },
        )
        assert response.status_code == 400
        body = response.json()
        assert body["code"] == "invalid_request"
        assert "message" in body

    def test_handle_message_missing_conversation_id(self, client):
        response = client.post(
            "/api/v1/gateway/telegram/messages",
            json={"message": "Hello"},
        )
        assert response.status_code == 422

    def test_handle_message_with_options(self, client):
        response = client.post(
            "/api/v1/gateway/rest/messages",
            json={
                "conversation_id": "conv-1",
                "message": "Hello",
                "profile": "coding_agent",
                "session_id": "custom-session",
                "agent_id": "research_agent",
            },
        )
        assert response.status_code == 200


class TestHandleWebhook:
    """Tests for POST /api/v1/gateway/{channel}/webhook."""

    def test_webhook_success(self, client):
        response = client.post(
            "/api/v1/gateway/telegram/webhook",
            json={"update_id": 12345, "message": {"text": "Hi"}},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["session_id"] == "sess-1"

    def test_webhook_unknown_channel(self, client):
        response = client.post(
            "/api/v1/gateway/unknown_channel/webhook",
            json={"data": "test"},
        )
        assert response.status_code == 400
        body = response.json()
        assert body["code"] == "invalid_request"

    def test_webhook_with_profile_query_param(self):
        """Webhook passes profile query parameter via GatewayOptions."""
        from taskforce.api.dependencies import get_gateway, get_inbound_adapters

        gw = _mock_gateway()
        app = create_app()
        app.dependency_overrides[get_gateway] = lambda: gw
        app.dependency_overrides[get_inbound_adapters] = _mock_adapters

        with TestClient(app) as tc:
            response = tc.post(
                "/api/v1/gateway/telegram/webhook?profile=accounting_agent",
                json={"update_id": 12345, "message": {"text": "Hi"}},
            )
        assert response.status_code == 200

        call_args = gw.handle_message.call_args
        options = call_args.args[1] if len(call_args.args) > 1 else None
        assert options is not None
        assert options.profile == "accounting_agent"
        app.dependency_overrides.clear()

    def test_webhook_with_plugin_path_query_param(self):
        """Webhook passes plugin_path query parameter via GatewayOptions."""
        from taskforce.api.dependencies import get_gateway, get_inbound_adapters

        gw = _mock_gateway()
        app = create_app()
        app.dependency_overrides[get_gateway] = lambda: gw
        app.dependency_overrides[get_inbound_adapters] = _mock_adapters

        with TestClient(app) as tc:
            response = tc.post(
                "/api/v1/gateway/telegram/webhook"
                "?profile=accounting_agent&plugin_path=examples/accounting_agent",
                json={"update_id": 12345, "message": {"text": "Hi"}},
            )
        assert response.status_code == 200

        call_args = gw.handle_message.call_args
        options = call_args.args[1] if len(call_args.args) > 1 else None
        assert options is not None
        assert options.profile == "accounting_agent"
        assert options.plugin_path == "examples/accounting_agent"
        app.dependency_overrides.clear()

    def test_webhook_default_profile(self):
        """Webhook without profile query param defaults to 'butler'."""
        from taskforce.api.dependencies import get_gateway, get_inbound_adapters

        gw = _mock_gateway()
        app = create_app()
        app.dependency_overrides[get_gateway] = lambda: gw
        app.dependency_overrides[get_inbound_adapters] = _mock_adapters

        with TestClient(app) as tc:
            response = tc.post(
                "/api/v1/gateway/telegram/webhook",
                json={"update_id": 12345, "message": {"text": "Hi"}},
            )
        assert response.status_code == 200

        call_args = gw.handle_message.call_args
        options = call_args.args[1] if len(call_args.args) > 1 else None
        assert options is not None
        assert options.profile == "butler"
        assert options.plugin_path is None
        app.dependency_overrides.clear()

    def test_webhook_signature_failure(self, client):
        from taskforce.api.dependencies import get_inbound_adapters

        def bad_adapters():
            adapter = MagicMock()
            adapter.verify_signature = MagicMock(return_value=False)
            return {"telegram": adapter}

        app = client.app
        app.dependency_overrides[get_inbound_adapters] = bad_adapters

        response = client.post(
            "/api/v1/gateway/telegram/webhook",
            json={"data": "test"},
        )
        assert response.status_code == 401
        body = response.json()
        assert body["code"] == "unauthorized"


class TestNotify:
    """Tests for POST /api/v1/gateway/notify."""

    def test_notify_success(self, client):
        response = client.post(
            "/api/v1/gateway/notify",
            json={
                "channel": "telegram",
                "recipient_id": "user-1",
                "message": "Hello!",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["channel"] == "telegram"

    def test_notify_empty_message(self, client):
        response = client.post(
            "/api/v1/gateway/notify",
            json={
                "channel": "telegram",
                "recipient_id": "user-1",
                "message": "  ",
            },
        )
        assert response.status_code == 400

    def test_notify_missing_fields(self, client):
        response = client.post(
            "/api/v1/gateway/notify",
            json={"channel": "telegram"},
        )
        assert response.status_code == 422


class TestBroadcast:
    """Tests for POST /api/v1/gateway/broadcast."""

    def test_broadcast_success(self, client):
        response = client.post(
            "/api/v1/gateway/broadcast",
            json={
                "channel": "telegram",
                "message": "Broadcast msg",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert body["sent"] == 1
        assert body["failed"] == 1

    def test_broadcast_empty_message(self, client):
        response = client.post(
            "/api/v1/gateway/broadcast",
            json={"channel": "telegram", "message": ""},
        )
        assert response.status_code == 400


class TestListChannels:
    """Tests for GET /api/v1/gateway/channels."""

    def test_list_channels(self, client):
        response = client.get("/api/v1/gateway/channels")
        assert response.status_code == 200
        body = response.json()
        assert "channels" in body
        assert sorted(body["channels"]) == ["teams", "telegram"]


class TestLinkCodeEndpoints:
    """Tests for the issue #162 link-code mint + revoke endpoints."""

    @pytest.fixture
    def link_client(self):
        from taskforce.api.dependencies import get_channel_link_registry
        from taskforce.infrastructure.communication.channel_link_registry import (
            InMemoryChannelLinkRegistry,
        )

        registry = InMemoryChannelLinkRegistry()
        app = create_app()
        app.dependency_overrides[get_channel_link_registry] = lambda: registry
        yield TestClient(app), registry
        app.dependency_overrides.clear()

    def test_mint_link_code_default_ttl(self, link_client):
        client, _registry = link_client
        response = client.post("/api/v1/gateway/telegram/link-codes", json={})
        assert response.status_code == 200
        body = response.json()
        assert body["channel"] == "telegram"
        assert body["code"].isdigit()
        assert len(body["code"]) == 6
        assert body["ttl_seconds"] == 600
        assert body["expires_at"]

    def test_mint_link_code_custom_ttl(self, link_client):
        client, _registry = link_client
        response = client.post(
            "/api/v1/gateway/telegram/link-codes",
            json={"ttl_seconds": 90},
        )
        assert response.status_code == 200
        assert response.json()["ttl_seconds"] == 90

    def test_mint_link_code_rejects_invalid_ttl(self, link_client):
        client, _registry = link_client
        response = client.post(
            "/api/v1/gateway/telegram/link-codes",
            json={"ttl_seconds": 10},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_request"

    def test_mint_then_consume_writes_to_registry(self, link_client):
        client, registry = link_client
        mint = client.post("/api/v1/gateway/telegram/link-codes", json={}).json()

        # Mint endpoint should have populated the pending bucket.
        assert mint["code"] in registry._pending["telegram"]
        record = registry._pending["telegram"][mint["code"]]
        assert record["tenant_id"] == "default"
        assert record["user_id"] == "default"

    def test_delete_my_links_with_no_links(self, link_client):
        client, _registry = link_client
        response = client.delete("/api/v1/gateway/telegram/links/me")
        assert response.status_code == 200
        assert response.json() == {"channel": "telegram", "removed": 0}

    def test_delete_my_links_removes_caller_links(self, link_client):
        from datetime import datetime

        client, registry = link_client
        # Pre-seed two links directly so we don't need cross-loop async calls.
        now = datetime.now(UTC)
        registry._links["telegram"] = {
            "tg-1": {
                "tenant_id": "default",
                "user_id": "default",
                "linked_at": now,
            },
            "tg-2": {
                "tenant_id": "default",
                "user_id": "default",
                "linked_at": now,
            },
        }
        # And one link owned by a different user that must be left alone.
        registry._links.setdefault("telegram", {})["tg-3"] = {
            "tenant_id": "default",
            "user_id": "someone-else",
            "linked_at": now,
        }

        response = client.delete("/api/v1/gateway/telegram/links/me")
        assert response.status_code == 200
        assert response.json() == {"channel": "telegram", "removed": 2}
        # tg-3 must still be present.
        assert "tg-3" in registry._links["telegram"]
