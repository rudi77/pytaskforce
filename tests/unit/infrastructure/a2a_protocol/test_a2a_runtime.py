"""Tests for the A2aRuntime façade — tenant scoping + dispatch."""

from __future__ import annotations

from typing import Any

import pytest

from taskforce.core.domain.a2a import A2aPeer, A2aTaskHandle, A2aTaskState
from taskforce.infrastructure.a2a.peer_registry import InMemoryA2aPeerRegistry
from taskforce.infrastructure.a2a.runtime import A2aRuntime


class _StubClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    async def run_sync(
        self, peer: A2aPeer, mission: str, *, session_id: str | None = None, push: Any = None
    ) -> A2aTaskHandle:
        self.calls.append((peer.name, mission, session_id))
        return A2aTaskHandle(
            task_id="t1",
            peer=peer.name,
            state=A2aTaskState.COMPLETED,
            output_text=f"reply to {mission}",
        )

    async def run_stream(self, *args: Any, **kwargs: Any):  # pragma: no cover
        if False:
            yield {}

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_runtime_call_routes_to_client() -> None:
    peers = InMemoryA2aPeerRegistry([A2aPeer(name="echo", base_url="http://example")])
    client = _StubClient()
    runtime = A2aRuntime(client=client, peers=peers)

    handle = await runtime.call("echo", "hello")
    assert handle.state == A2aTaskState.COMPLETED
    assert handle.output_text == "reply to hello"
    assert client.calls == [("echo", "hello", None)]


@pytest.mark.asyncio
async def test_runtime_call_raises_on_unknown_peer() -> None:
    runtime = A2aRuntime(client=_StubClient(), peers=InMemoryA2aPeerRegistry())
    with pytest.raises(KeyError):
        await runtime.call("ghost", "hi")


@pytest.mark.asyncio
async def test_runtime_blocks_cross_tenant_without_flag() -> None:
    peers = InMemoryA2aPeerRegistry([A2aPeer(name="other", base_url="http://x", tenant_id="alpha")])
    runtime = A2aRuntime(
        client=_StubClient(),
        peers=peers,
        tenant_id_provider=lambda: "beta",
    )
    with pytest.raises(PermissionError):
        await runtime.call("other", "hi")


@pytest.mark.asyncio
async def test_runtime_allows_cross_tenant_with_flag() -> None:
    peers = InMemoryA2aPeerRegistry(
        [
            A2aPeer(
                name="shared",
                base_url="http://x",
                tenant_id="alpha",
                allow_cross_tenant=True,
            )
        ]
    )
    runtime = A2aRuntime(
        client=_StubClient(),
        peers=peers,
        tenant_id_provider=lambda: "beta",
    )
    handle = await runtime.call("shared", "hi")
    assert handle.peer == "shared"


@pytest.mark.asyncio
async def test_runtime_register_agent_requires_server() -> None:
    runtime = A2aRuntime(client=_StubClient(), peers=InMemoryA2aPeerRegistry())
    with pytest.raises(RuntimeError, match="no server configured"):
        runtime.register_agent(object(), object())
