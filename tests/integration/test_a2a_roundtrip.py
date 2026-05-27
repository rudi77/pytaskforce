"""End-to-end roundtrip test for the A2A server + client.

Spawns a real A2A server on a random localhost port, calls it via
the client (both sync and stream paths), and asserts the response
shape. Requires ``a2a-sdk`` installed (``uv sync --extra a2a``);
skipped otherwise.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

a2a_sdk = pytest.importorskip("a2a")

from taskforce.application.a2a_service import build_a2a_service  # noqa: E402


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.asyncio
async def test_a2a_server_client_roundtrip(tmp_path: Path) -> None:
    port = _free_port()
    server_svc = build_a2a_service(
        {
            "server": {"enabled": True, "host": "127.0.0.1", "port": port},
            "peers": [],
        },
        work_dir=str(tmp_path / "server"),
    )
    assert server_svc is not None

    async def echo_handler(mission: str, session_id: str | None) -> str:
        return f"echo: {mission}"

    server_svc.register_profile_agent(echo_handler, profile_name="dev", tools=["python"])
    await server_svc.start()
    await server_svc.runtime.server.wait_started(timeout=10.0)
    try:
        client_svc = build_a2a_service(
            {
                "server": {"enabled": False},
                "peers": [
                    {
                        "name": "echo",
                        "base_url": f"http://127.0.0.1:{port}",
                    }
                ],
            },
            work_dir=str(tmp_path / "client"),
        )
        assert client_svc is not None

        peer = client_svc.list_peers()[0]
        card = await client_svc.runtime.client.fetch_agent_card(peer)
        assert card.name == "dev"
        assert "python" in {s.id for s in card.skills}

        handle = await client_svc.call_peer("echo", "hello world")
        assert handle.state.value == "completed"
        assert handle.output_text == "echo: hello world"
        assert handle.task_id

        events = []
        async for event in client_svc.runtime.client.run_stream(peer, "hi stream"):
            events.append(event)
        assert events
        assert any(e["type"] == "status_update" for e in events)
    finally:
        await server_svc.stop()
