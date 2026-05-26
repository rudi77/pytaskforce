"""Tests for the Hybrid RemoteAgentDiscoveryService."""

from __future__ import annotations

from pathlib import Path

from taskforce.application.remote_agent_discovery_service import (
    RemoteAgentDiscoveryService,
)
from taskforce.core.domain.a2a import A2aPeer
from taskforce.core.domain.acp import AcpPeer
from taskforce.core.domain.remote_agent import RemoteAgentProtocol
from taskforce.infrastructure.a2a.peer_registry import FileA2aPeerRegistry
from taskforce.infrastructure.acp.peer_registry import FilePeerRegistry


def test_list_peers_merges_acp_and_a2a(tmp_path: Path) -> None:
    FilePeerRegistry(work_dir=str(tmp_path)).register(
        AcpPeer(name="acp-1", base_url="http://acp:8800", agent="agent-a")
    )
    FileA2aPeerRegistry(work_dir=str(tmp_path)).register(
        A2aPeer(name="a2a-1", base_url="http://a2a:9000")
    )

    service = RemoteAgentDiscoveryService(work_dir=str(tmp_path))
    descriptors = service.list_peers()
    by_protocol = {d.protocol for d in descriptors}
    assert RemoteAgentProtocol.ACP in by_protocol
    assert RemoteAgentProtocol.A2A in by_protocol
    assert {d.name for d in descriptors} == {"acp-1", "a2a-1"}


def test_list_peers_dedups_by_base_url(tmp_path: Path) -> None:
    FilePeerRegistry(work_dir=str(tmp_path)).register(
        AcpPeer(name="acp-1", base_url="http://shared:9000", agent="a")
    )
    FilePeerRegistry(work_dir=str(tmp_path)).register(
        AcpPeer(name="acp-2", base_url="http://shared:9000/", agent="b")
    )

    service = RemoteAgentDiscoveryService(work_dir=str(tmp_path))
    descriptors = service.list_peers()
    bases = [d.base_url for d in descriptors]
    assert len(bases) == 1


def test_list_peers_returns_empty_when_no_registries(tmp_path: Path) -> None:
    service = RemoteAgentDiscoveryService(work_dir=str(tmp_path))
    assert service.list_peers() == []


def test_describes_acp_with_agent_name(tmp_path: Path) -> None:
    FilePeerRegistry(work_dir=str(tmp_path)).register(
        AcpPeer(name="acp-1", base_url="http://acp:8800", agent="coder")
    )
    service = RemoteAgentDiscoveryService(work_dir=str(tmp_path))
    [descriptor] = service.list_peers()
    assert descriptor.protocol == RemoteAgentProtocol.ACP
    assert descriptor.agent == "coder"


def test_describes_a2a_without_agent_name_until_probed(tmp_path: Path) -> None:
    FileA2aPeerRegistry(work_dir=str(tmp_path)).register(
        A2aPeer(name="a2a-1", base_url="http://a2a:9000")
    )
    service = RemoteAgentDiscoveryService(work_dir=str(tmp_path))
    [descriptor] = service.list_peers()
    assert descriptor.protocol == RemoteAgentProtocol.A2A
    assert descriptor.agent is None
