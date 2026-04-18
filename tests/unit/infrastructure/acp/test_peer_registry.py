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
