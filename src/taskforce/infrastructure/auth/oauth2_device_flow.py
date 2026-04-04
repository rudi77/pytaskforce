"""OAuth2 Device Authorization Grant (RFC 8628).

Implements the device flow for headless/agent environments where no
browser redirect is possible.  The user receives a verification URL
and code via a channel-agnostic callback (Telegram, Teams, CLI, etc.)
and authenticates on their own device.

Supports Google, Microsoft, and GitHub out of the box.  Custom providers
can be configured via *metadata* with ``device_auth_url`` and ``token_url``.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

import aiohttp
import structlog

from taskforce.core.domain.auth import (
    AuthFlowType,
    AuthStatus,
    TokenData,
    UserInteractionCallback,
)
from taskforce.core.utils.time import utc_now

logger = structlog.get_logger(__name__)

# ------------------------------------------------------------------
# Pre-configured provider endpoints
# ------------------------------------------------------------------
_PROVIDER_ENDPOINTS: dict[str, dict[str, str]] = {
    "google": {
        "device_auth_url": "https://oauth2.googleapis.com/device/code",
        "token_url": "https://oauth2.googleapis.com/token",
    },
    "microsoft": {
        "device_auth_url": ("https://login.microsoftonline.com/common/oauth2/v2.0/devicecode"),
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
    },
    "github": {
        "device_auth_url": "https://github.com/login/device/code",
        "token_url": "https://github.com/login/oauth/access_token",
    },
}

_DEFAULT_TIMEOUT_SECONDS = 600  # 10 minutes
_DEFAULT_POLL_INTERVAL = 5  # seconds


class OAuth2DeviceFlow:
    """OAuth2 Device Authorization Grant implementation.

    Implements :class:`~taskforce.core.interfaces.auth.AuthFlowProtocol`.
    """

    @property
    def flow_type(self) -> str:
        """Return the flow type identifier."""
        return AuthFlowType.OAUTH2_DEVICE.value

    async def execute(
        self,
        *,
        provider: str,
        client_id: str,
        client_secret: str,
        scopes: list[str],
        user_interaction: UserInteractionCallback,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute the device authorization flow.

        Args:
            provider: Provider identifier (e.g. 'google').
            client_id: OAuth2 client ID.
            client_secret: OAuth2 client secret.
            scopes: Scopes to request.
            user_interaction: Callback to send messages to the user.
            metadata: Optional overrides for endpoint URLs.

        Returns:
            Token data dictionary on success.

        Raises:
            RuntimeError: If the flow times out or is denied.
        """
        endpoints = self._resolve_endpoints(provider, metadata)
        device_resp = await self._request_device_code(
            endpoints["device_auth_url"], client_id, scopes, provider
        )
        await self._notify_user(device_resp, user_interaction)
        token_data = await self._poll_for_token(
            endpoints["token_url"],
            client_id,
            client_secret,
            device_resp,
            provider,
        )
        return token_data

    # ------------------------------------------------------------------
    # Step 1: Request device code
    # ------------------------------------------------------------------

    async def _request_device_code(
        self,
        device_auth_url: str,
        client_id: str,
        scopes: list[str],
        provider: str,
    ) -> dict[str, Any]:
        """POST to the device authorization endpoint."""
        payload: dict[str, str] = {"client_id": client_id}
        if scopes:
            payload["scope"] = " ".join(scopes)

        headers: dict[str, str] = {}
        if provider == "github":
            headers["Accept"] = "application/json"

        async with aiohttp.ClientSession() as session:
            async with session.post(device_auth_url, data=payload, headers=headers) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)

        logger.info("auth.device_code_received", provider=provider)
        return data

    # ------------------------------------------------------------------
    # Step 2: Notify user
    # ------------------------------------------------------------------

    async def _notify_user(
        self,
        device_resp: dict[str, Any],
        user_interaction: UserInteractionCallback,
    ) -> None:
        """Send the verification URL and code to the user."""
        verification_uri = device_resp.get(
            "verification_uri_complete",
            device_resp.get("verification_uri", device_resp.get("verification_url", "")),
        )
        user_code = device_resp.get("user_code", "")

        message = (
            f"Please authenticate by visiting:\n"
            f"{verification_uri}\n\n"
            f"Enter code: **{user_code}**"
        )
        await user_interaction(message)

    # ------------------------------------------------------------------
    # Step 3: Poll for token
    # ------------------------------------------------------------------

    async def _poll_for_token(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        device_resp: dict[str, Any],
        provider: str,
    ) -> dict[str, Any]:
        """Poll the token endpoint until the user completes auth."""
        device_code = device_resp["device_code"]
        interval = device_resp.get("interval", _DEFAULT_POLL_INTERVAL)
        expires_in = device_resp.get("expires_in", _DEFAULT_TIMEOUT_SECONDS)
        deadline = utc_now() + timedelta(seconds=expires_in)

        grant_type = "urn:ietf:params:oauth:grant-type:device_code"
        if provider == "github":
            grant_type = "urn:ietf:params:oauth:grant-type:device_code"

        while utc_now() < deadline:
            await asyncio.sleep(interval)
            result = await self._token_request(
                token_url, client_id, client_secret, device_code, grant_type, provider
            )
            if result is not None:
                return result
            # If we get here, the user hasn't completed auth yet — keep polling.

        raise RuntimeError(f"Device authorization timed out after {expires_in}s for {provider}")

    async def _token_request(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        device_code: str,
        grant_type: str,
        provider: str,
    ) -> dict[str, Any] | None:
        """Single token endpoint poll request.

        Returns token data dict on success, None if still pending.
        Raises on denial or other errors.
        """
        payload = {
            "client_id": client_id,
            "device_code": device_code,
            "grant_type": grant_type,
        }
        if client_secret:
            payload["client_secret"] = client_secret

        headers: dict[str, str] = {}
        if provider == "github":
            headers["Accept"] = "application/json"

        async with aiohttp.ClientSession() as session:
            async with session.post(token_url, data=payload, headers=headers) as resp:
                data = await resp.json(content_type=None)

        error = data.get("error")
        if error == "authorization_pending":
            return None
        if error == "slow_down":
            logger.debug("auth.device_flow_slow_down", provider=provider)
            return None
        if error:
            raise RuntimeError(f"Device flow error for {provider}: {error}")

        return self._parse_token_response(data, provider)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_token_response(self, data: dict[str, Any], provider: str) -> dict[str, Any]:
        """Parse a successful token response into a TokenData dict."""
        expires_in = data.get("expires_in")
        expires_at = None
        if expires_in:
            expires_at = utc_now() + timedelta(seconds=int(expires_in))

        token = TokenData(
            provider=_to_provider_type(provider),
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            scopes=_parse_scopes(data.get("scope", "")),
            expires_at=expires_at,
            status=AuthStatus.ACTIVE,
        )
        logger.info("auth.device_flow_success", provider=provider)
        return token.to_dict()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_endpoints(self, provider: str, metadata: dict[str, Any] | None) -> dict[str, str]:
        """Resolve device auth and token endpoint URLs."""
        if metadata and "device_auth_url" in metadata and "token_url" in metadata:
            return {
                "device_auth_url": metadata["device_auth_url"],
                "token_url": metadata["token_url"],
            }
        endpoints = _PROVIDER_ENDPOINTS.get(provider)
        if not endpoints:
            raise ValueError(
                f"No device flow endpoints configured for provider '{provider}'. "
                f"Pass device_auth_url and token_url in metadata."
            )
        return dict(endpoints)


def _to_provider_type(provider: str) -> Any:
    """Convert a string provider name to AuthProviderType."""
    from taskforce.core.domain.auth import AuthProviderType

    try:
        return AuthProviderType(provider)
    except ValueError:
        return AuthProviderType.CUSTOM


def _parse_scopes(scope_string: str) -> list[str]:
    """Parse a space-separated scope string into a list."""
    if not scope_string:
        return []
    return scope_string.split()
