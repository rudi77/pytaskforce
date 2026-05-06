"""Integration-test fixtures (INT-01).

When ``taskforce-enterprise`` is installed alongside the framework, its
auth middleware is wired into every FastAPI app created by
:func:`taskforce.api.server.create_app`. The integration tests in this
directory exercise unauthenticated TestClient requests against agent /
tool / workflow / UI endpoints — they were written against the OSS
build of ``create_app`` and don't supply credentials.

This conftest patches :func:`taskforce.api.server.create_app` so that
when it is called without an explicit ``plugin_config``, a test-mode
config is supplied that disables enterprise auth and policy
enforcement. With ``allow_anonymous`` switched on the middleware lets
unauthenticated requests through with a guest identity, which keeps
the existing integration tests valid while still exercising the rest
of the request pipeline.

Tests that *want* to verify auth behaviour can either:

* call ``create_app(plugin_config={"enterprise": {"auth": {"enabled":
  True}}})`` explicitly, or
* request the :func:`enterprise_auth_token` fixture below to mint a
  short-lived JWT and pass it via the ``Authorization`` header.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

import pytest

_TEST_PLUGIN_CONFIG: dict[str, Any] = {
    "enterprise": {
        "auth": {
            "enabled": False,
            "allow_anonymous": True,
        },
        "policy": {"enabled": False},
        "audit": {"enabled": False},
    }
}

_TEST_JWT_SECRET = "integration-test-secret"


@pytest.fixture(autouse=True)
def _disable_enterprise_auth_in_create_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``create_app()`` use a test plugin config that disables auth.

    Two coordinated effects:

    1. Patch ``server._load_plugin_config`` so an unconfigured
       ``create_app()`` call sees the test config (auth + policy
       disabled, ``allow_anonymous`` true).
    2. Reset the process-global :class:`PluginRegistry` so middleware
       and routers from a previous test (or earlier collection) don't
       linger. Without this the first test wins: once the auth
       middleware is registered with auth-enabled defaults, every
       subsequent test sees it because the registry is a module
       singleton.

    Patching at the loader level (rather than ``create_app`` itself)
    survives ``from taskforce.api.server import create_app`` re-exports
    in test modules — patching ``create_app`` directly wouldn't,
    because the reference has already been bound.
    """
    try:
        from taskforce.api import server
        from taskforce.application import plugin_loader
    except ImportError:  # pragma: no cover — taskforce always installed in tests
        return

    monkeypatch.setattr(server, "_load_plugin_config", lambda: _TEST_PLUGIN_CONFIG)

    # Wipe the global plugin registry + each plugin's "initialized" flag
    # so the next ``load_all_plugins(config)`` re-runs with our config.
    plugin_loader._plugin_registry = None
    for info in plugin_loader.discover_plugins():
        if info.instance is not None:
            # Force re-init on next load — the plugin's _initialized
            # flag is the gate that prevents middleware re-registration.
            try:
                setattr(info.instance, "_initialized", False)
                setattr(info.instance, "_middleware", [])
            except Exception:  # pragma: no cover — defensive
                pass


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


@pytest.fixture
def enterprise_auth_token() -> str:
    """Mint a short-lived JWT using the integration-test secret.

    Tests that opt back into auth (by passing
    ``plugin_config={"enterprise": {"auth": {"enabled": True, "postgres":
    {"jwt_secret": "integration-test-secret"}}}}``) can include this
    token via ``client.headers["Authorization"] = f"Bearer {token}"``
    to authenticate as a synthetic admin user.
    """
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": "test-user-id",
        "tenant_id": "test-tenant",
        "email": "test-admin@example.com",
        "roles": ["admin"],
        "iat": now,
        "exp": now + 3600,
        "iss": "taskforce-enterprise",
    }
    h = _b64u(json.dumps(header, separators=(",", ":")).encode())
    p = _b64u(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(
        _TEST_JWT_SECRET.encode("utf-8"),
        f"{h}.{p}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return f"{h}.{p}.{_b64u(sig)}"
