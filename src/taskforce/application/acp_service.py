"""High-level facade for ACP integration.

Builds an :class:`AcpRuntime` from profile configuration, registers peers,
optionally swaps the message bus implementation and exposes convenience
methods for the CLI / API layer.

This service is **optional** — profiles without an ``acp:`` section work
unchanged. Nothing in the core or main infrastructure wiring depends on
``acp-sdk`` at import time.
"""

from __future__ import annotations

from typing import Any

import structlog

from taskforce.application.config_schema import (
    AcpConfigSchema,
    AcpPeerSchema,
    AcpServerSchema,
)
from taskforce.core.domain.acp import (
    AcpAgentManifest,
    AcpAuth,
    AcpAuthType,
    AcpPeer,
)
from taskforce.core.interfaces.messaging import MessageBusProtocol
from taskforce.infrastructure.acp.acp_message_bus import AcpMessageBus
from taskforce.infrastructure.acp.peer_registry import (
    EnvPeerRegistry,
    FilePeerRegistry,
)
from taskforce.infrastructure.acp.runtime import AcpRuntime

logger = structlog.get_logger(__name__)


class AcpService:
    """Application-layer facade bundling ACP runtime + bus integration."""

    def __init__(
        self,
        config: AcpConfigSchema,
        *,
        work_dir: str = ".taskforce",
    ) -> None:
        self._config = config
        self._work_dir = work_dir
        self._file_registry = FilePeerRegistry(work_dir=work_dir)
        self._peers = EnvPeerRegistry(self._file_registry)
        self._runtime = AcpRuntime(
            host=config.server.host,
            port=config.server.port,
            peers=self._peers,
        )
        self._bus: MessageBusProtocol | None = None

        self._load_peers_from_config(config.peers)

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    @property
    def runtime(self) -> AcpRuntime:
        return self._runtime

    @property
    def bus(self) -> MessageBusProtocol | None:
        return self._bus

    @property
    def is_server_enabled(self) -> bool:
        return self._config.server.enabled

    async def start(self) -> None:
        if self._config.server.enabled:
            await self._runtime.start()

    async def stop(self) -> None:
        await self._runtime.stop()

    # ------------------------------------------------------------------ #
    # Configuration helpers
    # ------------------------------------------------------------------ #

    def build_message_bus(self) -> MessageBusProtocol | None:
        """Return an :class:`AcpMessageBus` when the profile selects it."""
        if self._config.message_bus.transport != "acp":
            return None
        bus = AcpMessageBus(
            self._runtime,
            publish_peers=list(self._config.message_bus.publish_peers),
        )
        self._bus = bus
        # Auto-register subscription agents for configured topics.
        for topic in self._config.message_bus.subscribe_topics:
            # Creating the subscription lazily triggers handler registration.
            bus._ensure_registered(  # noqa: SLF001 - internal setup path
                topic, bus._queues.setdefault(topic, _empty_queue())
            )
        return bus

    def register_profile_agent(
        self,
        handler: Any,
        *,
        profile_name: str,
        description: str = "",
    ) -> None:
        """Expose the profile's main agent via ACP if configured to do so."""
        if not self._config.server.expose_profile:
            return
        name = self._config.server.agent_name or profile_name
        manifest = AcpAgentManifest(
            name=name,
            description=description or f"Taskforce profile {profile_name!r}",
            metadata={"source": "profile", "profile": profile_name},
        )
        self._runtime.register_agent(manifest, handler)

    def _load_peers_from_config(self, peers: list[AcpPeerSchema]) -> None:
        for raw in peers:
            auth = AcpAuth(
                type=AcpAuthType(raw.auth.type),
                token_env=raw.auth.token_env,
                token=raw.auth.token,
                cert_path=raw.auth.cert_path,
                key_path=raw.auth.key_path,
            )
            peer = AcpPeer(
                name=raw.name,
                base_url=raw.base_url,
                agent=raw.agent,
                description=raw.description,
                auth=auth,
            )
            self._peers.register(peer)

    # ------------------------------------------------------------------ #
    # Helpers for CLI / API
    # ------------------------------------------------------------------ #

    def list_peers(self) -> list[AcpPeer]:
        return self._peers.list()

    async def call_peer(
        self,
        peer_name: str,
        mission: str,
        *,
        session_id: str | None = None,
        stream: bool = False,
    ) -> Any:
        return await self._runtime.call(peer_name, mission, session_id=session_id, stream=stream)


def _empty_queue():  # noqa: ANN202
    import asyncio

    return asyncio.Queue()


def build_acp_service(
    config: dict[str, Any] | AcpConfigSchema | None,
    *,
    work_dir: str = ".taskforce",
) -> AcpService | None:
    """Factory used by higher-level builders / CLI commands."""
    if config is None:
        return None
    if isinstance(config, dict):
        config = AcpConfigSchema(**config)
    # Even when disabled, still build peers so the CLI can list them.
    return AcpService(config, work_dir=work_dir)


def acp_server_schema_from_dict(data: dict[str, Any]) -> AcpServerSchema:
    """Utility for CLI code paths that only have raw config dicts."""
    return AcpServerSchema(**data)


def list_persisted_peers(work_dir: str = ".taskforce") -> list[AcpPeer]:
    """Return all peers persisted under ``<work_dir>/acp_peers.json``.

    Application-layer entry point used by the API so route handlers do
    not need to import infrastructure adapters directly.
    """
    return FilePeerRegistry(work_dir=work_dir).list()


def get_persisted_peer(name: str, work_dir: str = ".taskforce") -> AcpPeer | None:
    """Return a single peer by name or ``None`` if it does not exist."""
    return FilePeerRegistry(work_dir=work_dir).get(name)


def upsert_persisted_peer(
    peer: AcpPeer | dict[str, Any] | AcpPeerSchema,
    *,
    work_dir: str = ".taskforce",
    overwrite: bool = True,
) -> AcpPeer:
    """Persist (or update) an ACP peer in the on-disk registry.

    Args:
        peer: ``AcpPeer`` domain model, validated ``AcpPeerSchema``, or the
            raw dict that came in from the API.
        work_dir: Directory holding ``acp_peers.json`` (default
            ``.taskforce``). Tests pass a temp dir.
        overwrite: When ``False``, raises :class:`FileExistsError` if a
            peer with the same name already exists.

    Returns:
        The :class:`AcpPeer` that ended up on disk.
    """
    if isinstance(peer, AcpPeerSchema):
        domain = _peer_from_schema(peer)
    elif isinstance(peer, dict):
        domain = _peer_from_schema(AcpPeerSchema(**peer))
    else:
        domain = peer

    registry = FilePeerRegistry(work_dir=work_dir)
    if not overwrite and registry.get(domain.name) is not None:
        raise FileExistsError(f"ACP peer '{domain.name}' already exists")
    registry.register(domain)
    return domain


def delete_persisted_peer(name: str, *, work_dir: str = ".taskforce") -> bool:
    """Remove a peer from the on-disk registry. Returns ``True`` if removed."""
    registry = FilePeerRegistry(work_dir=work_dir)
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
    """Best-effort connectivity check for a registered ACP peer.

    Resolves the peer's auth (env-backed bearer included) and probes its
    base URL with an HTTP HEAD/GET request. Returns a serialisable dict
    so the route can pass it through unchanged.
    """
    import time

    inner = FilePeerRegistry(work_dir=work_dir)
    resolved = EnvPeerRegistry(inner).get(name)
    if resolved is None:
        return {
            "ok": False,
            "error": f"peer '{name}' not found",
            "latency_ms": 0,
        }

    headers: dict[str, str] = {}
    if (
        resolved.auth
        and resolved.auth.type == AcpAuthType.BEARER
        and resolved.auth.token
    ):
        headers["Authorization"] = f"Bearer {resolved.auth.token}"

    target = resolved.base_url.rstrip("/")
    start = time.perf_counter()
    try:
        import aiohttp

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as session:
            try:
                async with session.head(target, headers=headers) as resp:
                    status = resp.status
            except aiohttp.ClientResponseError as exc:
                status = exc.status
            except (aiohttp.ClientError, ConnectionError) as exc:
                return {
                    "ok": False,
                    "error": str(exc),
                    "latency_ms": int((time.perf_counter() - start) * 1000),
                }
        latency = int((time.perf_counter() - start) * 1000)
        # Reachability — any HTTP response means the host is up. But when the
        # peer requires auth, 401/403 is *not* a success: the user thinks
        # they are reachable when they're really seeing an auth rejection
        # (typically because ``token_env`` points at an unset env var).
        requires_auth = (
            resolved.auth is not None and resolved.auth.type != AcpAuthType.NONE
        )
        if requires_auth and status in (401, 403):
            return {
                "ok": False,
                "status_code": status,
                "latency_ms": latency,
                "agent": resolved.agent,
                "base_url": resolved.base_url,
                "error": (
                    f"auth rejected ({status}) — check token_env / token "
                    f"for peer '{name}'"
                ),
            }
        ok = status < 500
        return {
            "ok": ok,
            "status_code": status,
            "latency_ms": latency,
            "agent": resolved.agent,
            "base_url": resolved.base_url,
        }
    except ImportError:
        return {
            "ok": False,
            "error": "aiohttp is required for connectivity tests",
            "latency_ms": 0,
        }
    except Exception as exc:  # noqa: BLE001 — surfaced to the API
        return {
            "ok": False,
            "error": str(exc),
            "latency_ms": int((time.perf_counter() - start) * 1000),
        }


def _peer_from_schema(schema: AcpPeerSchema) -> AcpPeer:
    auth = AcpAuth(
        type=AcpAuthType(schema.auth.type),
        token_env=schema.auth.token_env,
        token=schema.auth.token,
        cert_path=schema.auth.cert_path,
        key_path=schema.auth.key_path,
    )
    return AcpPeer(
        name=schema.name,
        base_url=schema.base_url,
        agent=schema.agent,
        description=schema.description,
        auth=auth,
    )


def build_acp_runtime_for_tools(
    base_config: dict[str, Any] | None,
    *,
    work_dir: str = ".taskforce",
) -> AcpRuntime | None:
    """Build a client-only ``AcpRuntime`` from a profile config.

    Used by the agent factory to make ``call_acp_agent`` available to
    agents whose profile lists peers under ``acp.peers`` — **without**
    starting a local ACP server. Returns ``None`` when the profile has
    no ``acp`` section or no peers configured.
    """
    if not base_config:
        return None
    raw = base_config.get("acp")
    if not raw:
        return None
    service = build_acp_service(raw, work_dir=work_dir)
    if service is None or not service.list_peers():
        return None
    return service.runtime
