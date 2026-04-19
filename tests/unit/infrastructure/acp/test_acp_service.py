"""Tests for the AcpService application facade."""

from __future__ import annotations

from pathlib import Path

from taskforce.application.acp_service import build_acp_service, list_persisted_peers
from taskforce.application.config_schema import AcpConfigSchema
from taskforce.core.domain.acp import AcpAuth, AcpAuthType, AcpPeer
from taskforce.infrastructure.acp.peer_registry import FilePeerRegistry


def test_build_acp_service_returns_none_without_config() -> None:
    assert build_acp_service(None) is None


def test_build_acp_service_loads_peers_and_registers_them(tmp_path: Path) -> None:
    raw = {
        "server": {"enabled": False, "host": "127.0.0.1", "port": 8901},
        "peers": [
            {
                "name": "coder",
                "base_url": "http://coder:8800",
                "agent": "coder",
                "auth": {"type": "bearer", "token_env": "ACP_CODER_TOKEN"},
            }
        ],
        "message_bus": {"transport": "acp", "publish_peers": ["coder"]},
    }
    service = build_acp_service(raw, work_dir=str(tmp_path))
    assert service is not None
    assert service.is_server_enabled is False

    peers = service.list_peers()
    assert [p.name for p in peers] == ["coder"]

    bus = service.build_message_bus()
    assert bus is not None  # transport=acp → AcpMessageBus returned


def test_build_acp_service_accepts_validated_schema(tmp_path: Path) -> None:
    config = AcpConfigSchema()
    service = build_acp_service(config, work_dir=str(tmp_path))
    assert service is not None
    assert service.is_server_enabled is False
    assert service.build_message_bus() is None


def test_list_persisted_peers_returns_file_backed_peers(tmp_path: Path) -> None:
    FilePeerRegistry(work_dir=str(tmp_path)).register(
        AcpPeer(
            name="alpha",
            base_url="http://example",
            agent="alpha-agent",
            auth=AcpAuth(type=AcpAuthType.NONE),
        )
    )
    peers = list_persisted_peers(work_dir=str(tmp_path))
    assert [p.name for p in peers] == ["alpha"]


def test_file_peer_registry_sets_restrictive_permissions(tmp_path: Path) -> None:
    """Registry file must be readable only by the owner (token exposure risk)."""
    import os
    import stat

    registry = FilePeerRegistry(work_dir=str(tmp_path))
    registry.register(AcpPeer(name="p", base_url="http://x", agent="a"))
    mode = stat.S_IMODE(os.stat(tmp_path / "acp_peers.json").st_mode)
    # On POSIX systems the chmod must succeed and produce 0o600.
    if os.name == "posix":
        assert mode == 0o600
