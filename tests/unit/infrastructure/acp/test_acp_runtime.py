"""Tests for the AcpRuntime lifecycle facade."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.acp import AcpAgentManifest, AcpPeer
from taskforce.core.utils.time import utc_now
from taskforce.infrastructure.acp.peer_registry import InMemoryPeerRegistry
from taskforce.infrastructure.acp.runtime import AcpRuntime


def _runtime(client: Any | None = None) -> AcpRuntime:
    peers = InMemoryPeerRegistry([AcpPeer(name="p", base_url="http://x", agent="remote-agent")])
    server = MagicMock()
    server.is_running = False
    server.registered_manifests.return_value = []
    if client is None:
        client = MagicMock()
        client.run_sync = AsyncMock(
            return_value={
                "run_id": "r-1",
                "status": "completed",
                "output_text": "hi",
            }
        )
    return AcpRuntime(server=server, client=client, peers=peers)


@pytest.mark.spec("acp.unknown_peer_raises_not_falls_back")
@pytest.mark.asyncio
async def test_call_unknown_peer_raises() -> None:
    rt = _runtime()
    with pytest.raises(KeyError):
        await rt.call("missing", "do X")


@pytest.mark.asyncio
async def test_call_captures_started_at_before_run() -> None:
    """``AcpRunHandle.started_at`` must reflect call start, not completion."""

    async def slow_run_sync(*args: Any, **kwargs: Any) -> dict[str, Any]:
        import asyncio

        await asyncio.sleep(0.05)
        return {"run_id": "r-2", "status": "completed", "output_text": ""}

    client = MagicMock()
    client.run_sync = slow_run_sync
    rt = _runtime(client=client)

    before = utc_now()
    handle = await rt.call("p", "mission")
    after = utc_now()

    assert before <= handle.started_at <= after
    # The call slept ~50 ms; started_at must be measurably before ``after``.
    assert (after - handle.started_at) >= timedelta(milliseconds=40)


@pytest.mark.asyncio
async def test_call_returns_run_id_and_status() -> None:
    rt = _runtime()
    handle = await rt.call("p", "mission")
    assert handle.run_id == "r-1"
    assert handle.peer == "p"
    assert handle.agent == "remote-agent"
    assert handle.status == "completed"
    assert handle.result["output_text"] == "hi"


def test_register_agent_delegates_to_server() -> None:
    rt = _runtime()
    manifest = AcpAgentManifest(name="local", description="")
    handler = AsyncMock()
    rt.register_agent(manifest, handler)
    rt.server.register_agent.assert_called_once_with(manifest, handler)  # type: ignore[attr-defined]


def test_registered_manifests_is_on_server_protocol() -> None:
    """``registered_manifests`` must be reachable without a type: ignore."""
    rt = _runtime()
    # Should not raise; returns whatever the server tracks (empty MagicMock).
    assert rt.server.registered_manifests() == []


@pytest.mark.spec("acp.cross_tenant_call_denied_without_flag")
@pytest.mark.asyncio
async def test_call_rejects_cross_tenant_peer_without_opt_in() -> None:
    peers = InMemoryPeerRegistry(
        [AcpPeer(name="other", base_url="http://x", agent="remote-agent", tenant_id="tenant_b")]
    )
    server = MagicMock()
    server.is_running = False
    client = MagicMock()
    client.run_sync = AsyncMock()
    rt = AcpRuntime(server=server, client=client, peers=peers)

    with pytest.raises(PermissionError):
        await rt.call("other", "mission", tenant_id="tenant_a")

    client.run_sync.assert_not_called()


@pytest.mark.asyncio
async def test_call_uses_tenant_provider_for_cross_tenant_check() -> None:
    peers = InMemoryPeerRegistry(
        [AcpPeer(name="same", base_url="http://x", agent="remote-agent", tenant_id="tenant_a")]
    )
    server = MagicMock()
    server.is_running = False
    client = MagicMock()
    client.run_sync = AsyncMock(return_value={"run_id": "r-3", "status": "completed"})
    rt = AcpRuntime(
        server=server,
        client=client,
        peers=peers,
        tenant_id_provider=lambda: "tenant_a",
    )

    handle = await rt.call("same", "mission")

    assert handle.run_id == "r-3"


# ---------------------------------------------------------------------------
# ADR-022 §6: cross-tenant call goes through the installable authorizer
# ---------------------------------------------------------------------------


from taskforce.application.infrastructure_overrides import (
    clear_infrastructure_overrides,
    set_cross_tenant_acp_authorizer,
)


@pytest.fixture(autouse=False)
def _reset_authorizer():
    clear_infrastructure_overrides()
    yield
    clear_infrastructure_overrides()


@pytest.mark.spec("acp.cross_tenant_authorizer_consulted_per_call")
@pytest.mark.asyncio
async def test_cross_tenant_call_consults_authorizer(_reset_authorizer) -> None:
    """allow_cross_tenant=True peer + authorizer that says no → PermissionError."""
    peers = InMemoryPeerRegistry(
        [
            AcpPeer(
                name="shared",
                base_url="http://x",
                agent="remote-agent",
                tenant_id="tenant_b",
                allow_cross_tenant=True,
            )
        ]
    )
    server = MagicMock()
    server.is_running = False
    client = MagicMock()
    client.run_sync = AsyncMock()
    rt = AcpRuntime(server=server, client=client, peers=peers)

    captured: list[tuple[str, str, str]] = []

    def deny(caller: str, peer_t: str, peer) -> bool:
        captured.append((caller, peer_t, peer.name))
        return False

    set_cross_tenant_acp_authorizer(deny)

    with pytest.raises(PermissionError):
        await rt.call("shared", "mission", tenant_id="tenant_a")

    assert captured == [("tenant_a", "tenant_b", "shared")]
    client.run_sync.assert_not_called()


@pytest.mark.asyncio
async def test_cross_tenant_call_proceeds_when_authorizer_allows(_reset_authorizer) -> None:
    peers = InMemoryPeerRegistry(
        [
            AcpPeer(
                name="shared",
                base_url="http://x",
                agent="remote-agent",
                tenant_id="tenant_b",
                allow_cross_tenant=True,
            )
        ]
    )
    server = MagicMock()
    server.is_running = False
    client = MagicMock()
    client.run_sync = AsyncMock(return_value={"run_id": "r-x", "status": "completed"})
    rt = AcpRuntime(server=server, client=client, peers=peers)

    set_cross_tenant_acp_authorizer(lambda c, p, peer: True)

    handle = await rt.call("shared", "mission", tenant_id="tenant_a")
    assert handle.run_id == "r-x"
    client.run_sync.assert_called_once()


@pytest.mark.asyncio
async def test_same_tenant_call_does_not_consult_authorizer(_reset_authorizer) -> None:
    """Authorizer should only fire on actual cross-tenant calls."""
    peers = InMemoryPeerRegistry(
        [
            AcpPeer(
                name="local",
                base_url="http://x",
                agent="remote-agent",
                tenant_id="tenant_a",
            )
        ]
    )
    server = MagicMock()
    server.is_running = False
    client = MagicMock()
    client.run_sync = AsyncMock(return_value={"run_id": "r-z", "status": "completed"})
    rt = AcpRuntime(server=server, client=client, peers=peers)

    called = {"n": 0}

    def authorizer(c: str, p: str, peer) -> bool:
        called["n"] += 1
        return True

    set_cross_tenant_acp_authorizer(authorizer)

    await rt.call("local", "mission", tenant_id="tenant_a")
    assert called["n"] == 0
