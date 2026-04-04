"""Tests for SendNotificationTool."""

from typing import Any

import pytest

from taskforce.core.domain.gateway import NotificationResult
from taskforce.infrastructure.tools.native.send_notification_tool import (
    SendNotificationTool,
)


class FakeGateway:
    """Minimal gateway mock for tool tests."""

    def __init__(self, success: bool = True, error: str | None = None) -> None:
        self._success = success
        self._error = error
        self.last_request = None

    async def send_notification(self, request: Any) -> NotificationResult:
        self.last_request = request
        return NotificationResult(
            success=self._success,
            channel=request.channel,
            recipient_id=request.recipient_id,
            error=self._error,
        )


@pytest.mark.asyncio
async def test_send_notification_success() -> None:
    gw = FakeGateway(success=True)
    tool = SendNotificationTool(gateway=gw)

    result = await tool.execute(
        channel="telegram",
        recipient_id="user-1",
        message="Your report is ready!",
    )

    assert result["success"]
    assert result["channel"] == "telegram"
    assert result["recipient_id"] == "user-1"
    assert gw.last_request.message == "Your report is ready!"


@pytest.mark.asyncio
async def test_send_notification_failure() -> None:
    gw = FakeGateway(success=False, error="Recipient not found")
    tool = SendNotificationTool(gateway=gw)

    result = await tool.execute(
        channel="telegram",
        recipient_id="unknown",
        message="test",
    )

    assert not result["success"]
    assert "Recipient not found" in result["error"]


@pytest.mark.asyncio
async def test_send_notification_no_gateway() -> None:
    tool = SendNotificationTool(gateway=None)

    result = await tool.execute(
        channel="telegram",
        recipient_id="user-1",
        message="test",
    )

    assert not result["success"]
    assert "gateway not configured" in result["error"]


def test_validate_params_success() -> None:
    tool = SendNotificationTool()
    valid, error = tool.validate_params(channel="telegram", recipient_id="user-1", message="Hello")
    assert valid
    assert error is None


def test_validate_params_missing_field() -> None:
    tool = SendNotificationTool()
    valid, error = tool.validate_params(channel="telegram", recipient_id="user-1")
    assert not valid
    assert "message" in error


def test_validate_params_empty_field() -> None:
    tool = SendNotificationTool()
    valid, error = tool.validate_params(channel="telegram", recipient_id="user-1", message="")
    assert not valid
    assert "empty" in error


def test_tool_metadata() -> None:
    tool = SendNotificationTool()
    assert tool.name == "send_notification"
    assert tool.requires_approval
    assert "push notification" in tool.description


def test_approval_preview() -> None:
    tool = SendNotificationTool()
    preview = tool.get_approval_preview(
        channel="telegram",
        recipient_id="user-1",
        message="Report ready!",
    )
    assert "telegram" in preview
    assert "user-1" in preview
    assert "Report ready!" in preview
