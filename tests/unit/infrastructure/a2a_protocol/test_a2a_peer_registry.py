"""Tests for the A2A peer registry implementations."""

from __future__ import annotations

from pathlib import Path

import pytest

from taskforce.application.infrastructure_overrides import (
    clear_infrastructure_overrides,
    set_tenant_resolver,
)
from taskforce.core.domain.a2a import A2aAuth, A2aAuthType, A2aPeer, A2aTransport
from taskforce.infrastructure.a2a.peer_registry import (
    EnvA2aPeerRegistry,
    FileA2aPeerRegistry,
    InMemoryA2aPeerRegistry,
    TenantScopedA2aPeerRegistry,
)


def _peer(
    name: str = "p1",
    *,
    token_env: str | None = None,
    auth_type: A2aAuthType = A2aAuthType.NONE,
    tenant_id: str = "default",
    allow_cross: bool = False,
) -> A2aPeer:
    auth = A2aAuth(type=auth_type, token_env=token_env)
    return A2aPeer(
        name=name,
        base_url="http://example",
        tenant_id=tenant_id,
        allow_cross_tenant=allow_cross,
        auth=auth,
        preferred_transport=A2aTransport.JSON_RPC,
    )


def test_in_memory_registry_register_and_lookup() -> None:
    registry = InMemoryA2aPeerRegistry()
    registry.register(_peer("a"))
    registry.register(_peer("b"))

    assert registry.get("a") is not None
    assert {p.name for p in registry.list()} == {"a", "b"}

    registry.remove("a")
    assert registry.get("a") is None


def test_file_registry_round_trips_to_disk(tmp_path: Path) -> None:
    first = FileA2aPeerRegistry(work_dir=str(tmp_path))
    first.register(_peer("alpha"))
    first.register(
        _peer(
            "beta",
            token_env="A2A_TOKEN_BETA",
            auth_type=A2aAuthType.BEARER,
        )
    )

    reloaded = FileA2aPeerRegistry(work_dir=str(tmp_path))
    names = {p.name for p in reloaded.list()}
    assert names == {"alpha", "beta"}

    beta = reloaded.get("beta")
    assert beta is not None
    assert beta.auth.type == A2aAuthType.BEARER
    assert beta.auth.token_env == "A2A_TOKEN_BETA"


def test_env_registry_resolves_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    inner = InMemoryA2aPeerRegistry()
    inner.register(_peer("peer", token_env="A2A_TEST_TOKEN", auth_type=A2aAuthType.BEARER))
    env = EnvA2aPeerRegistry(inner)

    resolved = env.get("peer")
    assert resolved is not None
    assert resolved.auth.token is None

    monkeypatch.setenv("A2A_TEST_TOKEN", "secret-123")
    resolved = env.get("peer")
    assert resolved is not None
    assert resolved.auth.token == "secret-123"


def test_env_registry_resolves_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    inner = InMemoryA2aPeerRegistry()
    inner.register(_peer("peer", token_env="A2A_API_KEY", auth_type=A2aAuthType.API_KEY))
    env = EnvA2aPeerRegistry(inner)

    monkeypatch.setenv("A2A_API_KEY", "key-xyz")
    resolved = env.get("peer")
    assert resolved is not None
    assert resolved.auth.token == "key-xyz"


def test_tenant_scoped_registry_hides_other_tenants() -> None:
    clear_infrastructure_overrides()
    try:
        inner = InMemoryA2aPeerRegistry()
        inner.register(_peer("mine", tenant_id="alpha"))
        inner.register(_peer("theirs", tenant_id="beta"))
        inner.register(_peer("shared", tenant_id="beta", allow_cross=True))

        scoped = TenantScopedA2aPeerRegistry(inner)
        set_tenant_resolver(lambda: "alpha")

        names = {p.name for p in scoped.list()}
        assert names == {"mine", "shared"}
        assert scoped.get("theirs") is None
        assert scoped.get("shared") is not None
    finally:
        clear_infrastructure_overrides()
