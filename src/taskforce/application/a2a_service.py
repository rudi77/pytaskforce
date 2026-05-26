"""High-level facade for A2A integration.

Builds an :class:`A2aRuntime` from profile configuration, registers
peers and exposes convenience methods for the CLI / API layer.

This service is **optional** — profiles without an ``a2a:`` section
work unchanged. Nothing in the core or main infrastructure wiring
depends on ``a2a-sdk`` at import time; the lazy SDK loader in
``infrastructure/a2a/_sdk.py`` raises ``A2aSdkNotInstalledError`` only
when the runtime is actually used.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

from taskforce.application.config_schema import (
    A2aConfigSchema,
    A2aPeerSchema,
    A2aServerSchema,
)
from taskforce.core.domain.a2a import (
    A2aAuth,
    A2aAuthType,
    A2aPeer,
    A2aTransport,
)
from taskforce.infrastructure.a2a.peer_registry import (
    EnvA2aPeerRegistry,
    FileA2aPeerRegistry,
)
from taskforce.infrastructure.a2a.runtime import A2aRuntime

logger = structlog.get_logger(__name__)


class A2aService:
    """Application-layer facade for A2A runtime + peer wiring."""

    def __init__(
        self,
        config: A2aConfigSchema,
        *,
        work_dir: str = ".taskforce",
        tenant_id_provider: Callable[[], str] | None = None,
        auth_manager: Any | None = None,
    ) -> None:
        self._config = config
        self._work_dir = work_dir
        self._file_registry = FileA2aPeerRegistry(work_dir=work_dir)
        self._peers = EnvA2aPeerRegistry(self._file_registry)
        server = self._build_server_if_enabled(config)
        client = self._build_client(config, work_dir, auth_manager)
        self._runtime = A2aRuntime(
            server=server,
            client=client,
            peers=self._peers,
            tenant_id_provider=tenant_id_provider,
        )
        self._load_peers_from_config(config.peers)

    @staticmethod
    def _build_client(
        config: A2aConfigSchema,
        work_dir: str,
        auth_manager: Any | None,
    ) -> Any:
        from taskforce.infrastructure.a2a.a2a_client import A2aClient

        artifact_dir = config.artifacts.work_dir or f"{work_dir.rstrip('/')}/a2a_artifacts"
        return A2aClient(auth_manager=auth_manager, artifact_dir=artifact_dir)

    @staticmethod
    def _build_server_if_enabled(config: A2aConfigSchema) -> Any | None:
        if not config.server.enabled:
            return None
        from taskforce.infrastructure.a2a.a2a_server import A2aServer

        return A2aServer(host=config.server.host, port=config.server.port)

    @property
    def runtime(self) -> A2aRuntime:
        return self._runtime

    @property
    def is_server_enabled(self) -> bool:
        return self._config.server.enabled

    async def start(self) -> None:
        if self._config.server.enabled:
            await self._runtime.start()

    async def stop(self) -> None:
        await self._runtime.stop()

    def list_peers(self) -> list[A2aPeer]:
        return self._peers.list()

    def register_profile_agent(
        self,
        handler: Any,
        *,
        profile_name: str,
        description: str = "",
        tools: list[str] | None = None,
    ) -> None:
        """Expose the profile's main agent via A2A if configured to do so.

        Builds the AgentCard from profile metadata + server config and
        registers it together with the mission handler on the embedded
        A2A server. No-op when ``a2a.server.expose_profile`` is False or
        the server is disabled.
        """
        if not self._config.server.expose_profile or not self._config.server.enabled:
            return
        from taskforce.infrastructure.a2a.agent_card_builder import build_agent_card

        base_url = f"http://{self._config.server.host}:{self._config.server.port}"
        card = build_agent_card(
            profile_name=profile_name,
            description=description,
            base_url=base_url,
            server_config=self._config.server,
            tools=tools or [],
        )
        self._runtime.register_agent(card, handler)

    async def call_peer(
        self,
        peer_name: str,
        mission: str,
        *,
        session_id: str | None = None,
        stream: bool = False,
    ) -> Any:
        return await self._runtime.call(peer_name, mission, session_id=session_id, stream=stream)

    def _load_peers_from_config(self, peers: list[A2aPeerSchema]) -> None:
        for raw in peers:
            peer = _peer_from_schema(raw)
            self._peers.register(peer)


def build_a2a_service(
    config: dict[str, Any] | A2aConfigSchema | None,
    *,
    work_dir: str = ".taskforce",
    tenant_id_provider: Callable[[], str] | None = None,
    auth_manager: Any | None = None,
) -> A2aService | None:
    """Factory used by higher-level builders / CLI commands."""
    if config is None:
        return None
    if isinstance(config, dict):
        config = A2aConfigSchema(**config)
    return A2aService(
        config,
        work_dir=work_dir,
        tenant_id_provider=tenant_id_provider,
        auth_manager=auth_manager,
    )


def a2a_server_schema_from_dict(data: dict[str, Any]) -> A2aServerSchema:
    """Utility for CLI code paths that only have raw config dicts."""
    return A2aServerSchema(**data)


def list_persisted_peers(work_dir: str = ".taskforce") -> list[A2aPeer]:
    """Return all peers persisted under ``<work_dir>/a2a_peers.json``."""
    return FileA2aPeerRegistry(work_dir=work_dir).list()


def get_persisted_peer(name: str, work_dir: str = ".taskforce") -> A2aPeer | None:
    """Return a single peer by name or ``None`` if it does not exist."""
    return FileA2aPeerRegistry(work_dir=work_dir).get(name)


def upsert_persisted_peer(
    peer: A2aPeer | dict[str, Any] | A2aPeerSchema,
    *,
    work_dir: str = ".taskforce",
    overwrite: bool = True,
) -> A2aPeer:
    """Persist (or update) an A2A peer in the on-disk registry."""
    if isinstance(peer, A2aPeerSchema):
        domain = _peer_from_schema(peer)
    elif isinstance(peer, dict):
        domain = _peer_from_schema(A2aPeerSchema(**peer))
    else:
        domain = peer

    registry = FileA2aPeerRegistry(work_dir=work_dir)
    if not overwrite and registry.get(domain.name) is not None:
        raise FileExistsError(f"A2A peer '{domain.name}' already exists")
    registry.register(domain)
    return domain


def delete_persisted_peer(name: str, *, work_dir: str = ".taskforce") -> bool:
    """Remove a peer from the on-disk registry. Returns ``True`` if removed."""
    registry = FileA2aPeerRegistry(work_dir=work_dir)
    if registry.get(name) is None:
        return False
    registry.remove(name)
    return True


async def ping_peer(
    name: str,
    *,
    work_dir: str = ".taskforce",
    timeout: float = 5.0,
) -> dict[str, Any]:
    """Best-effort connectivity check — fetches the AgentCard.

    Returns a serialisable dict so the API route can pass it through
    unchanged. A successful card resolution counts as "reachable".
    """
    import time

    inner = FileA2aPeerRegistry(work_dir=work_dir)
    resolved = EnvA2aPeerRegistry(inner).get(name)
    if resolved is None:
        return {"ok": False, "error": f"peer '{name}' not found", "latency_ms": 0}

    start = time.perf_counter()
    try:
        from taskforce.infrastructure.a2a.a2a_client import A2aClient

        client = A2aClient()
        try:
            card = await client.fetch_agent_card(resolved)
        finally:
            await client.close()
        latency = int((time.perf_counter() - start) * 1000)
        return {
            "ok": True,
            "agent": card.name,
            "version": card.version,
            "base_url": resolved.base_url,
            "skills": [s.id for s in card.skills],
            "latency_ms": latency,
        }
    except Exception as exc:  # noqa: BLE001 — surfaced to the API
        return {
            "ok": False,
            "error": str(exc),
            "latency_ms": int((time.perf_counter() - start) * 1000),
        }


def _peer_from_schema(schema: A2aPeerSchema) -> A2aPeer:
    auth = A2aAuth(
        type=A2aAuthType(schema.auth.type),
        token_env=schema.auth.token_env,
        token=schema.auth.token,
        api_key_header=schema.auth.api_key_header,
        provider=schema.auth.provider,
        scopes=tuple(schema.auth.scopes),
        client_id_env=schema.auth.client_id_env,
        token_url=schema.auth.token_url,
        cert_path=schema.auth.cert_path,
        key_path=schema.auth.key_path,
    )
    return A2aPeer(
        name=schema.name,
        base_url=schema.base_url,
        agent_card_url=schema.agent_card_url,
        description=schema.description,
        tenant_id=schema.tenant_id,
        allow_cross_tenant=schema.allow_cross_tenant,
        preferred_transport=A2aTransport(schema.preferred_transport),
        poll_interval_seconds=schema.poll_interval_seconds,
        auth=auth,
    )


def build_a2a_runtime_for_tools(
    base_config: dict[str, Any] | None,
    *,
    work_dir: str = ".taskforce",
    auth_manager: Any | None = None,
) -> A2aRuntime | None:
    """Build a client-only ``A2aRuntime`` from a profile config.

    Used by the agent factory to make ``call_a2a_agent`` available to
    agents whose profile lists peers under ``a2a.peers`` — **without**
    starting a local A2A server. Returns ``None`` when the profile has
    no ``a2a`` section or no peers configured.
    """
    if not base_config:
        return None
    raw = base_config.get("a2a")
    if not raw:
        return None
    from taskforce.application.infrastructure_overrides import (
        get_acp_tenant_id_provider,
    )

    service = build_a2a_service(
        raw,
        work_dir=work_dir,
        tenant_id_provider=get_acp_tenant_id_provider(),
        auth_manager=auth_manager,
    )
    if service is None or not service.list_peers():
        return None
    return service.runtime
