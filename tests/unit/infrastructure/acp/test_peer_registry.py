"""Tests for the ACP peer registry implementations."""

from __future__ import annotations

from pathlib import Path

import pytest

from taskforce.core.domain.acp import AcpAuth, AcpAuthType, AcpPeer
from taskforce.infrastructure.acp.peer_registry import (
    EnvPeerRegistry,
    FilePeerRegistry,
    InMemoryPeerRegistry,
)


def _peer(name: str = "p1", token_env: str | None = None) -> AcpPeer:
    auth = AcpAuth(type=AcpAuthType.BEARER, token_env=token_env) if token_env else AcpAuth()
    return AcpPeer(name=name, base_url="http://example", agent="a", auth=auth)


def test_in_memory_registry_register_and_lookup() -> None:
    registry = InMemoryPeerRegistry()
    registry.register(_peer("a"))
    registry.register(_peer("b"))

    assert registry.get("a") is not None
    assert {p.name for p in registry.list()} == {"a", "b"}

    registry.remove("a")
    assert registry.get("a") is None


def test_file_registry_round_trips_to_disk(tmp_path: Path) -> None:
    first = FilePeerRegistry(work_dir=str(tmp_path))
    first.register(_peer("alpha"))
    first.register(_peer("beta", token_env="ACP_TOKEN_BETA"))

    reloaded = FilePeerRegistry(work_dir=str(tmp_path))
    names = {p.name for p in reloaded.list()}
    assert names == {"alpha", "beta"}

    beta = reloaded.get("beta")
    assert beta is not None
    assert beta.auth.type == AcpAuthType.BEARER
    assert beta.auth.token_env == "ACP_TOKEN_BETA"


def test_env_registry_resolves_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inner = InMemoryPeerRegistry()
    inner.register(_peer("peer", token_env="ACP_TEST_TOKEN"))
    env = EnvPeerRegistry(inner)

    # Token missing → token field stays unset.
    resolved = env.get("peer")
    assert resolved is not None
    assert resolved.auth.token is None

    monkeypatch.setenv("ACP_TEST_TOKEN", "secret-123")
    resolved = env.get("peer")
    assert resolved is not None
    assert resolved.auth.token == "secret-123"


# ---------------------------------------------------------------------------
# ADR-022 §6: TenantScopedPeerRegistry — partition by tenant
# ---------------------------------------------------------------------------


from taskforce.application.infrastructure_overrides import (
    clear_infrastructure_overrides,
    set_tenant_resolver,
)
from taskforce.infrastructure.acp.peer_registry import TenantScopedPeerRegistry


def _tenant_peer(name: str, tenant_id: str, *, allow_cross: bool = False) -> AcpPeer:
    return AcpPeer(
        name=name,
        base_url=f"http://{name}.example",
        agent="a",
        auth=AcpAuth(),
        tenant_id=tenant_id,
        allow_cross_tenant=allow_cross,
    )


@pytest.fixture(autouse=False)
def _reset_resolver():
    clear_infrastructure_overrides()
    yield
    clear_infrastructure_overrides()


def test_tenant_scoped_registry_filters_by_current_tenant(_reset_resolver) -> None:
    inner = InMemoryPeerRegistry()
    inner.register(_tenant_peer("alpha", tenant_id="tenant-a"))
    inner.register(_tenant_peer("beta", tenant_id="tenant-b"))
    inner.register(_tenant_peer("shared", tenant_id="tenant-a", allow_cross=True))

    scoped = TenantScopedPeerRegistry(inner)
    set_tenant_resolver(lambda: "tenant-b")

    names = {p.name for p in scoped.list()}
    # tenant-b sees its own + shared, NOT tenant-a's private peer
    assert names == {"beta", "shared"}
    assert scoped.get("alpha") is None
    assert scoped.get("beta") is not None
    assert scoped.get("shared") is not None


def test_tenant_scoped_registry_default_tenant_sees_default_peers(_reset_resolver) -> None:
    """Single-tenant mode (no resolver) — bit-for-bit parity with default."""
    inner = InMemoryPeerRegistry()
    inner.register(_tenant_peer("p1", tenant_id="default"))
    inner.register(_tenant_peer("p2", tenant_id="default"))

    scoped = TenantScopedPeerRegistry(inner)
    # No resolver installed → get_current_tenant_id() returns "default"

    assert {p.name for p in scoped.list()} == {"p1", "p2"}
    assert scoped.get("p1") is not None


def test_tenant_scoped_registry_remove_blocks_cross_tenant(_reset_resolver) -> None:
    inner = InMemoryPeerRegistry()
    inner.register(_tenant_peer("alpha", tenant_id="tenant-a"))

    scoped = TenantScopedPeerRegistry(inner)
    set_tenant_resolver(lambda: "tenant-b")

    # tenant-b cannot see, therefore cannot remove tenant-a's peer
    scoped.remove("alpha")
    assert inner.get("alpha") is not None  # still in inner

    # tenant-a CAN remove its own peer
    set_tenant_resolver(lambda: "tenant-a")
    scoped.remove("alpha")
    assert inner.get("alpha") is None
