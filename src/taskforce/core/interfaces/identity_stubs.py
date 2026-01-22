"""Minimal identity stubs for type checking without enterprise dependency.

This module provides runtime_checkable protocols that define the minimum
interface needed for identity-aware code in the base package. The full
implementations live in taskforce-enterprise.

These stubs allow:
- Type checking in the base package
- Optional enterprise integration without hard dependencies
- Graceful fallback when enterprise is not installed

Usage:
    from taskforce.core.interfaces.identity_stubs import UserContextProtocol

    def process_with_user(user: UserContextProtocol | None) -> None:
        if user is not None:
            print(f"Processing for user {user.user_id}")
"""

from typing import Protocol, Optional, Any, Set, runtime_checkable
from datetime import datetime


@runtime_checkable
class TenantContextProtocol(Protocol):
    """Minimal protocol for tenant context.

    This defines the minimum interface needed for tenant-aware operations.
    The full TenantContext class is in taskforce-enterprise.
    """

    tenant_id: str
    name: str

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a tenant-specific setting."""
        ...

    def has_feature(self, feature: str) -> bool:
        """Check if tenant has a specific feature enabled."""
        ...


@runtime_checkable
class UserContextProtocol(Protocol):
    """Minimal protocol for user context.

    This defines the minimum interface needed for user-aware operations.
    The full UserContext class is in taskforce-enterprise.
    """

    user_id: str
    tenant_id: str
    username: str
    email: Optional[str]
    roles: Set[str]

    def has_permission(self, permission: Any) -> bool:
        """Check if user has a specific permission."""
        ...

    def has_role(self, role: str) -> bool:
        """Check if user has a specific role."""
        ...

    def is_admin(self) -> bool:
        """Check if user has admin role."""
        ...


@runtime_checkable
class IdentityProviderProtocol(Protocol):
    """Minimal protocol for identity providers.

    This defines the minimum interface for validating credentials.
    """

    async def validate_token(self, token: str) -> Optional[UserContextProtocol]:
        """Validate a token and return user context."""
        ...

    async def validate_api_key(self, api_key: str) -> Optional[UserContextProtocol]:
        """Validate an API key and return user context."""
        ...

    async def get_tenant(self, tenant_id: str) -> Optional[TenantContextProtocol]:
        """Get tenant by ID."""
        ...


@runtime_checkable
class PolicyEngineProtocol(Protocol):
    """Minimal protocol for policy engines.

    This defines the minimum interface for policy evaluation.
    """

    async def evaluate(
        self,
        user: UserContextProtocol,
        action: Any,
        resource_type: Any,
        resource_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Evaluate a policy decision."""
        ...


# Simple dataclass-like structures for fallback when enterprise not installed

class AnonymousUser:
    """Fallback anonymous user when enterprise is not installed.

    This provides a minimal user context for unauthenticated access
    in the base package.
    """

    def __init__(self, tenant_id: str = "default"):
        self.user_id = "anonymous"
        self.tenant_id = tenant_id
        self.username = "anonymous"
        self.email = None
        self.roles: Set[str] = {"viewer"}
        self._is_anonymous = True

    def has_permission(self, permission: Any) -> bool:
        """Anonymous users have minimal permissions."""
        return False

    def has_role(self, role: str) -> bool:
        """Check if user has role."""
        return role in self.roles

    def is_admin(self) -> bool:
        """Anonymous users are never admin."""
        return False


class DefaultTenant:
    """Fallback default tenant when enterprise is not installed.

    This provides a minimal tenant context for single-tenant mode.
    """

    def __init__(self):
        self.tenant_id = "default"
        self.name = "Default Tenant"
        self._settings: dict[str, Any] = {
            "features": ["basic"],
        }

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting."""
        return self._settings.get(key, default)

    def has_feature(self, feature: str) -> bool:
        """Check if feature is enabled."""
        features = self._settings.get("features", [])
        return feature in features


def create_anonymous_user(tenant_id: str = "default") -> AnonymousUser:
    """Create an anonymous user for unauthenticated access.

    Args:
        tenant_id: The tenant ID to associate with

    Returns:
        AnonymousUser instance
    """
    return AnonymousUser(tenant_id)


def create_default_tenant() -> DefaultTenant:
    """Create default tenant for single-tenant mode.

    Returns:
        DefaultTenant instance
    """
    return DefaultTenant()


def is_enterprise_identity_available() -> bool:
    """Check if full enterprise identity module is available.

    Returns:
        True if taskforce-enterprise identity is installed
    """
    try:
        from taskforce.core.interfaces.identity import UserContext  # noqa: F401
        return True
    except ImportError:
        return False
