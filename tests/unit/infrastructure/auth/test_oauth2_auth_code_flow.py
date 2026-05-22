"""Tests for the OAuth2 Authorization Code flow — PKCE coverage (#283)."""

from __future__ import annotations

import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest

from taskforce.infrastructure.auth import oauth2_auth_code_flow as mod
from taskforce.infrastructure.auth.oauth2_auth_code_flow import (
    OAuth2AuthCodeFlow,
    _generate_pkce_pair,
)


def test_pkce_challenge_is_s256_of_verifier() -> None:
    """The challenge must be the unpadded base64url SHA-256 of the verifier."""
    verifier, challenge = _generate_pkce_pair()
    # RFC 7636: verifier is 43-128 chars from the unreserved set.
    assert 43 <= len(verifier) <= 128
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .decode("ascii")
        .rstrip("=")
    )
    assert challenge == expected
    assert "=" not in challenge  # base64url challenge is unpadded


def test_pkce_pairs_are_unique() -> None:
    """Each flow gets a fresh verifier — no reuse across runs."""
    assert _generate_pkce_pair()[0] != _generate_pkce_pair()[0]


def test_auth_url_carries_pkce_challenge() -> None:
    """_build_auth_url must include code_challenge + S256 method (#283)."""
    flow = OAuth2AuthCodeFlow()
    url = flow._build_auth_url(
        "https://provider.example/auth",
        client_id="cid",
        redirect_uri="http://127.0.0.1:5000/callback",
        scopes=["email"],
        state="state-123",
        provider="google",
        code_challenge="CHALLENGE_VALUE",
    )
    params = parse_qs(urlparse(url).query)
    assert params["code_challenge"] == ["CHALLENGE_VALUE"]
    assert params["code_challenge_method"] == ["S256"]


async def test_exchange_code_sends_verifier(monkeypatch: pytest.MonkeyPatch) -> None:
    """The token exchange must POST the code_verifier — the PKCE proof (#283)."""
    captured: dict = {}

    class _FakeResponse:
        async def __aenter__(self) -> _FakeResponse:
            return self

        async def __aexit__(self, *exc: object) -> bool:
            return False

        def raise_for_status(self) -> None:
            pass

        async def json(self, content_type: object = None) -> dict:
            return {"access_token": "tok", "expires_in": 3600}

    class _FakeSession:
        async def __aenter__(self) -> _FakeSession:
            return self

        async def __aexit__(self, *exc: object) -> bool:
            return False

        def post(self, url: str, data: dict | None = None, headers: dict | None = None):
            captured["data"] = data
            return _FakeResponse()

    monkeypatch.setattr(mod.aiohttp, "ClientSession", _FakeSession)

    flow = OAuth2AuthCodeFlow()
    await flow._exchange_code(
        "https://provider.example/token",
        client_id="cid",
        client_secret="secret",
        code="authcode",
        redirect_uri="http://127.0.0.1:5000/callback",
        provider="google",
        code_verifier="my-code-verifier",
    )

    assert captured["data"]["code_verifier"] == "my-code-verifier"
    assert captured["data"]["grant_type"] == "authorization_code"
