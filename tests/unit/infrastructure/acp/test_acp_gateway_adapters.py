"""Tests for AcpInboundAdapter and AcpOutboundSender."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.acp import AcpPeer
from taskforce.infrastructure.acp.acp_gateway_adapters import (
    AcpInboundAdapter,
    AcpOutboundSender,
)
from taskforce.infrastructure.acp.peer_registry import InMemoryPeerRegistry
from taskforce.infrastructure.acp.runtime import AcpRuntime


def test_extract_message_collects_text_parts() -> None:
    adapter = AcpInboundAdapter()
    payload = {
        "agent": "coder",
        "session_id": "s-1",
        "sender_id": "peer_a",
        "input": [
            {
                "role": "user",
                "parts": [
                    {"content": "Refactor", "content_type": "text/plain"},
                    {"content": "module foo", "content_type": "text/plain"},
                ],
            }
        ],
    }
    extracted = adapter.extract_message(payload)
    assert extracted["conversation_id"] == "s-1"
    assert "Refactor" in extracted["message"]
    assert "module foo" in extracted["message"]
    assert extracted["metadata"]["agent"] == "coder"


def test_extract_message_raises_on_empty_input() -> None:
    adapter = AcpInboundAdapter()
    with pytest.raises(ValueError):
        adapter.extract_message({"agent": "x", "input": []})


def test_verify_signature_requires_matching_secret() -> None:
    adapter = AcpInboundAdapter(shared_secret="s3cret")
    assert adapter.verify_signature(raw_body=b"", headers={"x-acp-secret": "s3cret"})
    assert not adapter.verify_signature(raw_body=b"", headers={"x-acp-secret": "nope"})


def test_verify_signature_unconfigured_accepts_all() -> None:
    adapter = AcpInboundAdapter()
    assert adapter.verify_signature(raw_body=b"", headers={})


@pytest.mark.asyncio
async def test_outbound_sender_dispatches_via_runtime() -> None:
    client = MagicMock()
    client.run_sync = AsyncMock(return_value={"status": "ok"})
    peers = InMemoryPeerRegistry([AcpPeer(name="peer_a", base_url="http://a", agent="agent-x")])
    server = MagicMock()
    server.registered_manifests.return_value = []
    runtime = AcpRuntime(server=server, client=client, peers=peers)

    sender = AcpOutboundSender(runtime)
    await sender.send(
        recipient_id="peer_a",
        message="hello",
        metadata={"session_id": "s-9"},
    )

    client.run_sync.assert_awaited_once()
    assert client.run_sync.call_args.kwargs["session_id"] == "s-9"


@pytest.mark.asyncio
async def test_outbound_sender_unknown_peer_raises() -> None:
    runtime = AcpRuntime(server=MagicMock(), client=MagicMock(), peers=InMemoryPeerRegistry())
    sender = AcpOutboundSender(runtime)
    with pytest.raises(ValueError):
        await sender.send(recipient_id="ghost", message="x")
