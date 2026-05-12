"""Tests for the ``RecipientResolverProtocol`` extension point on the gateway.

Verifies that:
1. The default pass-through resolver preserves pre-existing behaviour.
2. A custom resolver can supply a ``default_agent_id`` that overrides
   the absence of an explicit ``options.agent_id``.
3. A custom resolver returning ``None`` produces an audited deny.
4. An explicit ``options.agent_id`` always wins over the resolver's
   default suggestion.
"""

from __future__ import annotations

from typing import Any

import pytest

from taskforce.application.gateway import (
    CommunicationGateway,
    _PassthroughRecipientResolver,
)
from taskforce.core.domain.gateway import (
    GatewayOptions,
    InboundMessage,
)
from taskforce.core.domain.models import ExecutionResult
from taskforce.core.interfaces.gateway import RecipientInfo
from taskforce.infrastructure.communication.gateway_conversation_store import (
    InMemoryGatewayConversationStore,
)
from taskforce.infrastructure.communication.recipient_registry import (
    InMemoryRecipientRegistry,
)


class _RecordingExecutor:
    """Executor stub that records the agent_id it was asked to run."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def execute_mission(self, **kwargs: Any) -> ExecutionResult:
        self.calls.append(kwargs)
        return ExecutionResult(
            session_id=kwargs["session_id"],
            status="completed",
            final_message="ok",
        )


def _build_gateway(
    *,
    executor: _RecordingExecutor,
    resolver: Any | None = None,
) -> CommunicationGateway:
    return CommunicationGateway(
        executor=executor,
        conversation_store=InMemoryGatewayConversationStore(),
        recipient_registry=InMemoryRecipientRegistry(),
        outbound_senders={},
        recipient_resolver=resolver,
    )


# ---------------------------------------------------------------------------
# Pass-through resolver
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_passthrough_uses_sender_id() -> None:
    resolver = _PassthroughRecipientResolver()
    info = await resolver.resolve("web", {"sender_id": "u-1"})
    assert info is not None
    assert info.recipient_id == "u-1"
    assert info.default_agent_id is None


@pytest.mark.asyncio
async def test_passthrough_falls_back_to_conversation_id() -> None:
    resolver = _PassthroughRecipientResolver()
    info = await resolver.resolve("web", {"conversation_id": "c-9"})
    assert info is not None
    assert info.recipient_id == "c-9"


@pytest.mark.asyncio
async def test_passthrough_anonymous_when_no_identifiers() -> None:
    """The pass-through never returns None — it always synthesises a recipient."""
    resolver = _PassthroughRecipientResolver()
    info = await resolver.resolve("web", {})
    assert info is not None
    assert info.recipient_id == "anonymous"


# ---------------------------------------------------------------------------
# Gateway integration: default resolver preserves legacy behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_resolver_does_not_change_legacy_routing() -> None:
    """Without a custom resolver, the gateway behaves exactly as before."""
    executor = _RecordingExecutor()
    gateway = _build_gateway(executor=executor)

    msg = InboundMessage(
        channel="web",
        conversation_id="conv-1",
        message="Hi",
        sender_id="user-a",
    )
    response = await gateway.handle_message(msg)

    assert response.status == "completed"
    assert len(executor.calls) == 1
    # No agent_id was supplied via options or resolver, so executor sees None.
    assert executor.calls[0].get("agent_id") is None


# ---------------------------------------------------------------------------
# Custom resolver: default_agent_id flows into options
# ---------------------------------------------------------------------------


class _FixedAgentResolver:
    """Resolver that always returns the same recipient with a fixed agent."""

    def __init__(self, recipient_id: str, default_agent_id: str) -> None:
        self._info = RecipientInfo(
            recipient_id=recipient_id,
            default_agent_id=default_agent_id,
        )

    async def resolve(
        self,
        channel: str,
        channel_identity: dict[str, Any],
    ) -> RecipientInfo | None:
        return self._info


@pytest.mark.asyncio
async def test_resolver_default_agent_id_used_when_options_missing() -> None:
    executor = _RecordingExecutor()
    gateway = _build_gateway(
        executor=executor,
        resolver=_FixedAgentResolver(recipient_id="rudi", default_agent_id="acc"),
    )

    msg = InboundMessage(
        channel="web",
        conversation_id="c-1",
        message="hi",
        sender_id="user-a",
    )
    await gateway.handle_message(msg)

    assert executor.calls[0]["agent_id"] == "acc"


@pytest.mark.asyncio
async def test_explicit_options_agent_id_wins_over_resolver_default() -> None:
    executor = _RecordingExecutor()
    gateway = _build_gateway(
        executor=executor,
        resolver=_FixedAgentResolver(recipient_id="rudi", default_agent_id="acc"),
    )

    msg = InboundMessage(
        channel="web",
        conversation_id="c-1",
        message="hi",
        sender_id="user-a",
    )
    await gateway.handle_message(msg, GatewayOptions(profile="butler", agent_id="explicit"))

    assert executor.calls[0]["agent_id"] == "explicit"


# ---------------------------------------------------------------------------
# Custom resolver: returning None denies the message
# ---------------------------------------------------------------------------


class _AlwaysDenyResolver:
    async def resolve(
        self,
        channel: str,
        channel_identity: dict[str, Any],
    ) -> RecipientInfo | None:
        return None


@pytest.mark.asyncio
async def test_resolver_returning_none_produces_audited_deny() -> None:
    executor = _RecordingExecutor()
    gateway = _build_gateway(executor=executor, resolver=_AlwaysDenyResolver())

    msg = InboundMessage(
        channel="web",
        conversation_id="c-1",
        message="hi",
        sender_id="user-a",
    )
    response = await gateway.handle_message(msg)

    assert response.status == "recipient_unresolved"
    # Executor must NOT have been called.
    assert executor.calls == []


@pytest.mark.asyncio
async def test_resolver_called_with_inbound_identity_payload() -> None:
    """The resolver receives sender_id, conversation_id, and metadata."""
    received: dict[str, Any] = {}

    class _RecordingResolver:
        async def resolve(
            self,
            channel: str,
            channel_identity: dict[str, Any],
        ) -> RecipientInfo | None:
            received["channel"] = channel
            received["identity"] = dict(channel_identity)
            return RecipientInfo(recipient_id="rec")

    executor = _RecordingExecutor()
    gateway = _build_gateway(executor=executor, resolver=_RecordingResolver())

    msg = InboundMessage(
        channel="web",
        conversation_id="c-1",
        message="hi",
        sender_id="user-a",
        metadata={"k": "v"},
    )
    await gateway.handle_message(msg)

    assert received["channel"] == "web"
    assert received["identity"]["sender_id"] == "user-a"
    assert received["identity"]["conversation_id"] == "c-1"
    assert received["identity"]["metadata"] == {"k": "v"}


# ---------------------------------------------------------------------------
# Issue #162: pass-through resolver consults the channel-link registry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_passthrough_with_link_registry_returns_linked_user() -> None:
    from taskforce.infrastructure.communication.channel_link_registry import (
        InMemoryChannelLinkRegistry,
    )

    link_registry = InMemoryChannelLinkRegistry()
    code = await link_registry.create_pending_code(
        channel="telegram", tenant_id="tid-a", user_id="rudi"
    )
    await link_registry.consume_code(channel="telegram", code=code.code, sender_id="tg-12345")

    resolver = _PassthroughRecipientResolver(link_registry=link_registry)
    info = await resolver.resolve("telegram", {"sender_id": "tg-12345"})

    assert info is not None
    assert info.recipient_id == "rudi"
    assert info.attributes["tenant_id"] == "tid-a"
    assert info.attributes["user_id"] == "rudi"
    assert info.attributes["channel_sender_id"] == "tg-12345"


@pytest.mark.asyncio
async def test_passthrough_with_link_registry_falls_through_for_unlinked() -> None:
    from taskforce.infrastructure.communication.channel_link_registry import (
        InMemoryChannelLinkRegistry,
    )

    resolver = _PassthroughRecipientResolver(link_registry=InMemoryChannelLinkRegistry())
    info = await resolver.resolve("telegram", {"sender_id": "tg-unlinked"})

    assert info is not None
    assert info.recipient_id == "tg-unlinked"
    assert info.attributes == {}
