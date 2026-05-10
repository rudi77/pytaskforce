"""OAuth connections API — list + disconnect.

Phase B4 ships a *minimal* OAuth surface so the UI can show which
external accounts (Google, GitHub, …) are connected and let the
operator disconnect them. Initiating a fresh OAuth flow from the UI
is intentionally deferred — the existing ``authenticate`` tool runs
the device flow interactively from chat, which is friendlier than
reproducing the multi-step polling in the SPA.

The framework's existing :class:`AuthManager` already encapsulates
revocation, refresh, and token persistence; this route is a thin
wrapper around it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from taskforce.api.dependencies import get_auth_manager, require_permission
from taskforce.api.errors import http_exception as _http_exception
from taskforce.core.domain.auth import TokenData

router = APIRouter()


class OAuthConnection(BaseModel):
    """Summary of a single stored OAuth connection."""

    provider: str
    status: str = Field(description="Auth status (active, expired, failed, …).")
    scopes: list[str] = Field(default_factory=list)
    has_refresh_token: bool = Field(
        description="True when the stored token can be refreshed without user interaction."
    )
    expires_at: datetime | None = Field(
        default=None,
        description="When the current access token expires. Null for non-expiring tokens.",
    )
    is_expired: bool = Field(default=False)


class OAuthConnectionsResponse(BaseModel):
    connections: list[OAuthConnection]
    auth_manager_available: bool = Field(
        description=(
            "False when the framework couldn't initialise an AuthManager "
            "(e.g. missing optional ``cryptography`` extra) — UI should hide "
            "OAuth controls and show an install hint."
        )
    )


def _summarise(provider: str, raw: dict[str, Any]) -> OAuthConnection:
    token = TokenData.from_dict(raw)
    expires_at = token.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return OAuthConnection(
        provider=provider,
        status=token.status.value if hasattr(token.status, "value") else str(token.status),
        scopes=list(token.scopes or []),
        has_refresh_token=bool(token.refresh_token),
        expires_at=expires_at,
        is_expired=token.is_expired,
    )


@router.get(
    "/oauth/connections",
    response_model=OAuthConnectionsResponse,
    summary="List stored OAuth connections",
)
async def list_oauth_connections(
    _permission: None = Depends(require_permission("tenant:manage")),
    auth_manager=Depends(get_auth_manager),
) -> OAuthConnectionsResponse:
    if auth_manager is None:
        return OAuthConnectionsResponse(connections=[], auth_manager_available=False)

    store = getattr(auth_manager, "_token_store", None)
    if store is None:
        return OAuthConnectionsResponse(connections=[], auth_manager_available=False)

    providers = await store.list_providers()
    connections: list[OAuthConnection] = []
    for provider in providers:
        raw = await store.load_token(provider)
        if raw is None:
            continue
        try:
            connections.append(_summarise(provider, raw))
        except Exception:  # noqa: BLE001 — corrupt token rows must not break listing
            connections.append(
                OAuthConnection(
                    provider=provider,
                    status="unreadable",
                    has_refresh_token=False,
                )
            )
    return OAuthConnectionsResponse(connections=connections, auth_manager_available=True)


@router.delete(
    "/oauth/connections/{provider}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke and remove an OAuth connection",
)
async def revoke_oauth_connection(
    provider: str,
    _permission: None = Depends(require_permission("tenant:manage")),
    auth_manager=Depends(get_auth_manager),
) -> None:
    if auth_manager is None:
        raise _http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="auth_manager_unavailable",
            message="AuthManager is not configured on this instance.",
        )
    await auth_manager.revoke(provider)
