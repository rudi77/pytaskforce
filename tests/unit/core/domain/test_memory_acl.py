"""Tests for Memory Access Control List (ACL) domain models."""

import pytest
from datetime import datetime, timezone, timedelta
from taskforce.core.domain.memory_acl import (
    MemoryPermission,
    SensitivityLevel,
    MemoryScope,
    ACLEntry,
    MemoryACL,
    ScopePolicy,
    MemoryACLManager,
)


class TestMemoryPermission:
    """Tests for MemoryPermission enum."""

    def test_permission_values(self):
        """Test permission enum values."""
        assert MemoryPermission.READ.value == "read"
        assert MemoryPermission.WRITE.value == "write"
        assert MemoryPermission.DELETE.value == "delete"
        assert MemoryPermission.REFERENCE.value == "reference"
        assert MemoryPermission.SHARE.value == "share"
        assert MemoryPermission.ADMIN.value == "admin"


class TestSensitivityLevel:
    """Tests for SensitivityLevel enum."""

    def test_sensitivity_levels(self):
        """Test sensitivity level values."""
        assert SensitivityLevel.PUBLIC.value == "public"
        assert SensitivityLevel.INTERNAL.value == "internal"
        assert SensitivityLevel.CONFIDENTIAL.value == "confidential"
        assert SensitivityLevel.RESTRICTED.value == "restricted"


class TestMemoryScope:
    """Tests for MemoryScope enum."""

    def test_scope_values(self):
        """Test scope enum values."""
        assert MemoryScope.GLOBAL.value == "global"
        assert MemoryScope.TENANT.value == "tenant"
        assert MemoryScope.PROJECT.value == "project"
        assert MemoryScope.SESSION.value == "session"
        assert MemoryScope.PRIVATE.value == "private"


class TestACLEntry:
    """Tests for ACLEntry dataclass."""

    def test_entry_creation(self):
        """Test creating a basic ACL entry."""
        entry = ACLEntry(
            entry_id="entry-1",
            principal_type="user",
            principal_id="user-123",
            permissions={MemoryPermission.READ, MemoryPermission.WRITE},
        )

        assert entry.entry_id == "entry-1"
        assert entry.principal_type == "user"
        assert entry.principal_id == "user-123"
        assert MemoryPermission.READ in entry.permissions
        assert MemoryPermission.WRITE in entry.permissions

    def test_entry_not_expired(self):
        """Test entry without expiration is not expired."""
        entry = ACLEntry(
            entry_id="entry-1",
            principal_type="user",
            principal_id="user-123",
            permissions={MemoryPermission.READ},
        )

        assert not entry.is_expired()

    def test_entry_expired(self):
        """Test entry with past expiration is expired."""
        entry = ACLEntry(
            entry_id="entry-1",
            principal_type="user",
            principal_id="user-123",
            permissions={MemoryPermission.READ},
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        assert entry.is_expired()

    def test_entry_not_yet_expired(self):
        """Test entry with future expiration is not expired."""
        entry = ACLEntry(
            entry_id="entry-1",
            principal_type="user",
            principal_id="user-123",
            permissions={MemoryPermission.READ},
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        assert not entry.is_expired()

    def test_has_permission(self):
        """Test checking permissions."""
        entry = ACLEntry(
            entry_id="entry-1",
            principal_type="user",
            principal_id="user-123",
            permissions={MemoryPermission.READ, MemoryPermission.WRITE},
        )

        assert entry.has_permission(MemoryPermission.READ)
        assert entry.has_permission(MemoryPermission.WRITE)
        assert not entry.has_permission(MemoryPermission.DELETE)

    def test_admin_permission_grants_all(self):
        """Test that admin permission grants all permissions."""
        entry = ACLEntry(
            entry_id="entry-1",
            principal_type="user",
            principal_id="user-123",
            permissions={MemoryPermission.ADMIN},
        )

        assert entry.has_permission(MemoryPermission.READ)
        assert entry.has_permission(MemoryPermission.WRITE)
        assert entry.has_permission(MemoryPermission.DELETE)

    def test_expired_entry_has_no_permissions(self):
        """Test expired entry grants no permissions."""
        entry = ACLEntry(
            entry_id="entry-1",
            principal_type="user",
            principal_id="user-123",
            permissions={MemoryPermission.READ},
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        assert not entry.has_permission(MemoryPermission.READ)

    def test_entry_to_dict(self):
        """Test serializing entry to dict."""
        entry = ACLEntry(
            entry_id="entry-1",
            principal_type="role",
            principal_id="admin",
            permissions={MemoryPermission.READ},
            granted_by="system",
        )

        result = entry.to_dict()

        assert result["entry_id"] == "entry-1"
        assert result["principal_type"] == "role"
        assert result["principal_id"] == "admin"
        assert "read" in result["permissions"]
        assert result["granted_by"] == "system"

    def test_entry_from_dict(self):
        """Test deserializing entry from dict."""
        data = {
            "entry_id": "entry-2",
            "principal_type": "user",
            "principal_id": "user-456",
            "permissions": ["read", "write"],
            "granted_at": "2025-01-01T12:00:00+00:00",
        }

        entry = ACLEntry.from_dict(data)

        assert entry.entry_id == "entry-2"
        assert entry.principal_type == "user"
        assert MemoryPermission.READ in entry.permissions
        assert MemoryPermission.WRITE in entry.permissions


class TestMemoryACL:
    """Tests for MemoryACL dataclass."""

    @pytest.fixture
    def basic_acl(self):
        """Create a basic ACL for testing."""
        return MemoryACL(
            acl_id="acl-123",
            resource_id="resource-456",
            resource_type="session",
            owner_id="owner-789",
            tenant_id="tenant-001",
        )

    def test_acl_creation(self, basic_acl):
        """Test creating a basic ACL."""
        assert basic_acl.acl_id == "acl-123"
        assert basic_acl.resource_id == "resource-456"
        assert basic_acl.owner_id == "owner-789"
        assert basic_acl.scope == MemoryScope.TENANT
        assert basic_acl.sensitivity == SensitivityLevel.INTERNAL

    def test_add_entry(self, basic_acl):
        """Test adding an ACL entry."""
        entry = basic_acl.add_entry(
            principal_type="user",
            principal_id="user-123",
            permissions={MemoryPermission.READ},
            granted_by="owner-789",
        )

        assert len(basic_acl.entries) == 1
        assert entry.principal_id == "user-123"
        assert entry.granted_by == "owner-789"

    def test_remove_entry(self, basic_acl):
        """Test removing an ACL entry."""
        entry = basic_acl.add_entry(
            principal_type="user",
            principal_id="user-123",
            permissions={MemoryPermission.READ},
        )

        result = basic_acl.remove_entry(entry.entry_id)

        assert result is True
        assert len(basic_acl.entries) == 0

    def test_remove_nonexistent_entry(self, basic_acl):
        """Test removing non-existent entry returns False."""
        result = basic_acl.remove_entry("nonexistent")

        assert result is False

    def test_get_entries_for_principal(self, basic_acl):
        """Test getting entries for a specific principal."""
        basic_acl.add_entry(
            principal_type="user",
            principal_id="user-123",
            permissions={MemoryPermission.READ},
        )
        basic_acl.add_entry(
            principal_type="user",
            principal_id="user-456",
            permissions={MemoryPermission.WRITE},
        )
        basic_acl.add_entry(
            principal_type="role",
            principal_id="admin",
            permissions={MemoryPermission.ADMIN},
        )

        entries = basic_acl.get_entries_for_principal("user", "user-123")

        assert len(entries) == 1
        assert entries[0].principal_id == "user-123"

    def test_owner_has_all_permissions(self, basic_acl):
        """Test that owner has all permissions."""
        assert basic_acl.check_permission("owner-789", set(), MemoryPermission.READ)
        assert basic_acl.check_permission("owner-789", set(), MemoryPermission.WRITE)
        assert basic_acl.check_permission("owner-789", set(), MemoryPermission.DELETE)
        assert basic_acl.check_permission("owner-789", set(), MemoryPermission.ADMIN)

    def test_check_permission_user_entry(self, basic_acl):
        """Test checking permissions via user entry."""
        basic_acl.add_entry(
            principal_type="user",
            principal_id="user-123",
            permissions={MemoryPermission.READ},
        )

        assert basic_acl.check_permission("user-123", set(), MemoryPermission.READ)
        assert not basic_acl.check_permission("user-123", set(), MemoryPermission.WRITE)

    def test_check_permission_role_entry(self, basic_acl):
        """Test checking permissions via role entry."""
        basic_acl.add_entry(
            principal_type="role",
            principal_id="editor",
            permissions={MemoryPermission.READ, MemoryPermission.WRITE},
        )

        assert basic_acl.check_permission("user-123", {"editor"}, MemoryPermission.READ)
        assert basic_acl.check_permission("user-123", {"editor"}, MemoryPermission.WRITE)
        assert not basic_acl.check_permission("user-123", {"viewer"}, MemoryPermission.WRITE)

    def test_check_default_permissions(self, basic_acl):
        """Test checking default permissions."""
        basic_acl.default_permissions = {MemoryPermission.READ}

        assert basic_acl.check_permission("any-user", set(), MemoryPermission.READ)
        assert not basic_acl.check_permission("any-user", set(), MemoryPermission.WRITE)

    def test_get_effective_permissions(self, basic_acl):
        """Test getting all effective permissions."""
        basic_acl.default_permissions = {MemoryPermission.READ}
        basic_acl.add_entry(
            principal_type="user",
            principal_id="user-123",
            permissions={MemoryPermission.WRITE},
        )
        basic_acl.add_entry(
            principal_type="role",
            principal_id="editor",
            permissions={MemoryPermission.DELETE},
        )

        permissions = basic_acl.get_effective_permissions("user-123", {"editor"})

        assert MemoryPermission.READ in permissions
        assert MemoryPermission.WRITE in permissions
        assert MemoryPermission.DELETE in permissions

    def test_owner_gets_all_permissions(self, basic_acl):
        """Test owner gets all permissions from effective permissions."""
        permissions = basic_acl.get_effective_permissions("owner-789", set())

        assert permissions == set(MemoryPermission)

    def test_acl_to_dict(self, basic_acl):
        """Test serializing ACL to dict."""
        basic_acl.add_entry(
            principal_type="user",
            principal_id="user-123",
            permissions={MemoryPermission.READ},
        )

        result = basic_acl.to_dict()

        assert result["acl_id"] == "acl-123"
        assert result["resource_id"] == "resource-456"
        assert result["scope"] == "tenant"
        assert len(result["entries"]) == 1

    def test_acl_from_dict(self):
        """Test deserializing ACL from dict."""
        data = {
            "acl_id": "acl-new",
            "resource_id": "resource-new",
            "resource_type": "tool_result",
            "owner_id": "owner-new",
            "tenant_id": "tenant-new",
            "scope": "project",
            "sensitivity": "confidential",
            "entries": [
                {
                    "entry_id": "entry-1",
                    "principal_type": "user",
                    "principal_id": "user-1",
                    "permissions": ["read"],
                    "granted_at": "2025-01-01T12:00:00+00:00",
                }
            ],
            "default_permissions": ["read", "reference"],
            "created_at": "2025-01-01T12:00:00+00:00",
            "metadata": {"custom": "value"},
        }

        acl = MemoryACL.from_dict(data)

        assert acl.acl_id == "acl-new"
        assert acl.scope == MemoryScope.PROJECT
        assert acl.sensitivity == SensitivityLevel.CONFIDENTIAL
        assert len(acl.entries) == 1
        assert MemoryPermission.READ in acl.default_permissions


class TestScopePolicy:
    """Tests for ScopePolicy dataclass."""

    def test_policy_creation(self):
        """Test creating a scope policy."""
        policy = ScopePolicy(
            policy_id="policy-1",
            name="Test Policy",
            description="A test policy",
            scope=MemoryScope.TENANT,
        )

        assert policy.policy_id == "policy-1"
        assert policy.name == "Test Policy"
        assert policy.scope == MemoryScope.TENANT

    def test_is_sensitivity_allowed(self):
        """Test sensitivity level checking."""
        policy = ScopePolicy(
            policy_id="policy-1",
            name="Test",
            sensitivity_levels={SensitivityLevel.PUBLIC, SensitivityLevel.INTERNAL},
        )

        assert policy.is_sensitivity_allowed(SensitivityLevel.PUBLIC)
        assert policy.is_sensitivity_allowed(SensitivityLevel.INTERNAL)
        assert not policy.is_sensitivity_allowed(SensitivityLevel.CONFIDENTIAL)

    def test_is_role_allowed_no_restrictions(self):
        """Test role checking with no restrictions."""
        policy = ScopePolicy(
            policy_id="policy-1",
            name="Test",
        )

        assert policy.is_role_allowed("any_role")
        assert policy.is_role_allowed("admin")

    def test_is_role_allowed_with_restrictions(self):
        """Test role checking with restrictions."""
        policy = ScopePolicy(
            policy_id="policy-1",
            name="Test",
            allowed_roles={"admin", "security_admin"},
        )

        assert policy.is_role_allowed("admin")
        assert policy.is_role_allowed("security_admin")
        assert not policy.is_role_allowed("viewer")


class TestMemoryACLManager:
    """Tests for MemoryACLManager."""

    @pytest.fixture
    def manager(self):
        """Create an ACL manager for testing."""
        return MemoryACLManager()

    def test_create_acl(self, manager):
        """Test creating an ACL through manager."""
        acl = manager.create_acl(
            resource_id="resource-1",
            resource_type="session",
            owner_id="owner-1",
            tenant_id="tenant-1",
        )

        assert acl.resource_id == "resource-1"
        assert acl.owner_id == "owner-1"
        assert acl.tenant_id == "tenant-1"

    def test_get_acl(self, manager):
        """Test retrieving an ACL."""
        manager.create_acl(
            resource_id="resource-1",
            resource_type="session",
            owner_id="owner-1",
            tenant_id="tenant-1",
        )

        acl = manager.get_acl("resource-1")

        assert acl is not None
        assert acl.resource_id == "resource-1"

    def test_get_nonexistent_acl(self, manager):
        """Test retrieving non-existent ACL returns None."""
        acl = manager.get_acl("nonexistent")

        assert acl is None

    def test_check_access_owner(self, manager):
        """Test access check for owner."""
        manager.create_acl(
            resource_id="resource-1",
            resource_type="session",
            owner_id="owner-1",
            tenant_id="tenant-1",
        )

        result = manager.check_access(
            resource_id="resource-1",
            user_id="owner-1",
            tenant_id="tenant-1",
            roles=set(),
            permission=MemoryPermission.DELETE,
        )

        assert result is True

    def test_check_access_wrong_tenant(self, manager):
        """Test access denied for wrong tenant."""
        manager.create_acl(
            resource_id="resource-1",
            resource_type="session",
            owner_id="owner-1",
            tenant_id="tenant-1",
        )

        result = manager.check_access(
            resource_id="resource-1",
            user_id="user-1",
            tenant_id="tenant-2",  # Different tenant
            roles=set(),
            permission=MemoryPermission.READ,
        )

        assert result is False

    def test_check_access_with_grant(self, manager):
        """Test access check with explicit grant."""
        manager.create_acl(
            resource_id="resource-1",
            resource_type="session",
            owner_id="owner-1",
            tenant_id="tenant-1",
        )
        manager.grant_access(
            resource_id="resource-1",
            principal_type="user",
            principal_id="user-1",
            permissions={MemoryPermission.READ},
            granted_by="owner-1",
        )

        result = manager.check_access(
            resource_id="resource-1",
            user_id="user-1",
            tenant_id="tenant-1",
            roles=set(),
            permission=MemoryPermission.READ,
        )

        assert result is True

    def test_grant_and_revoke_access(self, manager):
        """Test granting and revoking access."""
        manager.create_acl(
            resource_id="resource-1",
            resource_type="session",
            owner_id="owner-1",
            tenant_id="tenant-1",
        )

        # Use WRITE permission which is NOT in default_permissions
        entry = manager.grant_access(
            resource_id="resource-1",
            principal_type="user",
            principal_id="user-1",
            permissions={MemoryPermission.WRITE},
            granted_by="owner-1",
        )

        assert entry is not None

        # Verify access granted
        assert manager.check_access(
            "resource-1", "user-1", "tenant-1", set(), MemoryPermission.WRITE
        )

        # Revoke
        result = manager.revoke_access("resource-1", entry.entry_id)
        assert result is True

        # Verify access revoked (WRITE is not in default permissions)
        assert not manager.check_access(
            "resource-1", "user-1", "tenant-1", set(), MemoryPermission.WRITE
        )

    def test_delete_acl(self, manager):
        """Test deleting an ACL."""
        manager.create_acl(
            resource_id="resource-1",
            resource_type="session",
            owner_id="owner-1",
            tenant_id="tenant-1",
        )

        result = manager.delete_acl("resource-1")

        assert result is True
        assert manager.get_acl("resource-1") is None

    def test_delete_nonexistent_acl(self, manager):
        """Test deleting non-existent ACL returns False."""
        result = manager.delete_acl("nonexistent")

        assert result is False

    def test_default_policies_created(self, manager):
        """Test that default policies are created."""
        session_policy = manager.get_policy("session_policy")
        tenant_policy = manager.get_policy("tenant_policy")
        restricted_policy = manager.get_policy("restricted_policy")

        assert session_policy is not None
        assert tenant_policy is not None
        assert restricted_policy is not None

    def test_add_custom_policy(self, manager):
        """Test adding a custom policy."""
        policy = ScopePolicy(
            policy_id="custom_policy",
            name="Custom Policy",
            scope=MemoryScope.PROJECT,
        )

        manager.add_policy(policy)

        retrieved = manager.get_policy("custom_policy")
        assert retrieved is not None
        assert retrieved.name == "Custom Policy"

    def test_list_user_resources(self, manager):
        """Test listing resources a user can access."""
        manager.create_acl(
            resource_id="resource-1",
            resource_type="session",
            owner_id="owner-1",
            tenant_id="tenant-1",
        )
        manager.create_acl(
            resource_id="resource-2",
            resource_type="session",
            owner_id="owner-2",
            tenant_id="tenant-1",
        )
        manager.create_acl(
            resource_id="resource-3",
            resource_type="session",
            owner_id="owner-3",
            tenant_id="tenant-2",  # Different tenant
        )

        # Grant access to resource-2
        manager.grant_access(
            resource_id="resource-2",
            principal_type="user",
            principal_id="user-1",
            permissions={MemoryPermission.READ},
            granted_by="owner-2",
        )

        # List resources for owner-1 (owns resource-1)
        resources = manager.list_user_resources("owner-1", "tenant-1", set())
        assert "resource-1" in resources

        # List resources for user-1 (granted access to resource-2)
        resources = manager.list_user_resources("user-1", "tenant-1", set())
        assert "resource-2" in resources
        # Should not include resource-3 (different tenant)
        assert "resource-3" not in resources

    def test_default_permissions_by_scope(self, manager):
        """Test that default permissions are set based on scope."""
        # Public scope
        public_acl = manager.create_acl(
            resource_id="public-1",
            resource_type="global_data",
            owner_id="system",
            tenant_id="tenant-1",
            scope=MemoryScope.GLOBAL,
        )
        assert MemoryPermission.READ in public_acl.default_permissions
        assert MemoryPermission.REFERENCE in public_acl.default_permissions

        # Private scope
        private_acl = manager.create_acl(
            resource_id="private-1",
            resource_type="session",
            owner_id="owner-1",
            tenant_id="tenant-1",
            scope=MemoryScope.PRIVATE,
        )
        assert len(private_acl.default_permissions) == 0

    def test_access_check_for_nonexistent_resource(self, manager):
        """Test access check for non-existent resource returns False."""
        result = manager.check_access(
            resource_id="nonexistent",
            user_id="user-1",
            tenant_id="tenant-1",
            roles=set(),
            permission=MemoryPermission.READ,
        )

        assert result is False
