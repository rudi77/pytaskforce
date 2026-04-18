"""Lazy import helpers for the optional ``acp-sdk`` dependency.

Using these helpers lets the rest of the codebase reference ACP types at
module import time without forcing ``acp-sdk`` to be installed. A readable
error surfaces only when the runtime is actually started.
"""

from __future__ import annotations

from typing import Any


class AcpSdkNotInstalledError(ImportError):
    """Raised when code requiring ``acp-sdk`` runs without it installed."""

    def __init__(self, feature: str = "ACP support") -> None:
        super().__init__(
            f"{feature} requires the 'acp-sdk' package. " f"Install it with: uv sync --extra acp"
        )


def load_server() -> Any:
    try:
        from acp_sdk.server import Server  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - exercised via error path
        raise AcpSdkNotInstalledError("ACP server") from exc
    return Server


def load_client() -> Any:
    try:
        from acp_sdk.client import Client  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise AcpSdkNotInstalledError("ACP client") from exc
    return Client


def load_models() -> Any:
    try:
        from acp_sdk import models  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise AcpSdkNotInstalledError("ACP models") from exc
    return models
