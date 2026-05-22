"""Spec-coverage tests for OAuth2 + Auth Manager.

Covers the parts of ``docs/spec/auth.md`` that lacked a focused test:
encrypted at-rest round-trip, atomic token writes, the device-flow timeout,
the auth-code flow's CSRF-state rejection and localhost-only callback bind,
and the high-risk approval gate on the ``authenticate`` tool.

Spec: docs/spec/auth.md — tests tagged @pytest.mark.spec("auth.*").
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from taskforce.infrastructure.auth.encrypted_token_store import EncryptedTokenStore
from taskforce.infrastructure.auth.oauth2_auth_code_flow import OAuth2AuthCodeFlow
from taskforce.infrastructure.auth.oauth2_device_flow import OAuth2DeviceFlow


# ---------------------------------------------------------------------------
# Encrypted token store
# ---------------------------------------------------------------------------


@pytest.mark.spec("auth.token_store_round_trips_payload_encrypted")
@pytest.mark.asyncio
async def test_token_store_round_trips_payload_encrypted(tmp_path: Path) -> None:
    """A saved token round-trips, and the on-disk bytes never hold plaintext."""
    store = EncryptedTokenStore(store_dir=str(tmp_path / "auth"))
    token = {
        "provider": "google",
        "access_token": "SECRET-ACCESS-abc123",
        "refresh_token": "SECRET-REFRESH-def456",
    }
    await store.save_token("google", token)

    # Round-trips through decryption.
    assert await store.load_token("google") == token

    # The raw file is ciphertext — the plaintext secret never appears.
    raw = (tmp_path / "auth" / "google.enc").read_bytes()
    assert b"SECRET-ACCESS-abc123" not in raw
    assert b"SECRET-REFRESH-def456" not in raw


@pytest.mark.spec("auth.token_store_write_is_atomic")
@pytest.mark.asyncio
async def test_token_store_write_is_atomic(tmp_path: Path, monkeypatch) -> None:
    """Token writes go through a temp file + atomic rename, leaving no scraps."""
    store = EncryptedTokenStore(store_dir=str(tmp_path / "auth"))

    replace_calls: list[tuple[str, str]] = []
    original_replace = Path.replace

    def spy_replace(self: Path, target):  # type: ignore[no-untyped-def]
        replace_calls.append((str(self), str(target)))
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", spy_replace)

    await store.save_token("google", {"access_token": "v1"})

    # The write landed on the target via a rename from a .tmp sibling …
    assert replace_calls, "save_token must rename a temp file onto the target"
    src, dst = replace_calls[0]
    assert src.endswith(".tmp")
    assert dst.endswith(".enc")
    # … and no half-written temp file lingers afterwards.
    assert list((tmp_path / "auth").glob("*.tmp")) == []
    assert await store.load_token("google") == {"access_token": "v1"}


# ---------------------------------------------------------------------------
# Device flow
# ---------------------------------------------------------------------------


@pytest.mark.spec("auth.device_flow_times_out_after_expires_in")
@pytest.mark.asyncio
async def test_device_flow_times_out_after_expires_in(monkeypatch) -> None:
    """Polling stops with a timeout error once ``expires_in`` elapses."""
    flow = OAuth2DeviceFlow()

    polls = {"count": 0}

    async def never_completes(*_args, **_kwargs):
        polls["count"] += 1
        return None  # authorization_pending → keep polling

    monkeypatch.setattr(flow, "_token_request", never_completes)

    with pytest.raises(RuntimeError, match="timed out"):
        await flow._poll_for_token(
            "https://token.url",
            "client_id",
            "client_secret",
            {"device_code": "dc", "interval": 0.01, "expires_in": 0.05},
            "google",
        )

    assert polls["count"] >= 1, "the flow must poll at least once before timing out"


# ---------------------------------------------------------------------------
# Auth-code flow callback server
# ---------------------------------------------------------------------------


@pytest.mark.spec("auth.auth_code_callback_server_binds_localhost_only")
@pytest.mark.asyncio
async def test_auth_code_callback_server_binds_localhost_only() -> None:
    """The local callback server binds 127.0.0.1 on an ephemeral port."""
    flow = OAuth2AuthCodeFlow()
    code_future: asyncio.Future[str] = asyncio.get_event_loop().create_future()

    server, port = await flow._start_callback_server("state-x", code_future)
    try:
        host = server.sockets[0].getsockname()[0]
        assert host == "127.0.0.1"
        assert port > 0
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.spec("auth.auth_code_flow_rejects_mismatched_state")
@pytest.mark.asyncio
async def test_auth_code_flow_rejects_mismatched_state() -> None:
    """A callback whose CSRF ``state`` does not match is rejected."""
    flow = OAuth2AuthCodeFlow()
    code_future: asyncio.Future[str] = asyncio.get_event_loop().create_future()

    server, port = await flow._start_callback_server("EXPECTED_STATE", code_future)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(
            b"GET /callback?code=abc&state=WRONG_STATE HTTP/1.1\r\n\r\n"
        )
        await writer.drain()
        response = await reader.read(4096)
        writer.close()
        await writer.wait_closed()
    finally:
        server.close()
        await server.wait_closed()

    assert b"Invalid state" in response
    # A mismatched state must NOT hand a code to the waiting flow.
    assert not code_future.done()


# ---------------------------------------------------------------------------
# authenticate tool — high-risk approval gate
# ---------------------------------------------------------------------------


@pytest.mark.spec("auth.authenticate_tool_marked_high_risk_approval")
def test_authenticate_tool_marked_high_risk_approval() -> None:
    """The ``authenticate`` tool is gated as a HIGH-risk approval tool."""
    from taskforce.core.interfaces.tools import ApprovalRiskLevel
    from taskforce.infrastructure.tools.native.auth_tool import AuthTool

    tool = AuthTool()
    assert tool.requires_approval is True
    assert tool.approval_risk_level == ApprovalRiskLevel.HIGH
