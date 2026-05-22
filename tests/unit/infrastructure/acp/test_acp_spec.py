"""Spec-coverage tests for the Agent Communication Protocol (ACP).

Covers the ACP claims that lacked a focused test: the no-SDK import
guarantee, runtime start/stop idempotency, message-bus inbox-agent
registration, and the peer-CRUD route status codes (bare-app, so the
enterprise auth middleware is not involved).

Spec: docs/spec/acp.md — tests tagged @pytest.mark.spec("acp.*").
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.infrastructure.acp.acp_message_bus import AcpMessageBus, _topic_to_agent
from taskforce.infrastructure.acp.peer_registry import InMemoryPeerRegistry
from taskforce.infrastructure.acp.runtime import AcpRuntime


# ---------------------------------------------------------------------------
# Lazy SDK import
# ---------------------------------------------------------------------------


@pytest.mark.spec("acp.no_acp_section_works_without_sdk")
def test_no_acp_section_works_without_sdk() -> None:
    """Importing ``taskforce`` never imports ``acp_sdk``.

    ACP code paths load lazily — a plain install (or a profile with no
    ``acp:`` block) must work without the optional ``acp-sdk`` dependency.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import taskforce, sys; "
            "assert 'acp_sdk' not in sys.modules, "
            "'importing taskforce must not pull in acp_sdk'",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# Runtime lifecycle idempotency
# ---------------------------------------------------------------------------


def _runtime_with_mock_server() -> tuple[AcpRuntime, MagicMock]:
    server = MagicMock()
    server.is_running = False
    server.start = AsyncMock()
    server.stop = AsyncMock()
    server.registered_manifests.return_value = []
    client = MagicMock()
    client.close = AsyncMock()
    runtime = AcpRuntime(
        server=server, client=client, peers=InMemoryPeerRegistry([])
    )
    return runtime, server


@pytest.mark.spec("acp.runtime_start_stop_idempotent")
@pytest.mark.asyncio
async def test_runtime_start_stop_idempotent() -> None:
    """Repeated start()/stop() calls do not double-start or leak sessions."""
    runtime, server = _runtime_with_mock_server()

    await runtime.start()
    await runtime.start()
    server.start.assert_called_once()

    await runtime.stop()
    await runtime.stop()
    server.stop.assert_called_once()


# ---------------------------------------------------------------------------
# Message bus subscribe → inbox agent
# ---------------------------------------------------------------------------


@pytest.mark.spec("acp.message_bus_subscribe_registers_inbox_agent")
@pytest.mark.asyncio
async def test_message_bus_subscribe_registers_inbox_agent() -> None:
    """subscribe(topic) registers a local inbox agent on the ACP server."""
    import asyncio

    runtime, server = _runtime_with_mock_server()
    bus = AcpMessageBus(runtime)

    iterator = bus.subscribe("tasks.new")

    async def _drain() -> None:
        async for _ in iterator:
            return

    task = asyncio.create_task(_drain())
    await asyncio.sleep(0)  # let subscribe run up to its first queue.get()
    task.cancel()

    server.register_agent.assert_called_once()
    manifest = server.register_agent.call_args.args[0]
    assert manifest.name == _topic_to_agent("tasks.new")


# ---------------------------------------------------------------------------
# Peer-CRUD route status codes (bare app)
# ---------------------------------------------------------------------------


def _peer_payload(name: str = "remote-butler") -> dict:
    return {
        "name": name,
        "base_url": "http://remote.local:8800",
        "agent": "butler",
        "description": "Remote butler",
        "auth": {"type": "none"},
    }


@pytest.fixture
def acp_client(tmp_path: Path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient

    from taskforce.api.exception_handlers import taskforce_http_exception_handler
    from taskforce.api.routes import acp as acp_route

    monkeypatch.setenv("TASKFORCE_ACP_WORK_DIR", str(tmp_path))

    app = FastAPI()
    app.add_exception_handler(HTTPException, taskforce_http_exception_handler)
    app.include_router(acp_route.router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.spec("acp.post_peers_duplicate_returns_409")
def test_post_peers_duplicate_returns_409(acp_client) -> None:
    """Creating a peer whose name already exists returns 409."""
    first = acp_client.post("/api/v1/acp/peers", json=_peer_payload())
    assert first.status_code == 201

    second = acp_client.post("/api/v1/acp/peers", json=_peer_payload())
    assert second.status_code == 409


@pytest.mark.spec("acp.delete_peer_missing_returns_404")
def test_delete_peer_missing_returns_404(acp_client) -> None:
    """Deleting a peer that does not exist returns 404."""
    response = acp_client.delete("/api/v1/acp/peers/does-not-exist")
    assert response.status_code == 404


@pytest.mark.spec("acp.test_peer_missing_returns_404")
def test_test_peer_missing_returns_404(acp_client) -> None:
    """A connectivity probe of an unknown peer returns 404."""
    response = acp_client.post("/api/v1/acp/peers/does-not-exist/test")
    assert response.status_code == 404
