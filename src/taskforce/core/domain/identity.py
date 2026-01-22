"""Identity domain models and utilities.

This module provides domain-level identity management including context
propagation, session scoping, and tenant isolation utilities.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, TypeVar, Generic
from datetime import datetime, timezone
from contextvars import ContextVar
import uuid


def _utcnow() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)

from taskforce.core.interfaces.identity import (
    TenantContext,
    UserContext,
    Permission,
    get_permissions_for_roles,
)


# Context variables for request-scoped identity propagation
_current_tenant: ContextVar[Optional[TenantContext]] = ContextVar(
    "current_tenant", default=None
)
_current_user: ContextVar[Optional[UserContext]] = ContextVar(
    "current_user", default=None
)


def get_current_tenant() -> Optional[TenantContext]:
    """Get the current tenant context from the request scope."""
    return _current_tenant.get()


def set_current_tenant(tenant: Optional[TenantContext]) -> None:
    """Set the current tenant context for the request scope."""
    _current_tenant.set(tenant)


def get_current_user() -> Optional[UserContext]:
    """Get the current user context from the request scope."""
    return _current_user.get()


def set_current_user(user: Optional[UserContext]) -> None:
    """Set the current user context for the request scope."""
    _current_user.set(user)


def require_tenant() -> TenantContext:
    """Get current tenant, raising if not set.

    Returns:
        Current TenantContext

    Raises:
        RuntimeError: If no tenant is set in the current context
    """
    tenant = get_current_tenant()
    if tenant is None:
        raise RuntimeError("No tenant context available - authentication required")
    return tenant


def require_user() -> UserContext:
    """Get current user, raising if not set.

    Returns:
        Current UserContext

    Raises:
        RuntimeError: If no user is set in the current context
    """
    user = get_current_user()
    if user is None:
        raise RuntimeError("No user context available - authentication required")
    return user


@dataclass
class IdentityToken:
    """Represents a parsed identity token with claims.

    Attributes:
        token_id: Unique identifier for the token
        token_type: Type of token (jwt, api_key, service)
        subject: Subject identifier (user_id or service_id)
        tenant_id: Associated tenant identifier
        issued_at: When the token was issued
        expires_at: When the token expires
        claims: Additional token claims
        raw_token: The original token string
    """

    token_id: str
    token_type: str
    subject: str
    tenant_id: str
    issued_at: datetime
    expires_at: datetime
    claims: Dict[str, Any] = field(default_factory=dict)
    raw_token: Optional[str] = None

    def is_expired(self) -> bool:
        """Check if the token has expired."""
        now = datetime.now(timezone.utc)
        # Handle both naive and aware datetimes
        if self.expires_at.tzinfo is None:
            return now.replace(tzinfo=None) > self.expires_at
        return now > self.expires_at

    def get_claim(self, key: str, default: Any = None) -> Any:
        """Get a specific claim from the token."""
        return self.claims.get(key, default)


@dataclass
class AuthenticationResult:
    """Result of an authentication attempt.

    Attributes:
        success: Whether authentication succeeded
        user: The authenticated user context (if successful)
        tenant: The tenant context (if successful)
        token: The parsed token (if successful)
        error: Error message (if failed)
        error_code: Machine-readable error code (if failed)
    """

    success: bool
    user: Optional[UserContext] = None
    tenant: Optional[TenantContext] = None
    token: Optional[IdentityToken] = None
    error: Optional[str] = None
    error_code: Optional[str] = None

    @classmethod
    def authenticated(
        cls,
        user: UserContext,
        tenant: TenantContext,
        token: Optional[IdentityToken] = None,
    ) -> "AuthenticationResult":
        """Create a successful authentication result."""
        return cls(success=True, user=user, tenant=tenant, token=token)

    @classmethod
    def failed(cls, error: str, error_code: str = "AUTH_FAILED") -> "AuthenticationResult":
        """Create a failed authentication result."""
        return cls(success=False, error=error, error_code=error_code)


T = TypeVar("T")


@dataclass
class TenantScoped(Generic[T]):
    """Wrapper for tenant-scoped data.

    This class ensures that data is always associated with a specific tenant,
    preventing accidental cross-tenant data access.

    Attributes:
        tenant_id: The tenant this data belongs to
        data: The actual data
        created_at: When this scoped data was created
        created_by: User who created this data
    """

    tenant_id: str
    data: T
    created_at: datetime = field(default_factory=_utcnow)
    created_by: Optional[str] = None

    def validate_access(self, user: UserContext) -> bool:
        """Validate that the user can access this tenant-scoped data."""
        return user.tenant_id == self.tenant_id


@dataclass
class SessionIdentity:
    """Identity information attached to an agent session.

    This tracks who created and owns a session for audit and access control.

    Attributes:
        session_id: The unique session identifier
        tenant_id: The tenant this session belongs to
        user_id: The user who created/owns the session
        created_at: When the session was created
        last_accessed_at: When the session was last accessed
        metadata: Additional session metadata
    """

    session_id: str
    tenant_id: str
    user_id: str
    created_at: datetime = field(default_factory=_utcnow)
    last_accessed_at: datetime = field(default_factory=_utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        """Update the last accessed timestamp."""
        self.last_accessed_at = _utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat(),
            "last_accessed_at": self.last_accessed_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionIdentity":
        """Create from dictionary."""
        return cls(
            session_id=data["session_id"],
            tenant_id=data["tenant_id"],
            user_id=data["user_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            last_accessed_at=datetime.fromisoformat(data["last_accessed_at"]),
            metadata=data.get("metadata", {}),
        )


def create_tenant_session_id(tenant_id: str, session_id: Optional[str] = None) -> str:
    """Create a tenant-namespaced session ID.

    This ensures sessions are isolated per tenant even if UUIDs collide.

    Args:
        tenant_id: The tenant identifier
        session_id: Optional specific session ID (UUID generated if not provided)

    Returns:
        Namespaced session ID in format: tenant_id:session_id
    """
    if session_id is None:
        session_id = str(uuid.uuid4())
    return f"{tenant_id}:{session_id}"


def parse_tenant_session_id(namespaced_id: str) -> tuple[str, str]:
    """Parse a tenant-namespaced session ID.

    Args:
        namespaced_id: The namespaced session ID

    Returns:
        Tuple of (tenant_id, session_id)

    Raises:
        ValueError: If the ID format is invalid
    """
    parts = namespaced_id.split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid namespaced session ID format: {namespaced_id}")
    return parts[0], parts[1]


def create_anonymous_user(tenant_id: str = "default") -> UserContext:
    """Create an anonymous user context for unauthenticated access.

    This is used for backward compatibility when auth is disabled.

    Args:
        tenant_id: The default tenant to use

    Returns:
        UserContext with minimal permissions
    """
    return UserContext(
        user_id="anonymous",
        tenant_id=tenant_id,
        username="anonymous",
        roles={"viewer"},
        permissions=get_permissions_for_roles({"viewer"}),
        metadata={"anonymous": True},
    )


def create_system_user(tenant_id: str = "system") -> UserContext:
    """Create a system user context for internal operations.

    This is used for background tasks and system-initiated actions.

    Args:
        tenant_id: The tenant context (usually "system")

    Returns:
        UserContext with elevated permissions
    """
    return UserContext(
        user_id="system",
        tenant_id=tenant_id,
        username="system",
        roles={"admin"},
        permissions=get_permissions_for_roles({"admin"}),
        metadata={"system": True},
    )


def create_default_tenant() -> TenantContext:
    """Create a default tenant context for single-tenant mode.

    Returns:
        Default TenantContext
    """
    return TenantContext(
        tenant_id="default",
        name="Default Tenant",
        settings={
            "features": ["basic"],
            "max_sessions": 100,
            "max_agents": 50,
        },
        created_at=_utcnow(),
        metadata={"default": True},
    )


@dataclass
class AuditEvent:
    """Audit event for tracking identity-related actions.

    Attributes:
        event_id: Unique identifier for the event
        event_type: Type of event (auth, access, admin, etc.)
        action: Specific action taken
        tenant_id: Tenant where the event occurred
        user_id: User who performed the action
        resource_type: Type of resource affected
        resource_id: Identifier of the affected resource
        success: Whether the action succeeded
        timestamp: When the event occurred
        details: Additional event details
        ip_address: Client IP address
        user_agent: Client user agent
    """

    event_id: str
    event_type: str
    action: str
    tenant_id: str
    user_id: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    success: bool = True
    timestamp: datetime = field(default_factory=_utcnow)
    details: Dict[str, Any] = field(default_factory=dict)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/storage."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "action": self.action,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "success": self.success,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
        }

    @classmethod
    def create(
        cls,
        event_type: str,
        action: str,
        user: Optional[UserContext] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        success: bool = True,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> "AuditEvent":
        """Create an audit event from context."""
        current_user = user or get_current_user()
        return cls(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            action=action,
            tenant_id=current_user.tenant_id if current_user else "unknown",
            user_id=current_user.user_id if current_user else "unknown",
            resource_type=resource_type,
            resource_id=resource_id,
            success=success,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
        )
