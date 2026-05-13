"""Verify AgentService surfaces notification dispatch failures.

A scheduled push that the gateway rejects (e.g. recipient_id not
registered, or no gateway configured at all) used to be only logged
to structlog. That made the failure invisible in the butler status —
operators saw "job fired" but had no record of the dispatch failing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from taskforce.application.agent_service import AgentService


@dataclass
class _Result:
    success: bool
    error: str | None = None
    channel: str = ""
    recipient_id: str = ""


class _RejectingGateway:
    """Gateway that always reports the recipient is not registered."""

    def __init__(self) -> None:
        self.calls: list[Any] = []

    async def send_notification(self, request: Any) -> _Result:
        self.calls.append(request)
        return _Result(
            success=False,
            error=f"Recipient '{request.recipient_id}' not registered on '{request.channel}'",
            channel=request.channel,
            recipient_id=request.recipient_id,
        )


@pytest.mark.asyncio
async def test_failure_recorded_in_status(tmp_path) -> None:
    butler = AgentService(
        work_dir=str(tmp_path),
        default_notification_channel="telegram",
        default_recipient_id="",
    )
    butler.set_gateway(_RejectingGateway())

    await butler._send_notification(
        channel="telegram",
        recipient_id="",
        message="Spielstand prüfen",
        params={},
    )

    status = await butler.get_status()
    failures = status["notification_failures"]
    assert failures["total"] == 1
    assert len(failures["recent"]) == 1
    record = failures["recent"][0]
    assert record["channel"] == "telegram"
    assert record["recipient_id"] == ""
    assert "Spielstand" in record["message_preview"]
    assert "not registered" in record["error"]
    assert record["timestamp"]


@pytest.mark.asyncio
async def test_no_gateway_is_recorded_as_failure(tmp_path) -> None:
    butler = AgentService(work_dir=str(tmp_path))
    # Intentionally no set_gateway call.

    await butler._send_notification(
        channel="telegram",
        recipient_id="u1",
        message="hi",
        params={},
    )

    status = await butler.get_status()
    failures = status["notification_failures"]
    assert failures["total"] == 1
    assert "gateway" in failures["recent"][0]["error"].lower()


@pytest.mark.asyncio
async def test_ring_buffer_caps_at_max(tmp_path) -> None:
    butler = AgentService(work_dir=str(tmp_path))
    butler.set_gateway(_RejectingGateway())

    for i in range(25):
        await butler._send_notification(
            channel="telegram",
            recipient_id="u1",
            message=f"msg-{i}",
            params={},
        )

    status = await butler.get_status()
    failures = status["notification_failures"]
    assert failures["total"] == 25
    # Ring buffer is bounded — only the most recent entries survive.
    assert len(failures["recent"]) == 20
    assert failures["recent"][-1]["message_preview"] == "msg-24"
    assert failures["recent"][0]["message_preview"] == "msg-5"


@pytest.mark.asyncio
async def test_successful_dispatch_does_not_record(tmp_path) -> None:
    class _OkGateway:
        async def send_notification(self, request: Any) -> _Result:
            return _Result(success=True, channel=request.channel, recipient_id=request.recipient_id)

    butler = AgentService(work_dir=str(tmp_path))
    butler.set_gateway(_OkGateway())

    await butler._send_notification(
        channel="telegram",
        recipient_id="u1",
        message="all good",
        params={},
    )

    status = await butler.get_status()
    assert status["notification_failures"]["total"] == 0
    assert status["notification_failures"]["recent"] == []
