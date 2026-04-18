"""Tests for the AcpService application facade."""

from __future__ import annotations

from pathlib import Path

from taskforce.application.acp_service import build_acp_service
from taskforce.application.config_schema import AcpConfigSchema


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
