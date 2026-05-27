"""Tests for the A2aService application facade."""

from __future__ import annotations

from pathlib import Path

import pytest

from taskforce.application.a2a_service import (
    build_a2a_runtime_for_tools,
    build_a2a_service,
    delete_persisted_peer,
    get_persisted_peer,
    upsert_persisted_peer,
)
from taskforce.application.config_schema import A2aConfigSchema, A2aPeerSchema


def test_build_a2a_service_returns_none_without_config() -> None:
    assert build_a2a_service(None) is None


def test_build_a2a_service_loads_peers_and_registers_them(tmp_path: Path) -> None:
    raw = {
        "server": {"enabled": False, "host": "127.0.0.1", "port": 9000},
        "peers": [
            {
                "name": "coder",
                "base_url": "http://coder:9000",
                "auth": {"type": "bearer", "token_env": "A2A_CODER_TOKEN"},
            }
        ],
    }
    service = build_a2a_service(raw, work_dir=str(tmp_path))
    assert service is not None
    assert service.is_server_enabled is False

    peers = service.list_peers()
    assert [p.name for p in peers] == ["coder"]


def test_build_a2a_service_accepts_validated_schema(tmp_path: Path) -> None:
    config = A2aConfigSchema()
    service = build_a2a_service(config, work_dir=str(tmp_path))
    assert service is not None


def test_persisted_peer_crud_round_trip(tmp_path: Path) -> None:
    schema = A2aPeerSchema(
        name="alpha",
        base_url="http://alpha:9000",
        description="alpha test peer",
    )
    upsert_persisted_peer(schema, work_dir=str(tmp_path))

    loaded = get_persisted_peer("alpha", work_dir=str(tmp_path))
    assert loaded is not None
    assert loaded.base_url == "http://alpha:9000"

    assert delete_persisted_peer("alpha", work_dir=str(tmp_path)) is True
    assert get_persisted_peer("alpha", work_dir=str(tmp_path)) is None


def test_upsert_overwrite_false_raises_on_existing(tmp_path: Path) -> None:
    schema = A2aPeerSchema(name="dup", base_url="http://a:9000")
    upsert_persisted_peer(schema, work_dir=str(tmp_path))
    with pytest.raises(FileExistsError):
        upsert_persisted_peer(schema, work_dir=str(tmp_path), overwrite=False)


def test_build_runtime_for_tools_returns_none_when_no_a2a_block(tmp_path: Path) -> None:
    assert build_a2a_runtime_for_tools({}, work_dir=str(tmp_path)) is None
    assert build_a2a_runtime_for_tools(None, work_dir=str(tmp_path)) is None


def test_build_runtime_for_tools_returns_none_when_no_peers(tmp_path: Path) -> None:
    cfg = {"a2a": {"server": {"enabled": False}, "peers": []}}
    assert build_a2a_runtime_for_tools(cfg, work_dir=str(tmp_path)) is None


def test_build_runtime_for_tools_succeeds_with_peers(tmp_path: Path) -> None:
    cfg = {
        "a2a": {
            "server": {"enabled": False},
            "peers": [{"name": "p1", "base_url": "http://p1:9000"}],
        }
    }
    runtime = build_a2a_runtime_for_tools(cfg, work_dir=str(tmp_path))
    assert runtime is not None
    assert runtime.server is None  # client-only mode
    assert any(p.name == "p1" for p in runtime.peers.list())
