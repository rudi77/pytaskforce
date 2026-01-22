"""Identity protocols for multi-tenant authentication and authorization.

This module defines the protocols for identity management in a multi-tenant
enterprise environment. All implementations must follow these protocols to
ensure proper tenant isolation and user context propagation.
"""

from typing import Protocol, Optional, Dict, Any, List, Set, runtime_checkable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class Permission(Enum):
    """Enumeration of available permissions in the system."""

    # Agent permissions
    AGENT_CREATE = "agent:create"
    AGENT_READ = "agent:read"
    AGENT_UPDATE = "agent:update"
    AGENT_DELETE = "agent:delete"
    AGENT_EXECUTE = "agent:execute"

    # Session permissions
    SESSION_CREATE = "session:create"
    SESSION_READ = "session:read"
    SESSION_DELETE = "session:delete"

    # Tool permissions
    TOOL_EXECUTE = "tool:execute"
    TOOL_READ = "tool:read"

    # Memory permissions
    MEMORY_READ = "memory:read"
    MEMORY_WRITE = "memory:write"
    MEMORY_DELETE = "memory:delete"

    # Admin permissions
    TENANT_MANAGE = "tenant:manage"
    USER_MANAGE = "user:manage"
    ROLE_MANAGE = "role:manage"
    POLICY_MANAGE = "policy:manage"
    AUDIT_READ = "audit:read"

    # System permissions
    SYSTEM_CONFIG = "system:config"
    SYSTEM_METRICS = "system:metrics"


class ResourceType(Enum):
    """Types of resources that can be protected by RBAC."""

    AGENT = "agent"
    SESSION = "session"
    TOOL = "tool"
    MEMORY = "memory"
    TENANT = "tenant"
    USER = "user"
    ROLE = "role"
    POLICY = "policy"
    REPORT = "report"


@dataclass(frozen=True)
class TenantContext:
    """Immutable context representing a tenant (organization).

    Attributes:
        tenant_id: Unique identifier for the tenant
        name: Human-readable tenant name
        settings: Tenant-specific configuration settings
        created_at: Timestamp when tenant was created
        metadata: Additional tenant metadata
    """

    tenant_id: str
    name: str
    settings: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a tenant-specific setting."""
        return self.settings.get(key, default)

    def has_feature(self, feature: str) -> bool:
        """Check if tenant has a specific feature enabled."""
        features = self.settings.get("features", [])
        return feature in features


@dataclass(frozen=True)
class UserContext:
    """Immutable context representing an authenticated user.

    Attributes:
        user_id: Unique identifier for the user
        tenant_id: ID of the tenant this user belongs to
        username: User's login name
        email: User's email address
        roles: Set of role names assigned to the user
        permissions: Derived set of permissions from roles
        attributes: Additional user attributes (e.g., department, team)
        authenticated_at: Timestamp of authentication
        token_expires_at: When the auth token expires
        metadata: Additional user metadata
    """

    user_id: str
    tenant_id: str
    username: str
    email: Optional[str] = None
    roles: Set[str] = field(default_factory=set)
    permissions: Set[Permission] = field(default_factory=set)
    attributes: Dict[str, Any] = field(default_factory=dict)
    authenticated_at: Optional[datetime] = None
    token_expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def has_permission(self, permission: Permission) -> bool:
        """Check if user has a specific permission."""
        return permission in self.permissions

    def has_any_permission(self, permissions: Set[Permission]) -> bool:
        """Check if user has any of the specified permissions."""
        return bool(self.permissions & permissions)

    def has_all_permissions(self, permissions: Set[Permission]) -> bool:
        """Check if user has all of the specified permissions."""
        return permissions <= self.permissions

    def has_role(self, role: str) -> bool:
        """Check if user has a specific role."""
        return role in self.roles

    def get_attribute(self, key: str, default: Any = None) -> Any:
        """Get a user attribute."""
        return self.attributes.get(key, default)

    def is_admin(self) -> bool:
        """Check if user has admin role."""
        return "admin" in self.roles or self.has_permission(Permission.TENANT_MANAGE)


@dataclass
class Role:
    """Definition of a role with associated permissions.

    Attributes:
        role_id: Unique identifier for the role
        name: Human-readable role name
        description: Description of the role's purpose
        permissions: Set of permissions granted by this role
        tenant_id: Optional tenant ID (None for system roles)
        is_system_role: Whether this is a built-in system role
        metadata: Additional role metadata
    """

    role_id: str
    name: str
    description: str
    permissions: Set[Permission]
    tenant_id: Optional[str] = None
    is_system_role: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyDecision:
    """Result of a policy evaluation.

    Attributes:
        allowed: Whether the action is permitted
        reason: Human-readable explanation of the decision
        matched_policy: Name of the policy that made the decision
        audit_info: Information for audit logging
    """

    allowed: bool
    reason: str
    matched_policy: Optional[str] = None
    audit_info: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class IdentityProviderProtocol(Protocol):
    """Protocol for identity provider implementations.

    Identity providers are responsible for validating tokens and
    returning user/tenant context information.
    """

    async def validate_token(self, token: str) -> Optional[UserContext]:
        """Validate a token and return the associated user context.

        Args:
            token: The authentication token to validate

        Returns:
            UserContext if token is valid, None otherwise
        """
        ...

    async def validate_api_key(self, api_key: str) -> Optional[UserContext]:
        """Validate an API key and return the associated user context.

        Args:
            api_key: The API key to validate

        Returns:
            UserContext if API key is valid, None otherwise
        """
        ...

    async def get_tenant(self, tenant_id: str) -> Optional[TenantContext]:
        """Retrieve tenant context by ID.

        Args:
            tenant_id: The tenant identifier

        Returns:
            TenantContext if tenant exists, None otherwise
        """
        ...

    async def get_user(self, user_id: str, tenant_id: str) -> Optional[UserContext]:
        """Retrieve user context by ID within a tenant.

        Args:
            user_id: The user identifier
            tenant_id: The tenant identifier

        Returns:
            UserContext if user exists in tenant, None otherwise
        """
        ...


@runtime_checkable
class PolicyEngineProtocol(Protocol):
    """Protocol for RBAC policy engine implementations.

    Policy engines evaluate access requests against defined policies
    to determine if an action should be allowed.
    """

    async def evaluate(
        self,
        user: UserContext,
        action: Permission,
        resource_type: ResourceType,
        resource_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> PolicyDecision:
        """Evaluate a policy decision.

        Args:
            user: The user requesting the action
            action: The permission being requested
            resource_type: The type of resource being accessed
            resource_id: Optional specific resource identifier
            context: Additional context for policy evaluation

        Returns:
            PolicyDecision indicating whether the action is allowed
        """
        ...

    async def get_user_permissions(
        self,
        user: UserContext,
        resource_type: Optional[ResourceType] = None,
    ) -> Set[Permission]:
        """Get all permissions for a user, optionally filtered by resource type.

        Args:
            user: The user to get permissions for
            resource_type: Optional filter for resource type

        Returns:
            Set of permissions the user has
        """
        ...


@runtime_checkable
class TenantManagerProtocol(Protocol):
    """Protocol for tenant management operations."""

    async def create_tenant(
        self,
        name: str,
        settings: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TenantContext:
        """Create a new tenant.

        Args:
            name: Human-readable tenant name
            settings: Optional tenant settings
            metadata: Optional tenant metadata

        Returns:
            The created TenantContext
        """
        ...

    async def update_tenant(
        self,
        tenant_id: str,
        name: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TenantContext:
        """Update an existing tenant.

        Args:
            tenant_id: The tenant to update
            name: Optional new name
            settings: Optional settings to merge
            metadata: Optional metadata to merge

        Returns:
            The updated TenantContext
        """
        ...

    async def delete_tenant(self, tenant_id: str) -> bool:
        """Delete a tenant.

        Args:
            tenant_id: The tenant to delete

        Returns:
            True if deleted, False if not found
        """
        ...

    async def list_tenants(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> List[TenantContext]:
        """List all tenants.

        Args:
            limit: Maximum number of tenants to return
            offset: Number of tenants to skip

        Returns:
            List of TenantContext objects
        """
        ...


@runtime_checkable
class UserManagerProtocol(Protocol):
    """Protocol for user management operations."""

    async def create_user(
        self,
        tenant_id: str,
        username: str,
        email: Optional[str] = None,
        roles: Optional[Set[str]] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> UserContext:
        """Create a new user within a tenant.

        Args:
            tenant_id: The tenant the user belongs to
            username: The user's login name
            email: Optional email address
            roles: Optional set of role names
            attributes: Optional user attributes

        Returns:
            The created UserContext
        """
        ...

    async def update_user(
        self,
        user_id: str,
        tenant_id: str,
        username: Optional[str] = None,
        email: Optional[str] = None,
        roles: Optional[Set[str]] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> UserContext:
        """Update an existing user.

        Args:
            user_id: The user to update
            tenant_id: The tenant the user belongs to
            username: Optional new username
            email: Optional new email
            roles: Optional new roles (replaces existing)
            attributes: Optional attributes to merge

        Returns:
            The updated UserContext
        """
        ...

    async def delete_user(self, user_id: str, tenant_id: str) -> bool:
        """Delete a user.

        Args:
            user_id: The user to delete
            tenant_id: The tenant the user belongs to

        Returns:
            True if deleted, False if not found
        """
        ...

    async def list_users(
        self,
        tenant_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[UserContext]:
        """List users within a tenant.

        Args:
            tenant_id: The tenant to list users for
            limit: Maximum number of users to return
            offset: Number of users to skip

        Returns:
            List of UserContext objects
        """
        ...


@runtime_checkable
class RoleManagerProtocol(Protocol):
    """Protocol for role management operations."""

    async def create_role(
        self,
        name: str,
        description: str,
        permissions: Set[Permission],
        tenant_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Role:
        """Create a new role.

        Args:
            name: Human-readable role name
            description: Description of the role
            permissions: Set of permissions for this role
            tenant_id: Optional tenant ID for tenant-specific roles
            metadata: Optional role metadata

        Returns:
            The created Role
        """
        ...

    async def update_role(
        self,
        role_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        permissions: Optional[Set[Permission]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Role:
        """Update an existing role.

        Args:
            role_id: The role to update
            name: Optional new name
            description: Optional new description
            permissions: Optional new permissions (replaces existing)
            metadata: Optional metadata to merge

        Returns:
            The updated Role
        """
        ...

    async def delete_role(self, role_id: str) -> bool:
        """Delete a role.

        Args:
            role_id: The role to delete

        Returns:
            True if deleted, False if not found
        """
        ...

    async def get_role(self, role_id: str) -> Optional[Role]:
        """Get a role by ID.

        Args:
            role_id: The role identifier

        Returns:
            Role if found, None otherwise
        """
        ...

    async def list_roles(
        self,
        tenant_id: Optional[str] = None,
        include_system_roles: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Role]:
        """List roles.

        Args:
            tenant_id: Optional tenant to filter by
            include_system_roles: Whether to include system roles
            limit: Maximum number of roles to return
            offset: Number of roles to skip

        Returns:
            List of Role objects
        """
        ...


# Default system roles with predefined permissions
SYSTEM_ROLES: Dict[str, Role] = {
    "admin": Role(
        role_id="system:admin",
        name="Admin",
        description="Full administrative access to the tenant",
        permissions={
            Permission.AGENT_CREATE,
            Permission.AGENT_READ,
            Permission.AGENT_UPDATE,
            Permission.AGENT_DELETE,
            Permission.AGENT_EXECUTE,
            Permission.SESSION_CREATE,
            Permission.SESSION_READ,
            Permission.SESSION_DELETE,
            Permission.TOOL_EXECUTE,
            Permission.TOOL_READ,
            Permission.MEMORY_READ,
            Permission.MEMORY_WRITE,
            Permission.MEMORY_DELETE,
            Permission.USER_MANAGE,
            Permission.ROLE_MANAGE,
            Permission.POLICY_MANAGE,
            Permission.AUDIT_READ,
        },
        is_system_role=True,
    ),
    "agent_designer": Role(
        role_id="system:agent_designer",
        name="Agent Designer",
        description="Can create and manage agents",
        permissions={
            Permission.AGENT_CREATE,
            Permission.AGENT_READ,
            Permission.AGENT_UPDATE,
            Permission.AGENT_DELETE,
            Permission.TOOL_READ,
            Permission.SESSION_READ,
        },
        is_system_role=True,
    ),
    "operator": Role(
        role_id="system:operator",
        name="Operator",
        description="Can execute agents and manage sessions",
        permissions={
            Permission.AGENT_READ,
            Permission.AGENT_EXECUTE,
            Permission.SESSION_CREATE,
            Permission.SESSION_READ,
            Permission.SESSION_DELETE,
            Permission.TOOL_EXECUTE,
            Permission.TOOL_READ,
            Permission.MEMORY_READ,
            Permission.MEMORY_WRITE,
        },
        is_system_role=True,
    ),
    "auditor": Role(
        role_id="system:auditor",
        name="Auditor",
        description="Read-only access for compliance and auditing",
        permissions={
            Permission.AGENT_READ,
            Permission.SESSION_READ,
            Permission.TOOL_READ,
            Permission.MEMORY_READ,
            Permission.AUDIT_READ,
        },
        is_system_role=True,
    ),
    "viewer": Role(
        role_id="system:viewer",
        name="Viewer",
        description="Basic read-only access",
        permissions={
            Permission.AGENT_READ,
            Permission.SESSION_READ,
            Permission.TOOL_READ,
        },
        is_system_role=True,
    ),
}


def get_permissions_for_roles(role_names: Set[str]) -> Set[Permission]:
    """Get combined permissions for a set of role names.

    Args:
        role_names: Set of role names to look up

    Returns:
        Combined set of permissions from all roles
    """
    permissions: Set[Permission] = set()
    for role_name in role_names:
        if role_name in SYSTEM_ROLES:
            permissions.update(SYSTEM_ROLES[role_name].permissions)
    return permissions
