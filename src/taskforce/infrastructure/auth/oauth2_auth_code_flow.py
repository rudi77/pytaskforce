"""OAuth2 Authorization Code Flow.

Implements the standard OAuth2 auth code flow for environments where
a browser redirect is possible (CLI mode, local development).  The
user receives a URL via the ``UserInteractionCallback``, authenticates
in their browser, and a temporary local HTTP server captures the
redirect with the authorization code.

For headless / remote agent scenarios prefer the Device Flow instead.
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

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
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
    },
    "microsoft": {
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
    },
    "github": {
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
    },
}

_DEFAULT_REDIRECT_HOST = "127.0.0.1"
_CALLBACK_TIMEOUT = 300  # 5 minutes


class OAuth2AuthCodeFlow:
    """OAuth2 Authorization Code Flow implementation.

    Implements :class:`~taskforce.core.interfaces.auth.AuthFlowProtocol`.
    """

    @property
    def flow_type(self) -> str:
        """Return the flow type identifier."""
        return AuthFlowType.OAUTH2_AUTH_CODE.value

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
        """Execute the authorization code flow.

        Args:
            provider: Provider identifier (e.g. 'google').
            client_id: OAuth2 client ID.
            client_secret: OAuth2 client secret.
            scopes: Scopes to request.
            user_interaction: Callback to send the auth URL to the user.
            metadata: Optional overrides for endpoint URLs.

        Returns:
            Token data dictionary on success.

        Raises:
            RuntimeError: If the flow fails or times out.
        """
        endpoints = self._resolve_endpoints(provider, metadata)
        state = secrets.token_urlsafe(32)

        code_future: asyncio.Future[str] = asyncio.get_event_loop().create_future()
        server, port = await self._start_callback_server(state, code_future)

        try:
            redirect_uri = f"http://{_DEFAULT_REDIRECT_HOST}:{port}/callback"
            auth_url = self._build_auth_url(
                endpoints["auth_url"], client_id, redirect_uri, scopes, state, provider
            )
            await user_interaction(f"Please open this URL to authenticate:\n{auth_url}")
            code = await asyncio.wait_for(code_future, timeout=_CALLBACK_TIMEOUT)
        finally:
            server.close()
            await server.wait_closed()

        token_data = await self._exchange_code(
            endpoints["token_url"],
            client_id,
            client_secret,
            code,
            redirect_uri,
            provider,
        )
        return token_data

    # ------------------------------------------------------------------
    # Auth URL construction
    # ------------------------------------------------------------------

    def _build_auth_url(
        self,
        auth_url: str,
        client_id: str,
        redirect_uri: str,
        scopes: list[str],
        state: str,
        provider: str,
    ) -> str:
        """Build the authorization URL with query parameters."""
        params: dict[str, str] = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "response_type": "code",
        }
        if scopes:
            params["scope"] = " ".join(scopes)
        if provider == "google":
            params["access_type"] = "offline"
            params["prompt"] = "consent"

        return f"{auth_url}?{urlencode(params)}"

    # ------------------------------------------------------------------
    # Local callback server
    # ------------------------------------------------------------------

    async def _start_callback_server(
        self,
        expected_state: str,
        code_future: asyncio.Future[str],
    ) -> tuple[asyncio.AbstractServer, int]:
        """Start a temporary HTTP server to receive the OAuth callback."""

        async def handle_callback(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            data = await reader.read(4096)
            request_line = data.decode().split("\r\n")[0]
            # Parse GET /callback?code=xxx&state=yyy HTTP/1.1
            params = self._parse_callback_params(request_line)

            response_body: str
            if params.get("state") != expected_state:
                response_body = "Error: Invalid state parameter."
            elif "code" not in params:
                response_body = f"Error: {params.get('error', 'No code received')}."
            else:
                response_body = "Authentication successful! You can close this tab."
                if not code_future.done():
                    code_future.set_result(params["code"])

            response = (
                f"HTTP/1.1 200 OK\r\n"
                f"Content-Type: text/html\r\n"
                f"Content-Length: {len(response_body)}\r\n"
                f"\r\n{response_body}"
            )
            writer.write(response.encode())
            await writer.drain()
            writer.close()

        server = await asyncio.start_server(handle_callback, _DEFAULT_REDIRECT_HOST, 0)
        port = server.sockets[0].getsockname()[1]
        logger.info("auth.callback_server_started", port=port)
        return server, port

    def _parse_callback_params(self, request_line: str) -> dict[str, str]:
        """Extract query parameters from an HTTP request line."""
        parts = request_line.split(" ")
        if len(parts) < 2:
            return {}
        parsed = urlparse(parts[1])
        return {k: v[0] for k, v in parse_qs(parsed.query).items()}

    # ------------------------------------------------------------------
    # Token exchange
    # ------------------------------------------------------------------

    async def _exchange_code(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str,
        provider: str,
    ) -> dict[str, Any]:
        """Exchange the authorization code for tokens."""
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        headers: dict[str, str] = {}
        if provider == "github":
            headers["Accept"] = "application/json"

        async with aiohttp.ClientSession() as session:
            async with session.post(token_url, data=payload, headers=headers) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)

        if "error" in data:
            raise RuntimeError(f"Token exchange failed for {provider}: {data['error']}")

        return self._parse_token_response(data, provider)

    def _parse_token_response(self, data: dict[str, Any], provider: str) -> dict[str, Any]:
        """Parse a successful token response into a TokenData dict."""
        from taskforce.core.domain.auth import AuthProviderType

        expires_in = data.get("expires_in")
        expires_at = None
        if expires_in:
            expires_at = utc_now() + timedelta(seconds=int(expires_in))

        try:
            provider_type = AuthProviderType(provider)
        except ValueError:
            provider_type = AuthProviderType.CUSTOM

        token = TokenData(
            provider=provider_type,
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            token_uri=data.get("token_uri", ""),
            client_id=data.get("client_id", ""),
            client_secret=data.get("client_secret", ""),
            scopes=data.get("scope", "").split() if data.get("scope") else [],
            expires_at=expires_at,
            status=AuthStatus.ACTIVE,
        )
        logger.info("auth.auth_code_flow_success", provider=provider)
        return token.to_dict()

    # ------------------------------------------------------------------
    # Endpoint resolution
    # ------------------------------------------------------------------

    def _resolve_endpoints(self, provider: str, metadata: dict[str, Any] | None) -> dict[str, str]:
        """Resolve auth and token endpoint URLs."""
        if metadata and "auth_url" in metadata and "token_url" in metadata:
            return {
                "auth_url": metadata["auth_url"],
                "token_url": metadata["token_url"],
            }
        endpoints = _PROVIDER_ENDPOINTS.get(provider)
        if not endpoints:
            raise ValueError(
                f"No auth code flow endpoints for provider '{provider}'. "
                f"Pass auth_url and token_url in metadata."
            )
        return dict(endpoints)
