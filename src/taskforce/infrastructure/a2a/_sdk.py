"""Lazy import helpers for the optional ``a2a-sdk`` dependency.

Mirrors ``infrastructure/acp/_sdk.py`` — the rest of the codebase can
reference A2A types at module import time without forcing ``a2a-sdk`` to
be installed. A readable error surfaces only when the runtime is
actually used.
"""

from __future__ import annotations

from typing import Any


class A2aSdkNotInstalledError(ImportError):
    """Raised when code requiring ``a2a-sdk`` runs without it installed."""

    def __init__(self, feature: str = "A2A support") -> None:
        super().__init__(
            f"{feature} requires the 'a2a-sdk' package. " f"Install it with: uv sync --extra a2a"
        )


def load_client_factory() -> Any:
    try:
        from a2a.client import create_client  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - exercised via error path
        raise A2aSdkNotInstalledError("A2A client") from exc
    return create_client


def load_client_config() -> Any:
    try:
        from a2a.client import ClientConfig  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise A2aSdkNotInstalledError("A2A client") from exc
    return ClientConfig


def load_card_resolver() -> Any:
    try:
        from a2a.client import A2ACardResolver  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise A2aSdkNotInstalledError("A2A card resolver") from exc
    return A2ACardResolver


def load_types() -> Any:
    try:
        from a2a import types  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise A2aSdkNotInstalledError("A2A types") from exc
    return types


def load_server_request_handlers() -> Any:
    try:
        from a2a.server import request_handlers  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise A2aSdkNotInstalledError("A2A server") from exc
    return request_handlers


def load_server_routes() -> Any:
    try:
        from a2a.server import routes  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise A2aSdkNotInstalledError("A2A server routes") from exc
    return routes


def load_server_agent_execution() -> Any:
    try:
        from a2a.server import agent_execution  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise A2aSdkNotInstalledError("A2A server agent execution") from exc
    return agent_execution


def load_httpx() -> Any:
    try:
        import httpx  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise A2aSdkNotInstalledError("A2A HTTP client") from exc
    return httpx
