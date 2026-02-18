"""Tests for WebhookEventSource."""

import pytest
from unittest.mock import AsyncMock

from taskforce.core.domain.agent_event import AgentEventType
from taskforce.infrastructure.event_sources.webhook_source import WebhookEventSource


class TestWebhookEventSource:
    """Tests for the webhook event source."""

    @pytest.fixture
    def callback(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def source(self, callback: AsyncMock) -> WebhookEventSource:
        return WebhookEventSource(event_callback=callback)

    async def test_start_stop(self, source: WebhookEventSource) -> None:
        assert not source.is_running
        await source.start()
        assert source.is_running
        await source.stop()
        assert not source.is_running

    async def test_source_name(self, source: WebhookEventSource) -> None:
        assert source.source_name == "webhook"

    async def test_handle_webhook(
        self, source: WebhookEventSource, callback: AsyncMock
    ) -> None:
        await source.start()
        event = await source.handle_webhook(
            source_label="github",
            payload={"action": "push", "ref": "refs/heads/main"},
            metadata={"ip": "192.168.1.1"},
        )

        assert event.source == "webhook.github"
        assert event.event_type == AgentEventType.WEBHOOK_RECEIVED
        assert event.payload["action"] == "push"
        assert event.metadata["ip"] == "192.168.1.1"
        callback.assert_called_once_with(event)

    async def test_handle_webhook_without_callback(self) -> None:
        source = WebhookEventSource(event_callback=None)
        await source.start()
        event = await source.handle_webhook(
            source_label="jira",
            payload={"issue": "TEST-123"},
        )
        assert event.source == "webhook.jira"
