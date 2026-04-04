"""Authentication protocol definitions.

Defines the contracts for token storage, authentication flows,
and the auth manager service. All layer boundaries use these
protocols for dependency inversion.
"""

from __future__ import annotations

from typing import Any, Protocol

from taskforce.core.domain.auth import (
    AuthFlowResult,
    TokenData,
    UserInteractionCallback,
)


class TokenStoreProtocol(Protocol):
    """Protocol for encrypted token/credential persistence.

    Implementations must provide async methods for saving, loading,
    and managing authentication tokens. Token data is stored encrypted
    at rest.

    Error Handling:
        - save_token: Raises on write failure.
        - load_token: Returns None if provider not found.
        - delete_token: Should not raise if provider doesn't exist.
        - list_providers: Returns empty list on error.
    """

    async def save_token(self, provider: str, token_data: dict[str, Any]) -> None:
        """Save token data for a provider.

        Args:
            provider: Provider identifier (e.g. 'google').
            token_data: Serialized token dictionary to encrypt and store.
        """
        ...

    async def load_token(self, provider: str) -> dict[str, Any] | None:
        """Load token data for a provider.

        Args:
            provider: Provider identifier.

        Returns:
            Decrypted token dictionary, or None if not found.
        """
        ...

    async def delete_token(self, provider: str) -> None:
        """Delete stored token for a provider.

        Args:
            provider: Provider identifier.
        """
        ...

    async def list_providers(self) -> list[str]:
        """List all providers that have stored tokens.

        Returns:
            List of provider identifiers.
        """
        ...


class AuthFlowProtocol(Protocol):
    """Protocol for an authentication flow implementation.

    Each flow type (device, auth code, credential) implements this
    protocol. The flow uses a ``UserInteractionCallback`` to communicate
    with the user in a channel-agnostic way.
    """

    @property
    def flow_type(self) -> str:
        """Return the flow type identifier (e.g. 'oauth2_device')."""
        ...

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
        """Execute the authentication flow.

        Args:
            provider: Provider identifier.
            client_id: OAuth2 client ID.
            client_secret: OAuth2 client secret.
            scopes: OAuth2 scopes to request.
            user_interaction: Callback for sending messages to and
                receiving responses from the user.
            metadata: Additional flow-specific parameters.

        Returns:
            Dictionary with token data on success.

        Raises:
            AuthFlowError: If the flow fails.
        """
        ...


class AuthManagerProtocol(Protocol):
    """Protocol for the application-level auth orchestration service.

    The auth manager coordinates token lifecycle: checking for existing
    tokens, refreshing expired ones, and initiating new auth flows
    when needed.
    """

    async def authenticate(
        self,
        provider: str,
        scopes: list[str] | None = None,
        flow_type: str | None = None,
    ) -> AuthFlowResult:
        """Authenticate with a provider.

        Checks for an existing valid token first. If expired, attempts
        a refresh. If no token exists, initiates the configured auth flow.

        Args:
            provider: Provider identifier (e.g. 'google').
            scopes: OAuth2 scopes to request.
            flow_type: Override the default flow type for this provider.

        Returns:
            Result of the authentication attempt.
        """
        ...

    async def get_token(self, provider: str) -> TokenData | None:
        """Get a valid token for a provider.

        Transparently refreshes expired tokens when a refresh token
        is available. This is the primary API for other tools.

        Args:
            provider: Provider identifier.

        Returns:
            Valid token data, or None if no token exists.
        """
        ...

    async def refresh_token(self, provider: str) -> TokenData | None:
        """Force-refresh a token for a provider.

        Args:
            provider: Provider identifier.

        Returns:
            Refreshed token data, or None on failure.
        """
        ...

    async def revoke(self, provider: str) -> bool:
        """Revoke and delete stored tokens for a provider.

        Args:
            provider: Provider identifier.

        Returns:
            True if successfully revoked, False otherwise.
        """
        ...
