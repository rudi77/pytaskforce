"""Authentication domain models.

Defines enums, dataclasses, and type aliases for the centralized
authentication and credential management system.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from taskforce.core.utils.time import utc_now


class AuthProviderType(str, Enum):
    """Supported authentication providers."""

    GOOGLE = "google"
    MICROSOFT = "microsoft"
    GITHUB = "github"
    CUSTOM = "custom"


class AuthFlowType(str, Enum):
    """Supported authentication flow types."""

    OAUTH2_DEVICE = "oauth2_device"
    OAUTH2_AUTH_CODE = "oauth2_auth_code"
    CREDENTIAL = "credential"


class AuthStatus(str, Enum):
    """Status of a stored authentication token or credential."""

    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    PENDING = "pending"
    FAILED = "failed"


# Callback type for channel-agnostic user interaction during auth flows.
# Takes a message to display, returns the user's response (or None for
# fire-and-forget messages like status updates).
UserInteractionCallback = Callable[[str], Awaitable[str | None]]


@dataclass
class TokenData:
    """Stored OAuth2 token with metadata.

    Attributes:
        provider: The authentication provider (google, microsoft, etc.).
        access_token: The OAuth2 access token.
        refresh_token: Optional refresh token for token renewal.
        token_uri: Provider's token endpoint URL.
        client_id: OAuth2 client identifier.
        client_secret: OAuth2 client secret.
        scopes: List of granted OAuth2 scopes.
        expires_at: When the access token expires (UTC).
        created_at: When this token was first stored (UTC).
        status: Current token status.
    """

    provider: AuthProviderType
    access_token: str
    refresh_token: str | None = None
    token_uri: str = ""
    client_id: str = ""
    client_secret: str = ""
    scopes: list[str] = field(default_factory=list)
    expires_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)
    status: AuthStatus = AuthStatus.ACTIVE

    @property
    def is_expired(self) -> bool:
        """Check whether the access token has expired."""
        if self.expires_at is None:
            return False
        return utc_now() >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary for storage."""
        return {
            "provider": self.provider.value,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_uri": self.token_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scopes": list(self.scopes),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat(),
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TokenData:
        """Deserialize from a plain dictionary."""
        expires_at = data.get("expires_at")
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)

        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        else:
            created_at = utc_now()

        return cls(
            provider=AuthProviderType(data["provider"]),
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            token_uri=data.get("token_uri", ""),
            client_id=data.get("client_id", ""),
            client_secret=data.get("client_secret", ""),
            scopes=data.get("scopes", []),
            expires_at=expires_at,
            created_at=created_at,
            status=AuthStatus(data.get("status", "active")),
        )


@dataclass
class CredentialData:
    """Stored credential pair (username/password).

    Attributes:
        provider: Identifier for the target service.
        username: The login username or email.
        password: The login password (encrypted at rest by the token store).
        metadata: Optional extra data (e.g. login URL, notes).
        created_at: When this credential was stored (UTC).
    """

    provider: str
    username: str
    password: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary for storage."""
        return {
            "provider": self.provider,
            "username": self.username,
            "password": self.password,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CredentialData:
        """Deserialize from a plain dictionary."""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        else:
            created_at = utc_now()

        return cls(
            provider=data["provider"],
            username=data["username"],
            password=data["password"],
            metadata=data.get("metadata", {}),
            created_at=created_at,
        )


@dataclass
class AuthFlowRequest:
    """Request to initiate an authentication flow.

    Attributes:
        provider: Target provider type.
        flow_type: Which auth flow to use.
        scopes: OAuth2 scopes to request.
        client_id: OAuth2 client identifier.
        client_secret: OAuth2 client secret.
        metadata: Additional flow-specific parameters.
    """

    provider: AuthProviderType
    flow_type: AuthFlowType
    scopes: list[str] = field(default_factory=list)
    client_id: str = ""
    client_secret: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuthFlowResult:
    """Result of an authentication flow attempt.

    Attributes:
        success: Whether the flow completed successfully.
        provider: The provider that was targeted.
        status: Resulting auth status.
        error: Error message if the flow failed.
        token: The resulting token data on success.
    """

    success: bool
    provider: AuthProviderType
    status: AuthStatus
    error: str | None = None
    token: TokenData | None = None
