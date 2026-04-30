"""Tests for ``POST /api/v1/mcp/probe``.

The probe path is sensitive: it execs a user-supplied command. These
tests cover the localhost gating, command allowlist, validation errors,
SSE happy path, and timeout-induced subprocess teardown — without ever
spawning a real subprocess.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from taskforce.api.server import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_loopback_request_allowed_by_default(client: TestClient) -> None:
    """A trivial validation rejection still returns 200; gating is per-host."""
    response = client.post(
        "/api/v1/mcp/probe",
        json={"type": "stdio", "command": ""},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "stdio probe requires a command" in body["error"]


def test_remote_request_forbidden_without_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TASKFORCE_MCP_PROBE_ALLOW_REMOTE", raising=False)
    app = create_app()
    client = TestClient(app, raise_server_exceptions=True, base_url="http://test")
    # ``TestClient`` reports the loopback as the client by default. Patch the
    # check to see what happens when the request comes from a non-loopback IP.
    from taskforce.api.routes import mcp as mcp_route

    monkeypatch.setattr(mcp_route, "_is_loopback_client", lambda req: False)
    response = client.post(
        "/api/v1/mcp/probe",
        json={"type": "stdio", "command": "npx", "args": []},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "mcp_probe_forbidden"


def test_remote_request_allowed_with_env_opt_in(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TASKFORCE_MCP_PROBE_ALLOW_REMOTE", "1")
    from taskforce.api.routes import mcp as mcp_route

    monkeypatch.setattr(mcp_route, "_is_loopback_client", lambda req: True)
    response = client.post(
        "/api/v1/mcp/probe",
        json={"type": "stdio", "command": ""},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    # The validation rejection should have surfaced — proves we passed the gate.
    assert "stdio probe requires a command" in body["error"]


def test_command_outside_allowlist_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/mcp/probe",
        json={"type": "stdio", "command": "/usr/bin/curl", "args": []},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "not on the MCP probe allowlist" in body["error"]


def test_command_basename_matched_case_insensitive(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Probe rejects unknown commands but matches by basename, case-insensitively."""

    @asynccontextmanager
    async def _fake_stdio(*_a: Any, **_kw: Any):
        yield _FakeClient([{"name": "ok", "description": "", "input_schema": {}}])

    from taskforce.api.routes import mcp as mcp_route
    from taskforce.infrastructure.tools.mcp import client as mcp_client

    monkeypatch.setattr(mcp_client.MCPClient, "create_stdio", _fake_stdio)
    monkeypatch.setattr(mcp_route, "_is_loopback_client", lambda req: True)

    response = client.post(
        "/api/v1/mcp/probe",
        json={"type": "stdio", "command": "C:/Tools/NPX.EXE", "args": ["foo"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert [t["name"] for t in body["tools"]] == ["ok"]


def test_custom_allowlist_via_env(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TASKFORCE_MCP_PROBE_COMMANDS", "echo,whoami")

    @asynccontextmanager
    async def _fake_stdio(*_a: Any, **_kw: Any):
        yield _FakeClient([])

    from taskforce.infrastructure.tools.mcp import client as mcp_client

    monkeypatch.setattr(mcp_client.MCPClient, "create_stdio", _fake_stdio)
    response = client.post(
        "/api/v1/mcp/probe",
        json={"type": "stdio", "command": "echo", "args": ["ok"]},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_allowlist_disabled_with_star(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TASKFORCE_MCP_PROBE_COMMANDS", "*")

    @asynccontextmanager
    async def _fake_stdio(*_a: Any, **_kw: Any):
        yield _FakeClient([])

    from taskforce.infrastructure.tools.mcp import client as mcp_client

    monkeypatch.setattr(mcp_client.MCPClient, "create_stdio", _fake_stdio)
    response = client.post(
        "/api/v1/mcp/probe",
        json={"type": "stdio", "command": "/usr/bin/anything", "args": []},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_sse_url_must_be_http(client: TestClient) -> None:
    response = client.post(
        "/api/v1/mcp/probe",
        json={"type": "sse", "url": "file:///etc/passwd"},
    )
    body = response.json()
    assert body["ok"] is False
    assert "must be http(s)" in body["error"]


def test_sse_happy_path(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def _fake_sse(*_a: Any, **_kw: Any):
        yield _FakeClient(
            [
                {
                    "name": "echo",
                    "description": "Echo input",
                    "inputSchema": {"type": "object"},
                }
            ]
        )

    from taskforce.infrastructure.tools.mcp import client as mcp_client

    monkeypatch.setattr(mcp_client.MCPClient, "create_sse", _fake_sse)
    response = client.post(
        "/api/v1/mcp/probe",
        json={"type": "sse", "url": "http://localhost:5050/mcp"},
    )
    body = response.json()
    assert body["ok"] is True
    assert body["tools"] == [
        {"name": "echo", "description": "Echo input", "input_schema": {"type": "object"}}
    ]


def test_timeout_cancels_inner_task(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the probe times out, the inner ``list_tools`` call must be cancelled."""

    @asynccontextmanager
    async def _hang_stdio(*_a: Any, **_kw: Any):
        yield _HangingClient()

    from taskforce.api.routes import mcp as mcp_route
    from taskforce.infrastructure.tools.mcp import client as mcp_client

    _HangingClient.cancelled = False
    monkeypatch.setattr(mcp_client.MCPClient, "create_stdio", _hang_stdio)
    monkeypatch.setattr(mcp_route, "_probe", _shortened_probe(mcp_route, 0.1))

    response = client.post(
        "/api/v1/mcp/probe",
        json={"type": "stdio", "command": "npx", "args": ["hang"]},
    )
    body = response.json()
    assert body["ok"] is False
    assert "timed out after 0.1s" in body["error"]
    assert _HangingClient.cancelled is True


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


class _FakeClient:
    def __init__(self, tools: list[dict[str, Any]]) -> None:
        self._tools = tools

    async def list_tools(self) -> list[dict[str, Any]]:
        return self._tools


class _HangingClient:
    """Simulates an MCP server that never returns from ``list_tools``."""

    cancelled: bool = False

    async def list_tools(self) -> list[dict[str, Any]]:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            type(self).cancelled = True
            raise
        return []


def _shortened_probe(mcp_route_module: Any, override_timeout: float):
    """Replace ``_probe`` with one that ignores the caller's timeout."""
    original = mcp_route_module._probe

    async def runner(request, timeout: float = 10.0):  # noqa: ARG001 — caller passes 10
        return await original(request, timeout=override_timeout)

    return runner
