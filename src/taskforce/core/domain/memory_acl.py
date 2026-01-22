"""Memory Access Control List (ACL) domain models.

This module provides ACL-based access control for memory objects,
integrating with the RBAC system from Epic 1.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Set
from datetime import datetime, timezone
from enum import Enum
import uuid


def _utcnow() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class MemoryPermission(Enum):
    """Permissions for memory object access."""

    READ = "read"  # Can read memory content
    WRITE = "write"  # Can modify memory content
    DELETE = "delete"  # Can delete memory
    REFERENCE = "reference"  # Can reference in citations/evidence
    SHARE = "share"  # Can share with other users
    ADMIN = "admin"  # Full control including ACL management


class SensitivityLevel(Enum):
    """Sensitivity classification for memory objects."""

    PUBLIC = "public"  # Accessible to all authenticated users in tenant
    INTERNAL = "internal"  # Accessible to team members
    CONFIDENTIAL = "confidential"  # Restricted access
    RESTRICTED = "restricted"  # Highly restricted, explicit grants only


class MemoryScope(Enum):
    """Scope of memory object visibility."""

    GLOBAL = "global"  # Visible across tenants (system data)
    TENANT = "tenant"  # Visible within tenant
    PROJECT = "project"  # Visible within project
    SESSION = "session"  # Visible within session only
    PRIVATE = "private"  # Visible only to owner


@dataclass
class ACLEntry:
    """A single ACL entry granting permissions.

    Attributes:
        entry_id: Unique identifier for this entry
        principal_type: Type of principal (user, role, group)
        principal_id: ID of the principal
        permissions: Set of granted permissions
        granted_by: User who granted this access
        granted_at: When access was granted
        expires_at: Optional expiration time
        conditions: Optional conditions for access
    """

    entry_id: str
    principal_type: str  # "user", "role", "group"
    principal_id: str
    permissions: Set[MemoryPermission]
    granted_by: Optional[str] = None
    granted_at: datetime = field(default_factory=_utcnow)
    expires_at: Optional[datetime] = None
    conditions: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        """Check if this entry has expired.

        Returns:
            True if expired, False otherwise
        """
        if self.expires_at is None:
            return False
        return _utcnow() > self.expires_at

    def has_permission(self, permission: MemoryPermission) -> bool:
        """Check if this entry grants a specific permission.

        Args:
            permission: The permission to check

        Returns:
            True if permission is granted and not expired
        """
        if self.is_expired():
            return False
        return permission in self.permissions or MemoryPermission.ADMIN in self.permissions

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entry_id": self.entry_id,
            "principal_type": self.principal_type,
            "principal_id": self.principal_id,
            "permissions": [p.value for p in self.permissions],
            "granted_by": self.granted_by,
            "granted_at": self.granted_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "conditions": self.conditions,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ACLEntry":
        """Create from dictionary."""
        return cls(
            entry_id=data["entry_id"],
            principal_type=data["principal_type"],
            principal_id=data["principal_id"],
            permissions={MemoryPermission(p) for p in data["permissions"]},
            granted_by=data.get("granted_by"),
            granted_at=datetime.fromisoformat(data["granted_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            conditions=data.get("conditions", {}),
        )


@dataclass
class MemoryACL:
    """Access Control List for a memory object.

    Attributes:
        acl_id: Unique ACL identifier
        resource_id: ID of the memory resource
        resource_type: Type of resource (session, tool_result, etc.)
        owner_id: User ID of the owner
        tenant_id: Tenant ID
        scope: Visibility scope
        sensitivity: Sensitivity classification
        entries: List of ACL entries
        default_permissions: Default permissions for authenticated users
        created_at: When ACL was created
        metadata: Additional metadata
    """

    acl_id: str
    resource_id: str
    resource_type: str
    owner_id: str
    tenant_id: str
    scope: MemoryScope = MemoryScope.TENANT
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
    entries: List[ACLEntry] = field(default_factory=list)
    default_permissions: Set[MemoryPermission] = field(default_factory=set)
    created_at: datetime = field(default_factory=_utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_entry(
        self,
        principal_type: str,
        principal_id: str,
        permissions: Set[MemoryPermission],
        granted_by: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        conditions: Optional[Dict[str, Any]] = None,
    ) -> ACLEntry:
        """Add an ACL entry.

        Args:
            principal_type: Type of principal
            principal_id: ID of principal
            permissions: Permissions to grant
            granted_by: User granting access
            expires_at: Optional expiration
            conditions: Optional conditions

        Returns:
            The created ACL entry
        """
        entry = ACLEntry(
            entry_id=str(uuid.uuid4()),
            principal_type=principal_type,
            principal_id=principal_id,
            permissions=permissions,
            granted_by=granted_by,
            expires_at=expires_at,
            conditions=conditions or {},
        )
        self.entries.append(entry)
        return entry

    def remove_entry(self, entry_id: str) -> bool:
        """Remove an ACL entry.

        Args:
            entry_id: ID of entry to remove

        Returns:
            True if removed, False if not found
        """
        for i, entry in enumerate(self.entries):
            if entry.entry_id == entry_id:
                self.entries.pop(i)
                return True
        return False

    def get_entries_for_principal(
        self, principal_type: str, principal_id: str
    ) -> List[ACLEntry]:
        """Get all entries for a specific principal.

        Args:
            principal_type: Type of principal
            principal_id: ID of principal

        Returns:
            List of matching entries
        """
        return [
            e for e in self.entries
            if e.principal_type == principal_type and e.principal_id == principal_id
        ]

    def check_permission(
        self,
        user_id: str,
        roles: Set[str],
        permission: MemoryPermission,
    ) -> bool:
        """Check if a user has a specific permission.

        Args:
            user_id: User to check
            roles: User's roles
            permission: Permission to check

        Returns:
            True if permission is granted
        """
        # Owner always has full access
        if user_id == self.owner_id:
            return True

        # Check default permissions for authenticated users
        if permission in self.default_permissions:
            return True

        # Check user-specific entries
        for entry in self.entries:
            if entry.is_expired():
                continue

            if entry.principal_type == "user" and entry.principal_id == user_id:
                if entry.has_permission(permission):
                    return True

            if entry.principal_type == "role" and entry.principal_id in roles:
                if entry.has_permission(permission):
                    return True

        return False

    def get_effective_permissions(
        self, user_id: str, roles: Set[str]
    ) -> Set[MemoryPermission]:
        """Get all effective permissions for a user.

        Args:
            user_id: User to check
            roles: User's roles

        Returns:
            Set of effective permissions
        """
        permissions = set(self.default_permissions)

        # Owner has all permissions
        if user_id == self.owner_id:
            return set(MemoryPermission)

        # Collect from all matching entries
        for entry in self.entries:
            if entry.is_expired():
                continue

            match = False
            if entry.principal_type == "user" and entry.principal_id == user_id:
                match = True
            elif entry.principal_type == "role" and entry.principal_id in roles:
                match = True

            if match:
                permissions.update(entry.permissions)

        return permissions

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "acl_id": self.acl_id,
            "resource_id": self.resource_id,
            "resource_type": self.resource_type,
            "owner_id": self.owner_id,
            "tenant_id": self.tenant_id,
            "scope": self.scope.value,
            "sensitivity": self.sensitivity.value,
            "entries": [e.to_dict() for e in self.entries],
            "default_permissions": [p.value for p in self.default_permissions],
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryACL":
        """Create from dictionary."""
        acl = cls(
            acl_id=data["acl_id"],
            resource_id=data["resource_id"],
            resource_type=data["resource_type"],
            owner_id=data["owner_id"],
            tenant_id=data["tenant_id"],
            scope=MemoryScope(data.get("scope", "tenant")),
            sensitivity=SensitivityLevel(data.get("sensitivity", "internal")),
            default_permissions={MemoryPermission(p) for p in data.get("default_permissions", [])},
            created_at=datetime.fromisoformat(data["created_at"]),
            metadata=data.get("metadata", {}),
        )
        acl.entries = [ACLEntry.from_dict(e) for e in data.get("entries", [])]
        return acl


@dataclass
class ScopePolicy:
    """Policy defining scope-based access rules.

    Attributes:
        policy_id: Unique policy identifier
        name: Policy name
        description: Policy description
        scope: Affected scope
        sensitivity_levels: Allowed sensitivity levels
        max_retention_days: Maximum retention period
        requires_audit: Whether access requires audit
        allowed_roles: Roles that can access
    """

    policy_id: str
    name: str
    description: str = ""
    scope: MemoryScope = MemoryScope.TENANT
    sensitivity_levels: Set[SensitivityLevel] = field(
        default_factory=lambda: {SensitivityLevel.PUBLIC, SensitivityLevel.INTERNAL}
    )
    max_retention_days: Optional[int] = None
    requires_audit: bool = False
    allowed_roles: Set[str] = field(default_factory=set)

    def is_sensitivity_allowed(self, level: SensitivityLevel) -> bool:
        """Check if a sensitivity level is allowed by this policy.

        Args:
            level: Sensitivity level to check

        Returns:
            True if allowed
        """
        return level in self.sensitivity_levels

    def is_role_allowed(self, role: str) -> bool:
        """Check if a role is allowed by this policy.

        Args:
            role: Role to check

        Returns:
            True if allowed (or no role restrictions)
        """
        if not self.allowed_roles:
            return True
        return role in self.allowed_roles


class MemoryACLManager:
    """Manager for memory ACLs with policy enforcement."""

    def __init__(self, default_scope: MemoryScope = MemoryScope.TENANT):
        """Initialize the ACL manager.

        Args:
            default_scope: Default scope for new ACLs
        """
        self._acls: Dict[str, MemoryACL] = {}
        self._policies: Dict[str, ScopePolicy] = {}
        self._default_scope = default_scope

        # Set up default policies
        self._setup_default_policies()

    def _setup_default_policies(self) -> None:
        """Set up default scope policies."""
        self._policies["session_policy"] = ScopePolicy(
            policy_id="session_policy",
            name="Session Data Policy",
            description="Policy for session-scoped data",
            scope=MemoryScope.SESSION,
            sensitivity_levels={
                SensitivityLevel.PUBLIC,
                SensitivityLevel.INTERNAL,
                SensitivityLevel.CONFIDENTIAL,
            },
            max_retention_days=30,
        )

        self._policies["tenant_policy"] = ScopePolicy(
            policy_id="tenant_policy",
            name="Tenant Data Policy",
            description="Policy for tenant-scoped data",
            scope=MemoryScope.TENANT,
            sensitivity_levels={SensitivityLevel.PUBLIC, SensitivityLevel.INTERNAL},
            max_retention_days=365,
        )

        self._policies["restricted_policy"] = ScopePolicy(
            policy_id="restricted_policy",
            name="Restricted Data Policy",
            description="Policy for restricted data",
            scope=MemoryScope.PRIVATE,
            sensitivity_levels={SensitivityLevel.RESTRICTED},
            requires_audit=True,
            allowed_roles={"admin", "security_admin"},
        )

    def create_acl(
        self,
        resource_id: str,
        resource_type: str,
        owner_id: str,
        tenant_id: str,
        scope: Optional[MemoryScope] = None,
        sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL,
    ) -> MemoryACL:
        """Create a new ACL for a memory resource.

        Args:
            resource_id: Resource identifier
            resource_type: Type of resource
            owner_id: Owner user ID
            tenant_id: Tenant ID
            scope: Visibility scope (default: manager default)
            sensitivity: Sensitivity level

        Returns:
            The created MemoryACL
        """
        acl = MemoryACL(
            acl_id=str(uuid.uuid4()),
            resource_id=resource_id,
            resource_type=resource_type,
            owner_id=owner_id,
            tenant_id=tenant_id,
            scope=scope or self._default_scope,
            sensitivity=sensitivity,
        )

        # Set default permissions based on scope and sensitivity
        self._apply_default_permissions(acl)

        self._acls[resource_id] = acl
        return acl

    def _apply_default_permissions(self, acl: MemoryACL) -> None:
        """Apply default permissions based on scope and sensitivity.

        Args:
            acl: ACL to configure
        """
        if acl.scope == MemoryScope.GLOBAL:
            acl.default_permissions = {MemoryPermission.READ, MemoryPermission.REFERENCE}
        elif acl.scope == MemoryScope.TENANT:
            if acl.sensitivity == SensitivityLevel.PUBLIC:
                acl.default_permissions = {MemoryPermission.READ, MemoryPermission.REFERENCE}
            elif acl.sensitivity == SensitivityLevel.INTERNAL:
                acl.default_permissions = {MemoryPermission.READ}
            else:
                acl.default_permissions = set()
        elif acl.scope == MemoryScope.PROJECT:
            acl.default_permissions = {MemoryPermission.READ}
        else:  # SESSION or PRIVATE
            acl.default_permissions = set()

    def get_acl(self, resource_id: str) -> Optional[MemoryACL]:
        """Get ACL for a resource.

        Args:
            resource_id: Resource identifier

        Returns:
            MemoryACL if found, None otherwise
        """
        return self._acls.get(resource_id)

    def check_access(
        self,
        resource_id: str,
        user_id: str,
        tenant_id: str,
        roles: Set[str],
        permission: MemoryPermission,
    ) -> bool:
        """Check if a user has access to a resource.

        Args:
            resource_id: Resource to check
            user_id: User requesting access
            tenant_id: User's tenant
            roles: User's roles
            permission: Required permission

        Returns:
            True if access is granted
        """
        acl = self._acls.get(resource_id)
        if acl is None:
            return False

        # Check tenant isolation
        if acl.scope != MemoryScope.GLOBAL and acl.tenant_id != tenant_id:
            return False

        # Check scope policies
        policy = self._get_policy_for_acl(acl)
        if policy and not self._check_policy_compliance(acl, roles, policy):
            return False

        return acl.check_permission(user_id, roles, permission)

    def _get_policy_for_acl(self, acl: MemoryACL) -> Optional[ScopePolicy]:
        """Get the applicable policy for an ACL.

        Args:
            acl: The ACL to check

        Returns:
            Applicable policy if found
        """
        for policy in self._policies.values():
            if policy.scope == acl.scope:
                return policy
        return None

    def _check_policy_compliance(
        self, acl: MemoryACL, roles: Set[str], policy: ScopePolicy
    ) -> bool:
        """Check if access complies with policy.

        Args:
            acl: The ACL being accessed
            roles: User's roles
            policy: Policy to check

        Returns:
            True if compliant
        """
        if not policy.is_sensitivity_allowed(acl.sensitivity):
            return False

        if policy.allowed_roles:
            if not any(policy.is_role_allowed(role) for role in roles):
                return False

        return True

    def grant_access(
        self,
        resource_id: str,
        principal_type: str,
        principal_id: str,
        permissions: Set[MemoryPermission],
        granted_by: str,
        expires_at: Optional[datetime] = None,
    ) -> Optional[ACLEntry]:
        """Grant access to a resource.

        Args:
            resource_id: Resource to grant access to
            principal_type: Type of principal
            principal_id: ID of principal
            permissions: Permissions to grant
            granted_by: User granting access
            expires_at: Optional expiration

        Returns:
            The created ACL entry, or None if resource not found
        """
        acl = self._acls.get(resource_id)
        if acl is None:
            return None

        return acl.add_entry(
            principal_type=principal_type,
            principal_id=principal_id,
            permissions=permissions,
            granted_by=granted_by,
            expires_at=expires_at,
        )

    def revoke_access(self, resource_id: str, entry_id: str) -> bool:
        """Revoke an access grant.

        Args:
            resource_id: Resource ID
            entry_id: Entry ID to revoke

        Returns:
            True if revoked, False otherwise
        """
        acl = self._acls.get(resource_id)
        if acl is None:
            return False

        return acl.remove_entry(entry_id)

    def delete_acl(self, resource_id: str) -> bool:
        """Delete ACL for a resource.

        Args:
            resource_id: Resource ID

        Returns:
            True if deleted, False if not found
        """
        if resource_id in self._acls:
            del self._acls[resource_id]
            return True
        return False

    def add_policy(self, policy: ScopePolicy) -> None:
        """Add or update a scope policy.

        Args:
            policy: Policy to add
        """
        self._policies[policy.policy_id] = policy

    def get_policy(self, policy_id: str) -> Optional[ScopePolicy]:
        """Get a policy by ID.

        Args:
            policy_id: Policy identifier

        Returns:
            Policy if found
        """
        return self._policies.get(policy_id)

    def list_user_resources(
        self, user_id: str, tenant_id: str, roles: Set[str]
    ) -> List[str]:
        """List all resources a user can access.

        Args:
            user_id: User ID
            tenant_id: Tenant ID
            roles: User's roles

        Returns:
            List of accessible resource IDs
        """
        accessible = []
        for resource_id, acl in self._acls.items():
            if self.check_access(
                resource_id, user_id, tenant_id, roles, MemoryPermission.READ
            ):
                accessible.append(resource_id)
        return accessible
