"""Hybrid discovery facade unifying ACP and A2A peer enumeration.

Implements :class:`RemoteAgentDiscoveryProtocol` from
``core/interfaces/remote_agent_discovery.py``. The invocation paths
(``call_acp_agent`` vs ``call_a2a_agent``) stay protocol-specific
because A2A's task lifecycle (artifacts, push, ``input-required``) has
no ACP analogue.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

from taskforce.core.domain.a2a import A2aPeer
from taskforce.core.domain.acp import AcpPeer
from taskforce.core.domain.remote_agent import RemoteAgentDescriptor, RemoteAgentProtocol
from taskforce.infrastructure.a2a.peer_registry import (
    FileA2aPeerRegistry as A2aFileRegistry,
)
from taskforce.infrastructure.acp.peer_registry import FilePeerRegistry as AcpFileRegistry

logger = structlog.get_logger(__name__)


class RemoteAgentDiscoveryService:
    """Cross-protocol peer enumeration + probing.

    Reads from the on-disk ACP + A2A peer registries (the source of
    truth shared by the CLI/REST surfaces). ``probe`` performs a
    network round-trip per peer to populate ``reachable`` and
    ``latency_ms``; off by default so listing stays cheap.
    """

    def __init__(self, *, work_dir: str = ".taskforce") -> None:
        self._work_dir = work_dir

    def list_peers(self, *, probe: bool = False) -> list[RemoteAgentDescriptor]:
        acp_descs = [_describe_acp(p) for p in AcpFileRegistry(work_dir=self._work_dir).list()]
        a2a_descs = [_describe_a2a(p) for p in A2aFileRegistry(work_dir=self._work_dir).list()]
        merged = acp_descs + a2a_descs
        if not probe:
            return _dedup(merged)
        return _dedup(asyncio.run(self._probe_all(merged)))

    async def list_peers_async(self, *, probe: bool = False) -> list[RemoteAgentDescriptor]:
        acp_descs = [_describe_acp(p) for p in AcpFileRegistry(work_dir=self._work_dir).list()]
        a2a_descs = [_describe_a2a(p) for p in A2aFileRegistry(work_dir=self._work_dir).list()]
        merged = acp_descs + a2a_descs
        if not probe:
            return _dedup(merged)
        return _dedup(await self._probe_all(merged))

    async def discover(self, base_url: str) -> RemoteAgentDescriptor | None:
        """Probe ``base_url`` — try A2A's well-known card path first,
        then ACP's ``/agents`` listing. Returns ``None`` when neither
        responds."""
        a2a = await _probe_a2a_url(base_url)
        if a2a is not None:
            return a2a
        return await _probe_acp_url(base_url)

    async def _probe_all(
        self, descriptors: list[RemoteAgentDescriptor]
    ) -> list[RemoteAgentDescriptor]:
        results = await asyncio.gather(
            *[_probe_descriptor(d) for d in descriptors],
            return_exceptions=True,
        )
        return [r for r in results if isinstance(r, RemoteAgentDescriptor)]


def _describe_acp(peer: AcpPeer) -> RemoteAgentDescriptor:
    auth_schemes = (peer.auth.type.value,) if peer.auth.type.value != "none" else ()
    return RemoteAgentDescriptor(
        name=peer.name,
        protocol=RemoteAgentProtocol.ACP,
        base_url=peer.base_url,
        agent=peer.agent,
        description=peer.description,
        capabilities=(peer.agent,),
        auth_schemes=auth_schemes,
        raw={"peer": peer.name, "agent": peer.agent, "tenant_id": peer.tenant_id},
    )


def _describe_a2a(peer: A2aPeer) -> RemoteAgentDescriptor:
    auth_schemes = (peer.auth.type.value,) if peer.auth.type.value != "none" else ()
    return RemoteAgentDescriptor(
        name=peer.name,
        protocol=RemoteAgentProtocol.A2A,
        base_url=peer.base_url,
        agent=None,
        description=peer.description,
        capabilities=(),
        auth_schemes=auth_schemes,
        raw={
            "peer": peer.name,
            "tenant_id": peer.tenant_id,
            "transport": peer.preferred_transport.value,
        },
    )


def _dedup(descriptors: list[RemoteAgentDescriptor]) -> list[RemoteAgentDescriptor]:
    """De-duplicate by (protocol, base_url) keeping the first occurrence."""
    seen: set[tuple[str, str]] = set()
    out: list[RemoteAgentDescriptor] = []
    for d in descriptors:
        key = (d.protocol.value, d.base_url.rstrip("/"))
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


async def _probe_descriptor(d: RemoteAgentDescriptor) -> RemoteAgentDescriptor:
    if d.protocol == RemoteAgentProtocol.A2A:
        probed = await _probe_a2a_url(d.base_url)
    else:
        probed = await _probe_acp_url(d.base_url)
    if probed is None:
        return RemoteAgentDescriptor(
            name=d.name,
            protocol=d.protocol,
            base_url=d.base_url,
            agent=d.agent,
            description=d.description,
            capabilities=d.capabilities,
            auth_schemes=d.auth_schemes,
            reachable=False,
            latency_ms=None,
            raw=d.raw,
        )
    return RemoteAgentDescriptor(
        name=d.name,
        protocol=d.protocol,
        base_url=d.base_url,
        agent=probed.agent or d.agent,
        description=probed.description or d.description,
        capabilities=probed.capabilities or d.capabilities,
        auth_schemes=probed.auth_schemes or d.auth_schemes,
        reachable=True,
        latency_ms=probed.latency_ms,
        raw={**d.raw, **probed.raw},
    )


async def _probe_a2a_url(base_url: str) -> RemoteAgentDescriptor | None:
    try:
        import httpx  # type: ignore[import-not-found]
    except ImportError:
        return None
    url = base_url.rstrip("/") + "/.well-known/agent-card.json"
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=5.0) as http:
            resp = await http.get(url)
            if resp.status_code >= 400:
                return None
            data = resp.json()
    except Exception:  # noqa: BLE001 - swallow for discovery
        return None
    latency = int((time.perf_counter() - start) * 1000)
    skills = [str(s.get("id", "")) for s in (data.get("skills") or [])]
    auth_schemes = tuple(_extract_a2a_auth_schemes(data))
    return RemoteAgentDescriptor(
        name=str(data.get("name", base_url)),
        protocol=RemoteAgentProtocol.A2A,
        base_url=base_url,
        agent=str(data.get("name", "")),
        description=str(data.get("description", "")),
        capabilities=tuple(s for s in skills if s),
        auth_schemes=auth_schemes,
        reachable=True,
        latency_ms=latency,
        raw={"card": data},
    )


def _extract_a2a_auth_schemes(card: dict[str, Any]) -> list[str]:
    schemes = card.get("security_schemes") or card.get("securitySchemes") or {}
    out: list[str] = []
    for name, body in schemes.items():
        if not isinstance(body, dict):
            out.append(name)
            continue
        if "oauth2_security_scheme" in body or "oauth2SecurityScheme" in body:
            out.append("oauth2")
        elif "http_auth_security_scheme" in body or "httpAuthSecurityScheme" in body:
            out.append("bearer")
        elif "api_key_security_scheme" in body or "apiKeySecurityScheme" in body:
            out.append("api_key")
        elif "open_id_connect_security_scheme" in body or "openIdConnectSecurityScheme" in body:
            out.append("oidc")
        elif "mtls_security_scheme" in body or "mtlsSecurityScheme" in body:
            out.append("mtls")
        else:
            out.append(name)
    return out


async def _probe_acp_url(base_url: str) -> RemoteAgentDescriptor | None:
    try:
        import httpx  # type: ignore[import-not-found]
    except ImportError:
        return None
    url = base_url.rstrip("/") + "/agents"
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=5.0) as http:
            resp = await http.get(url)
            if resp.status_code >= 400:
                return None
            data = resp.json()
    except Exception:  # noqa: BLE001
        return None
    latency = int((time.perf_counter() - start) * 1000)
    agents = data.get("agents") if isinstance(data, dict) else data
    if not isinstance(agents, list) or not agents:
        return RemoteAgentDescriptor(
            name=base_url,
            protocol=RemoteAgentProtocol.ACP,
            base_url=base_url,
            agent=None,
            reachable=True,
            latency_ms=latency,
        )
    first = agents[0]
    name = first.get("name") if isinstance(first, dict) else ""
    return RemoteAgentDescriptor(
        name=str(name or base_url),
        protocol=RemoteAgentProtocol.ACP,
        base_url=base_url,
        agent=str(name) if name else None,
        description=str(first.get("description", "") if isinstance(first, dict) else ""),
        capabilities=tuple(
            a.get("name", "") for a in agents if isinstance(a, dict) and a.get("name")
        ),
        reachable=True,
        latency_ms=latency,
        raw={"agents": agents},
    )
