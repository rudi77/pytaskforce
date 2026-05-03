"""ACP peer registry implementations."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock

from taskforce.core.domain.acp import AcpAuth, AcpAuthType, AcpPeer


class InMemoryPeerRegistry:
    """Simple in-memory peer registry (primarily for tests)."""

    def __init__(self, peers: list[AcpPeer] | None = None) -> None:
        self._peers: dict[str, AcpPeer] = {}
        self._lock = RLock()
        for peer in peers or []:
            self._peers[peer.name] = peer

    def get(self, name: str) -> AcpPeer | None:
        with self._lock:
            return self._peers.get(name)

    def list(self) -> list[AcpPeer]:
        with self._lock:
            return list(self._peers.values())

    def register(self, peer: AcpPeer) -> None:
        with self._lock:
            self._peers[peer.name] = peer

    def remove(self, name: str) -> None:
        with self._lock:
            self._peers.pop(name, None)


class FilePeerRegistry(InMemoryPeerRegistry):
    """Peer registry backed by a JSON file on disk."""

    def __init__(self, work_dir: str = ".taskforce") -> None:
        super().__init__()
        self._path = Path(work_dir) / "acp_peers.json"
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
        self._path.write_text(json.dumps(payload, indent=2))
        # The file may hold literal bearer tokens when callers skip token_env.
        try:
            self._path.chmod(0o600)
        except OSError:  # pragma: no cover - non-POSIX filesystems
            pass

    def register(self, peer: AcpPeer) -> None:
        super().register(peer)
        self._save()

    def remove(self, name: str) -> None:
        super().remove(name)
        self._save()


class EnvPeerRegistry(InMemoryPeerRegistry):
    """Registry that resolves bearer tokens from environment variables.

    Wraps another registry (typically ``FilePeerRegistry``) and rewrites
    ``AcpAuth.token_env`` into a resolved ``token`` on read.
    """

    def __init__(self, inner: InMemoryPeerRegistry) -> None:
        super().__init__()
        self._inner = inner

    def get(self, name: str) -> AcpPeer | None:
        peer = self._inner.get(name)
        if peer is None:
            return None
        return _resolve_env_auth(peer)

    def list(self) -> list[AcpPeer]:
        return [_resolve_env_auth(p) for p in self._inner.list()]

    def register(self, peer: AcpPeer) -> None:
        self._inner.register(peer)

    def remove(self, name: str) -> None:
        self._inner.remove(name)


def _resolve_env_auth(peer: AcpPeer) -> AcpPeer:
    if peer.auth.type != AcpAuthType.BEARER or not peer.auth.token_env:
        return peer
    token = os.getenv(peer.auth.token_env)
    if not token:
        return peer
    return AcpPeer(
        name=peer.name,
        base_url=peer.base_url,
        agent=peer.agent,
        description=peer.description,
        tenant_id=peer.tenant_id,
        allow_cross_tenant=peer.allow_cross_tenant,
        auth=AcpAuth(
            type=AcpAuthType.BEARER,
            token_env=peer.auth.token_env,
            token=token,
        ),
    )


def _peer_to_dict(peer: AcpPeer) -> dict:
    return {
        "name": peer.name,
        "base_url": peer.base_url,
        "agent": peer.agent,
        "description": peer.description,
        "tenant_id": peer.tenant_id,
        "allow_cross_tenant": peer.allow_cross_tenant,
        "auth": {
            "type": peer.auth.type.value,
            "token_env": peer.auth.token_env,
            "cert_path": peer.auth.cert_path,
            "key_path": peer.auth.key_path,
        },
    }


def _peer_from_dict(data: dict) -> AcpPeer | None:
    try:
        auth_data = data.get("auth", {}) or {}
        auth = AcpAuth(
            type=AcpAuthType(auth_data.get("type", "none")),
            token_env=auth_data.get("token_env"),
            cert_path=auth_data.get("cert_path"),
            key_path=auth_data.get("key_path"),
        )
        return AcpPeer(
            name=str(data["name"]),
            base_url=str(data["base_url"]),
            agent=str(data["agent"]),
            description=str(data.get("description", "")),
            tenant_id=str(data.get("tenant_id", "default")),
            allow_cross_tenant=bool(data.get("allow_cross_tenant", False)),
            auth=auth,
        )
    except (KeyError, ValueError):
        return None
