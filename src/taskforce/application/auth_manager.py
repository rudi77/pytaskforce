"""Centralized Authentication Manager.

Orchestrates authentication flows, token lifecycle (refresh, revoke),
and encrypted storage.  Uses the Communication Gateway for channel-agnostic
user interaction during auth flows.

This is the single entry point for all authentication needs — both as an
explicit ``authenticate`` tool and as an internal API for other tools
(calendar, gmail, browser, etc.) via ``get_token()``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
import structlog

from taskforce.core.domain.auth import (
    AuthFlowResult,
    AuthFlowType,
    AuthProviderType,
    AuthStatus,
    TokenData,
    UserInteractionCallback,
)
from taskforce.core.interfaces.auth import AuthFlowProtocol, TokenStoreProtocol

logger = structlog.get_logger(__name__)


class AuthManager:
    """Application-layer service for centralized authentication.

    Implements :class:`~taskforce.core.interfaces.auth.AuthManagerProtocol`.

    Args:
        token_store: Encrypted token persistence.
        auth_flows: Map of flow type string → flow implementation.
        gateway: Optional Communication Gateway for user interaction.
        provider_configs: Per-provider settings (client_id, client_secret,
            default_flow, default_scopes, etc.).
    """

    def __init__(
        self,
        *,
        token_store: TokenStoreProtocol,
        auth_flows: dict[str, AuthFlowProtocol],
        gateway: Any | None = None,
        provider_configs: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._token_store = token_store
        self._auth_flows = auth_flows
        self._gateway = gateway
        self._provider_configs = provider_configs or {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def authenticate(
        self,
        provider: str,
        scopes: list[str] | None = None,
        flow_type: str | None = None,
        channel: str | None = None,
        recipient_id: str | None = None,
    ) -> AuthFlowResult:
        """Authenticate with a provider.

        Checks for an existing valid token first.  If expired, attempts
        a refresh.  If no token exists, initiates the configured auth flow.

        Args:
            provider: Provider identifier (e.g. 'google').
            scopes: OAuth2 scopes to request (overrides provider defaults).
            flow_type: Override the default flow type for this provider.
            channel: Communication channel for user interaction.
            recipient_id: Recipient on the channel.

        Returns:
            Result of the authentication attempt.
        """
        config = self._provider_configs.get(provider, {})
        scopes = scopes or config.get("default_scopes", [])
        flow_type = flow_type or config.get("default_flow", AuthFlowType.OAUTH2_DEVICE.value)

        # 1. Check for existing valid token.
        existing = await self.get_token(provider)
        if existing and not existing.is_expired:
            return self._success_result(provider, existing)

        # 2. If expired, try refresh.
        if existing and existing.is_expired and existing.refresh_token:
            refreshed = await self.refresh_token(provider)
            if refreshed:
                return self._success_result(provider, refreshed)

        # 3. Initiate auth flow.
        return await self._run_flow(provider, scopes, flow_type, config, channel, recipient_id)

    async def get_token(self, provider: str) -> TokenData | None:
        """Get a valid token for a provider.

        Transparently refreshes expired tokens when possible.

        Args:
            provider: Provider identifier.

        Returns:
            Valid token data, or None if no token exists.
        """
        data = await self._token_store.load_token(provider)
        if data is None:
            return None

        token = TokenData.from_dict(data)
        if token.is_expired and token.refresh_token:
            refreshed = await self.refresh_token(provider)
            return refreshed
        return token

    async def refresh_token(self, provider: str) -> TokenData | None:
        """Force-refresh a token for a provider.

        Args:
            provider: Provider identifier.

        Returns:
            Refreshed token data, or None on failure.
        """
        data = await self._token_store.load_token(provider)
        if data is None:
            return None

        token = TokenData.from_dict(data)
        if not token.refresh_token or not token.token_uri:
            logger.warning("auth.refresh_no_refresh_token", provider=provider)
            return None

        try:
            new_data = await self._do_refresh(token)
            await self._token_store.save_token(provider, new_data.to_dict())
            logger.info("auth.token_refreshed", provider=provider)
            return new_data
        except Exception as exc:
            logger.warning("auth.refresh_failed", provider=provider, error=str(exc))
            return None

    async def revoke(self, provider: str) -> bool:
        """Revoke and delete stored tokens for a provider.

        Args:
            provider: Provider identifier.

        Returns:
            True if successfully revoked.
        """
        await self._token_store.delete_token(provider)
        logger.info("auth.token_revoked", provider=provider)
        return True

    # ------------------------------------------------------------------
    # Flow execution
    # ------------------------------------------------------------------

    async def _run_flow(
        self,
        provider: str,
        scopes: list[str],
        flow_type: str,
        config: dict[str, Any],
        channel: str | None,
        recipient_id: str | None,
    ) -> AuthFlowResult:
        """Run an authentication flow and store the resulting token."""
        flow = self._auth_flows.get(flow_type)
        if flow is None:
            return self._failure_result(provider, f"Unknown auth flow type: {flow_type}")

        try:
            token_dict = await self._execute_flow(
                flow, provider, config, scopes, channel, recipient_id
            )
            await self._token_store.save_token(provider, token_dict)
            return self._success_result(provider, TokenData.from_dict(token_dict))
        except Exception as exc:
            logger.error("auth.flow_failed", provider=provider, error=str(exc))
            return self._failure_result(provider, str(exc))

    async def _execute_flow(
        self,
        flow: AuthFlowProtocol,
        provider: str,
        config: dict[str, Any],
        scopes: list[str],
        channel: str | None,
        recipient_id: str | None,
    ) -> dict[str, Any]:
        """Execute a single auth flow with the given configuration."""
        return await flow.execute(
            provider=provider,
            client_id=config.get("client_id", ""),
            client_secret=config.get("client_secret", ""),
            scopes=scopes,
            user_interaction=self._make_user_interaction(channel, recipient_id),
            metadata=config.get("metadata"),
        )

    # ------------------------------------------------------------------
    # Token refresh
    # ------------------------------------------------------------------

    async def _do_refresh(self, token: TokenData) -> TokenData:
        """Perform an OAuth2 token refresh request."""
        payload = {
            "client_id": token.client_id,
            "client_secret": token.client_secret,
            "refresh_token": token.refresh_token,
            "grant_type": "refresh_token",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(token.token_uri, data=payload) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)

        return self._build_refreshed_token(token, data)

    def _build_refreshed_token(self, old: TokenData, data: dict[str, Any]) -> TokenData:
        """Build a new TokenData from a refresh response."""
        from datetime import timedelta

        from taskforce.core.utils.time import utc_now

        expires_at = None
        if data.get("expires_in"):
            expires_at = utc_now() + timedelta(seconds=int(data["expires_in"]))

        return TokenData(
            provider=old.provider,
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", old.refresh_token),
            token_uri=old.token_uri,
            client_id=old.client_id,
            client_secret=old.client_secret,
            scopes=old.scopes,
            expires_at=expires_at,
            status=AuthStatus.ACTIVE,
        )

    # ------------------------------------------------------------------
    # User interaction
    # ------------------------------------------------------------------

    def _make_user_interaction(
        self,
        channel: str | None,
        recipient_id: str | None,
    ) -> UserInteractionCallback:
        """Create a channel-agnostic user interaction callback.

        If a gateway + channel + recipient are available, routes messages
        through the Communication Gateway.  Otherwise falls back to
        logging (useful for CLI mode where ask_user handles interaction).
        """

        async def interact(message: str) -> str | None:
            if self._gateway and channel and recipient_id:
                return await self._gateway_interact(channel, recipient_id, message)
            logger.info("auth.user_interaction", message=message)
            return None

        return interact

    async def _gateway_interact(self, channel: str, recipient_id: str, message: str) -> str | None:
        """Send a message via gateway and poll for response."""
        session_id = f"auth_{channel}_{recipient_id}"
        await self._gateway.send_channel_question(
            session_id=session_id,
            channel=channel,
            recipient_id=recipient_id,
            question=message,
        )

        # Poll for up to 10 minutes.
        for _ in range(300):
            await asyncio.sleep(2)
            response = await self._gateway.poll_channel_response(session_id=session_id)
            if response is not None:
                await self._gateway.clear_channel_question(session_id=session_id)
                return response

        logger.warning("auth.gateway_interaction_timeout", channel=channel)
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _success_result(self, provider: str, token: TokenData) -> AuthFlowResult:
        """Build a successful AuthFlowResult."""
        return AuthFlowResult(
            success=True,
            provider=_to_provider_type(provider),
            status=AuthStatus.ACTIVE,
            token=token,
        )

    def _failure_result(self, provider: str, error: str) -> AuthFlowResult:
        """Build a failed AuthFlowResult."""
        return AuthFlowResult(
            success=False,
            provider=_to_provider_type(provider),
            status=AuthStatus.FAILED,
            error=error,
        )


def _to_provider_type(provider: str) -> AuthProviderType:
    """Convert a string provider name to AuthProviderType."""
    try:
        return AuthProviderType(provider)
    except ValueError:
        return AuthProviderType.CUSTOM
