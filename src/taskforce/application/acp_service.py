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
        bus_factory: Any | None = None,
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
        self._bus_factory = bus_factory

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
