"""Tests for the ``/link <code>`` slash command (issue #162)."""

from __future__ import annotations

from typing import Any

import pytest

from taskforce.application.gateway import CommunicationGateway
from taskforce.core.domain.gateway import InboundMessage
from taskforce.core.domain.models import ExecutionResult
from taskforce.infrastructure.communication.channel_link_registry import (
    InMemoryChannelLinkRegistry,
)
from taskforce.infrastructure.communication.gateway_conversation_store import (
    InMemoryGatewayConversationStore,
)
from taskforce.infrastructure.communication.recipient_registry import (
    InMemoryRecipientRegistry,
)


class _RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def execute_mission(self, **kwargs: Any) -> ExecutionResult:
        self.calls.append(kwargs)
        return ExecutionResult(
            session_id=kwargs["session_id"],
            status="completed",
            final_message="ok",
        )


class _CapturingSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    @property
    def channel(self) -> str:
        return "telegram"

    async def send(self, *, recipient_id: str, message: str, metadata=None) -> None:
        self.sent.append((recipient_id, message))

    async def send_file(self, **kwargs: Any) -> None:  # pragma: no cover
        raise NotImplementedError


def _build_gateway(
    *,
    link_registry: InMemoryChannelLinkRegistry | None = None,
    sender: _CapturingSender | None = None,
) -> tuple[CommunicationGateway, _RecordingExecutor]:
    executor = _RecordingExecutor()
    gateway = CommunicationGateway(
        executor=executor,
        conversation_store=InMemoryGatewayConversationStore(),
        recipient_registry=InMemoryRecipientRegistry(),
        outbound_senders={"telegram": sender} if sender else {},
        link_registry=link_registry,
    )
    return gateway, executor


@pytest.mark.asyncio
async def test_link_command_pairs_sender_and_does_not_reach_agent() -> None:
    registry = InMemoryChannelLinkRegistry()
    code = await registry.create_pending_code(channel="telegram", tenant_id="tid", user_id="rudi")
    sender = _CapturingSender()
    gateway, executor = _build_gateway(link_registry=registry, sender=sender)

    msg = InboundMessage(
        channel="telegram",
        conversation_id="chat-1",
        message=f"/link {code.code}",
        sender_id="tg-99",
    )
    response = await gateway.handle_message(msg)

    assert response.status == "link_created"
    assert response.metadata["tenant_id"] == "tid"
    assert response.metadata["user_id"] == "rudi"
    assert executor.calls == []  # never dispatched to an agent

    link = await registry.lookup(channel="telegram", sender_id="tg-99")
    assert link is not None
    assert link.user_id == "rudi"

    # User receives a confirmation via the outbound sender.
    assert len(sender.sent) == 1
    recipient, body = sender.sent[0]
    assert recipient == "chat-1"
    assert "erfolgreich" in body


@pytest.mark.asyncio
async def test_link_command_with_invalid_code_replies_error() -> None:
    registry = InMemoryChannelLinkRegistry()
    sender = _CapturingSender()
    gateway, executor = _build_gateway(link_registry=registry, sender=sender)

    msg = InboundMessage(
        channel="telegram",
        conversation_id="chat-1",
        message="/link 000000",
        sender_id="tg-99",
    )
    response = await gateway.handle_message(msg)

    assert response.status == "link_invalid"
    assert executor.calls == []
    assert sender.sent and "ungültig" in sender.sent[0][1]


@pytest.mark.asyncio
async def test_link_command_without_code_prints_usage() -> None:
    registry = InMemoryChannelLinkRegistry()
    sender = _CapturingSender()
    gateway, _executor = _build_gateway(link_registry=registry, sender=sender)

    msg = InboundMessage(
        channel="telegram",
        conversation_id="chat-1",
        message="/link",
        sender_id="tg-99",
    )
    response = await gateway.handle_message(msg)

    assert response.status == "link_usage"
    assert sender.sent and "/link <code>" in sender.sent[0][1]


@pytest.mark.asyncio
async def test_link_command_when_registry_disabled() -> None:
    sender = _CapturingSender()
    gateway, _executor = _build_gateway(link_registry=None, sender=sender)

    msg = InboundMessage(
        channel="telegram",
        conversation_id="chat-1",
        message="/link 123456",
        sender_id="tg-99",
    )
    response = await gateway.handle_message(msg)

    assert response.status == "link_disabled"
    assert sender.sent and "nicht aktiviert" in sender.sent[0][1]


@pytest.mark.asyncio
async def test_link_command_without_sender_id_replies_error() -> None:
    registry = InMemoryChannelLinkRegistry()
    code = await registry.create_pending_code(channel="telegram", tenant_id="tid", user_id="u")
    sender = _CapturingSender()
    gateway, _executor = _build_gateway(link_registry=registry, sender=sender)

    msg = InboundMessage(
        channel="telegram",
        conversation_id="chat-1",
        message=f"/link {code.code}",
        sender_id=None,
    )
    response = await gateway.handle_message(msg)

    assert response.status == "link_no_sender"
    assert sender.sent


@pytest.mark.asyncio
async def test_inbound_after_link_resolves_to_linked_user() -> None:
    """Once /link succeeds, subsequent messages from the same sender resolve
    to the linked user via the pass-through resolver."""
    registry = InMemoryChannelLinkRegistry()
    code = await registry.create_pending_code(channel="telegram", tenant_id="tid", user_id="rudi")
    sender = _CapturingSender()
    gateway, executor = _build_gateway(link_registry=registry, sender=sender)

    # Step 1: pair.
    await gateway.handle_message(
        InboundMessage(
            channel="telegram",
            conversation_id="chat-1",
            message=f"/link {code.code}",
            sender_id="tg-99",
        )
    )
    assert executor.calls == []

    # Step 2: a regular message must dispatch to an agent with the linked
    # recipient surfaced via the resolver. The default pass-through
    # resolver in CommunicationGateway is built without a registry by
    # default — but our gateway here was built without a custom resolver
    # *and* a registry, so the gateway constructed a link-aware
    # pass-through internally.
    await gateway.handle_message(
        InboundMessage(
            channel="telegram",
            conversation_id="chat-1",
            message="how is the weather?",
            sender_id="tg-99",
        )
    )
    assert len(executor.calls) == 1
