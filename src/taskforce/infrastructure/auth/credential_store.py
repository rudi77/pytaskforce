"""Simple encrypted credential store for username/password pairs.

Wraps the :class:`EncryptedTokenStore` to store and retrieve
:class:`~taskforce.core.domain.auth.CredentialData` objects for
services that do not support OAuth2.
"""

from __future__ import annotations

from typing import Any

import structlog

from taskforce.core.domain.auth import CredentialData, UserInteractionCallback
from taskforce.infrastructure.auth.encrypted_token_store import EncryptedTokenStore

logger = structlog.get_logger(__name__)

_CRED_PREFIX = "cred_"


class CredentialStore:
    """Encrypted credential storage backed by :class:`EncryptedTokenStore`.

    Args:
        token_store: The encrypted token store instance to delegate to.
    """

    def __init__(self, token_store: EncryptedTokenStore) -> None:
        self._store = token_store

    async def save_credential(self, credential: CredentialData) -> None:
        """Encrypt and persist a credential.

        Args:
            credential: The credential to store.
        """
        key = f"{_CRED_PREFIX}{credential.provider}"
        await self._store.save_token(key, credential.to_dict())
        logger.info("auth.credential_saved", provider=credential.provider)

    async def load_credential(self, provider: str) -> CredentialData | None:
        """Load a stored credential for a provider.

        Args:
            provider: Service identifier.

        Returns:
            The credential data, or None if not found.
        """
        key = f"{_CRED_PREFIX}{provider}"
        data = await self._store.load_token(key)
        if data is None:
            return None
        return CredentialData.from_dict(data)

    async def delete_credential(self, provider: str) -> None:
        """Delete a stored credential.

        Args:
            provider: Service identifier.
        """
        key = f"{_CRED_PREFIX}{provider}"
        await self._store.delete_token(key)

    async def list_providers(self) -> list[str]:
        """List all providers with stored credentials."""
        all_providers = await self._store.list_providers()
        return [p.removeprefix(_CRED_PREFIX) for p in all_providers if p.startswith(_CRED_PREFIX)]


class CredentialFlow:
    """Auth flow that asks the user for username/password via callback.

    Implements :class:`~taskforce.core.interfaces.auth.AuthFlowProtocol`
    for credential-based authentication.
    """

    def __init__(self, credential_store: CredentialStore) -> None:
        self._store = credential_store

    @property
    def flow_type(self) -> str:
        """Return the flow type identifier."""
        return "credential"

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
        """Ask the user for credentials and store them.

        Args:
            provider: Service identifier.
            client_id: Unused for credential flow.
            client_secret: Unused for credential flow.
            scopes: Unused for credential flow.
            user_interaction: Callback to prompt the user.
            metadata: Optional metadata to store with the credential.

        Returns:
            Dictionary with credential data.
        """
        username = await user_interaction(f"Please enter your username/email for {provider}:")
        if not username:
            raise RuntimeError(f"No username provided for {provider}")

        password = await user_interaction(f"Please enter your password for {provider}:")
        if not password:
            raise RuntimeError(f"No password provided for {provider}")

        credential = CredentialData(
            provider=provider,
            username=username,
            password=password,
            metadata=metadata or {},
        )
        await self._store.save_credential(credential)

        return credential.to_dict()
