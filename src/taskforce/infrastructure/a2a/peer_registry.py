"""A2A peer registry implementations.

Mirrors ``infrastructure/acp/peer_registry.py``: InMemory / File / Env /
TenantScoped variants compose so the file store backs the env resolver
that backs the tenant filter.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock

from taskforce.application.infrastructure_overrides import get_current_tenant_id
from taskforce.core.domain.a2a import A2aAuth, A2aAuthType, A2aPeer, A2aTransport
from taskforce.core.utils.secure_file import write_private_text


class InMemoryA2aPeerRegistry:
    """Simple in-memory peer registry (primarily for tests)."""

    def __init__(self, peers: list[A2aPeer] | None = None) -> None:
        self._peers: dict[str, A2aPeer] = {}
        self._lock = RLock()
        for peer in peers or []:
            self._peers[peer.name] = peer

    def get(self, name: str) -> A2aPeer | None:
        with self._lock:
            return self._peers.get(name)

    def list(self) -> list[A2aPeer]:
        with self._lock:
            return list(self._peers.values())

    def register(self, peer: A2aPeer) -> None:
        with self._lock:
            self._peers[peer.name] = peer

    def remove(self, name: str) -> None:
        with self._lock:
            self._peers.pop(name, None)


class FileA2aPeerRegistry(InMemoryA2aPeerRegistry):
    """A2A peer registry backed by ``<work_dir>/a2a_peers.json``."""

    def __init__(self, work_dir: str = ".taskforce") -> None:
        super().__init__()
        self._path = Path(work_dir) / "a2a_peers.json"
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        for entry in data.get("peers", []):
            peer = _peer_from_dict(entry)
            if peer is not None:
                self._peers[peer.name] = peer

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"peers": [_peer_to_dict(p) for p in self._peers.values()]}
        write_private_text(self._path, json.dumps(payload, indent=2))

    def register(self, peer: A2aPeer) -> None:
        super().register(peer)
        self._save()

    def remove(self, name: str) -> None:
        super().remove(name)
        self._save()


class EnvA2aPeerRegistry(InMemoryA2aPeerRegistry):
    """Resolves bearer/api_key tokens from environment variables on read."""

    def __init__(self, inner: InMemoryA2aPeerRegistry) -> None:
        super().__init__()
        self._inner = inner

    def get(self, name: str) -> A2aPeer | None:
        peer = self._inner.get(name)
        if peer is None:
            return None
        return _resolve_env_auth(peer)

    def list(self) -> list[A2aPeer]:
        return [_resolve_env_auth(p) for p in self._inner.list()]

    def register(self, peer: A2aPeer) -> None:
        self._inner.register(peer)

    def remove(self, name: str) -> None:
        self._inner.remove(name)


class TenantScopedA2aPeerRegistry(InMemoryA2aPeerRegistry):
    """A2A peer registry that filters peers by current tenant.

    Mirror of ``TenantScopedPeerRegistry`` for ACP (ADR-022 §6).
    """

    def __init__(self, inner: InMemoryA2aPeerRegistry) -> None:
        super().__init__()
        self._inner = inner

    def _is_visible(self, peer: A2aPeer) -> bool:
        if peer.allow_cross_tenant:
            return True
        return peer.tenant_id == get_current_tenant_id()

    def get(self, name: str) -> A2aPeer | None:
        peer = self._inner.get(name)
        if peer is None:
            return None
        return peer if self._is_visible(peer) else None

    def list(self) -> list[A2aPeer]:
        return [p for p in self._inner.list() if self._is_visible(p)]

    def register(self, peer: A2aPeer) -> None:
        self._inner.register(peer)

    def remove(self, name: str) -> None:
        peer = self._inner.get(name)
        if peer is None or not self._is_visible(peer):
            return
        self._inner.remove(name)


def _resolve_env_auth(peer: A2aPeer) -> A2aPeer:
    if peer.auth.type not in (A2aAuthType.BEARER, A2aAuthType.API_KEY):
        return peer
    if not peer.auth.token_env:
        return peer
    token = os.getenv(peer.auth.token_env)
    if not token:
        return peer
    return A2aPeer(
        name=peer.name,
        base_url=peer.base_url,
        agent_card_url=peer.agent_card_url,
        description=peer.description,
        tenant_id=peer.tenant_id,
        allow_cross_tenant=peer.allow_cross_tenant,
        preferred_transport=peer.preferred_transport,
        poll_interval_seconds=peer.poll_interval_seconds,
        auth=A2aAuth(
            type=peer.auth.type,
            token_env=peer.auth.token_env,
            token=token,
            api_key_header=peer.auth.api_key_header,
            provider=peer.auth.provider,
            scopes=peer.auth.scopes,
            client_id_env=peer.auth.client_id_env,
            token_url=peer.auth.token_url,
            cert_path=peer.auth.cert_path,
            key_path=peer.auth.key_path,
        ),
    )


def _peer_to_dict(peer: A2aPeer) -> dict:
    return {
        "name": peer.name,
        "base_url": peer.base_url,
        "agent_card_url": peer.agent_card_url,
        "description": peer.description,
        "tenant_id": peer.tenant_id,
        "allow_cross_tenant": peer.allow_cross_tenant,
        "preferred_transport": peer.preferred_transport.value,
        "poll_interval_seconds": peer.poll_interval_seconds,
        "auth": {
            "type": peer.auth.type.value,
            "token_env": peer.auth.token_env,
            "api_key_header": peer.auth.api_key_header,
            "provider": peer.auth.provider,
            "scopes": list(peer.auth.scopes),
            "client_id_env": peer.auth.client_id_env,
            "token_url": peer.auth.token_url,
            "cert_path": peer.auth.cert_path,
            "key_path": peer.auth.key_path,
        },
    }


def _peer_from_dict(data: dict) -> A2aPeer | None:
    try:
        auth_data = data.get("auth", {}) or {}
        auth = A2aAuth(
            type=A2aAuthType(auth_data.get("type", "none")),
            token_env=auth_data.get("token_env"),
            api_key_header=auth_data.get("api_key_header"),
            provider=auth_data.get("provider"),
            scopes=tuple(auth_data.get("scopes") or ()),
            client_id_env=auth_data.get("client_id_env"),
            token_url=auth_data.get("token_url"),
            cert_path=auth_data.get("cert_path"),
            key_path=auth_data.get("key_path"),
        )
        return A2aPeer(
            name=str(data["name"]),
            base_url=str(data["base_url"]),
            agent_card_url=data.get("agent_card_url"),
            description=str(data.get("description", "")),
            tenant_id=str(data.get("tenant_id", "default")),
            allow_cross_tenant=bool(data.get("allow_cross_tenant", False)),
            preferred_transport=A2aTransport(data.get("preferred_transport", "json_rpc")),
            poll_interval_seconds=int(data.get("poll_interval_seconds", 5)),
            auth=auth,
        )
    except (KeyError, ValueError):
        return None
