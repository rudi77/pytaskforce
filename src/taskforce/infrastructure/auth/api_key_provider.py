"""API Key-based identity provider implementation.

This module provides API key validation for service-to-service
and programmatic API access.
"""

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Set
from dataclasses import dataclass, field
import structlog

from taskforce.core.interfaces.identity import (
    IdentityProviderProtocol,
    TenantContext,
    UserContext,
    Permission,
    get_permissions_for_roles,
)


logger = structlog.get_logger(__name__)


@dataclass
class APIKeyRecord:
    """Record of an API key with associated metadata.

    Attributes:
        key_id: Unique identifier for this key
        key_hash: SHA-256 hash of the API key (never store plaintext)
        tenant_id: Associated tenant
        user_id: Associated user (service account)
        name: Human-readable name for this key
        roles: Roles granted to this key
        created_at: When the key was created
        expires_at: Optional expiration time
        last_used_at: When the key was last used
        metadata: Additional key metadata
        is_active: Whether the key is currently active
    """

    key_id: str
    key_hash: str
    tenant_id: str
    user_id: str
    name: str
    roles: Set[str] = field(default_factory=set)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = True

    def is_expired(self) -> bool:
        """Check if the API key has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def is_valid(self) -> bool:
        """Check if the API key is valid for use."""
        return self.is_active and not self.is_expired()


class APIKeyProvider:
    """API key-based identity provider implementing IdentityProviderProtocol.

    This provider validates API keys for service-to-service authentication
    and programmatic access. Keys are stored hashed, never in plaintext.
    """

    # Prefix for API keys to make them identifiable
    KEY_PREFIX = "tf_"

    def __init__(
        self,
        tenant_store: Optional[Dict[str, TenantContext]] = None,
    ):
        """Initialize the API key provider.

        Args:
            tenant_store: Optional in-memory tenant store for development
        """
        self._tenant_store = tenant_store or {}
        self._key_store: Dict[str, APIKeyRecord] = {}  # key_hash -> record
        self._user_store: Dict[str, Dict[str, UserContext]] = {}

    async def validate_token(self, token: str) -> Optional[UserContext]:
        """Validate a token - delegates to validate_api_key.

        Args:
            token: The token string (API key)

        Returns:
            UserContext if valid, None otherwise
        """
        return await self.validate_api_key(token)

    async def validate_api_key(self, api_key: str) -> Optional[UserContext]:
        """Validate an API key and return user context.

        Args:
            api_key: The API key to validate

        Returns:
            UserContext if valid, None otherwise
        """
        try:
            # Check key format
            if not api_key.startswith(self.KEY_PREFIX):
                logger.debug("api_key.invalid.prefix")
                return None

            # Hash the key for lookup
            key_hash = self._hash_key(api_key)
            record = self._key_store.get(key_hash)

            if record is None:
                logger.warning("api_key.not.found")
                return None

            if not record.is_valid():
                logger.warning(
                    "api_key.invalid",
                    key_id=record.key_id,
                    is_active=record.is_active,
                    is_expired=record.is_expired(),
                )
                return None

            # Update last used timestamp
            record.last_used_at = datetime.now(timezone.utc)

            # Build user context
            permissions = get_permissions_for_roles(record.roles)

            logger.info(
                "api_key.validated",
                key_id=record.key_id,
                tenant_id=record.tenant_id,
                user_id=record.user_id,
            )

            return UserContext(
                user_id=record.user_id,
                tenant_id=record.tenant_id,
                username=record.name,
                roles=record.roles,
                permissions=permissions,
                attributes={"key_id": record.key_id, **record.metadata},
                authenticated_at=datetime.now(timezone.utc),
                token_expires_at=record.expires_at,
                metadata={"auth_method": "api_key"},
            )

        except Exception as e:
            logger.warning("api_key.validation.failed", error=str(e))
            return None

    async def get_tenant(self, tenant_id: str) -> Optional[TenantContext]:
        """Retrieve tenant context by ID.

        Args:
            tenant_id: The tenant identifier

        Returns:
            TenantContext if found, None otherwise
        """
        return self._tenant_store.get(tenant_id)

    async def get_user(self, user_id: str, tenant_id: str) -> Optional[UserContext]:
        """Retrieve user context by ID within a tenant.

        Args:
            user_id: The user identifier
            tenant_id: The tenant identifier

        Returns:
            UserContext if found, None otherwise
        """
        tenant_users = self._user_store.get(tenant_id, {})
        return tenant_users.get(user_id)

    def create_api_key(
        self,
        tenant_id: str,
        user_id: str,
        name: str,
        roles: Optional[Set[str]] = None,
        expires_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, APIKeyRecord]:
        """Create a new API key.

        Args:
            tenant_id: The tenant this key belongs to
            user_id: The user (service account) this key represents
            name: Human-readable name for the key
            roles: Roles granted to this key
            expires_at: Optional expiration time
            metadata: Optional metadata

        Returns:
            Tuple of (plaintext_key, record)
            IMPORTANT: Store the plaintext key securely - it cannot be retrieved later!
        """
        # Generate a secure random key
        random_part = secrets.token_urlsafe(32)
        plaintext_key = f"{self.KEY_PREFIX}{random_part}"

        # Hash for storage
        key_hash = self._hash_key(plaintext_key)
        key_id = secrets.token_hex(8)

        record = APIKeyRecord(
            key_id=key_id,
            key_hash=key_hash,
            tenant_id=tenant_id,
            user_id=user_id,
            name=name,
            roles=roles or {"operator"},
            expires_at=expires_at,
            metadata=metadata or {},
        )

        self._key_store[key_hash] = record

        logger.info(
            "api_key.created",
            key_id=key_id,
            tenant_id=tenant_id,
            user_id=user_id,
            name=name,
        )

        return plaintext_key, record

    def revoke_api_key(self, key_id: str) -> bool:
        """Revoke an API key by its ID.

        Args:
            key_id: The key identifier

        Returns:
            True if key was found and revoked, False otherwise
        """
        for record in self._key_store.values():
            if record.key_id == key_id:
                record.is_active = False
                logger.info("api_key.revoked", key_id=key_id)
                return True

        logger.warning("api_key.revoke.not_found", key_id=key_id)
        return False

    def list_api_keys(self, tenant_id: str) -> list[APIKeyRecord]:
        """List all API keys for a tenant.

        Args:
            tenant_id: The tenant to list keys for

        Returns:
            List of API key records (without the actual keys)
        """
        return [
            record
            for record in self._key_store.values()
            if record.tenant_id == tenant_id
        ]

    def register_tenant(self, tenant: TenantContext) -> None:
        """Register a tenant in the in-memory store.

        Args:
            tenant: The tenant context to register
        """
        self._tenant_store[tenant.tenant_id] = tenant

    def _hash_key(self, api_key: str) -> str:
        """Hash an API key for secure storage/lookup.

        Args:
            api_key: The plaintext API key

        Returns:
            SHA-256 hash of the key
        """
        return hashlib.sha256(api_key.encode("utf-8")).hexdigest()
