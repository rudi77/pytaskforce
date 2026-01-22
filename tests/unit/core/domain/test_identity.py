"""Unit tests for identity domain models."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from taskforce.core.interfaces.identity import (
    TenantContext,
    UserContext,
    Permission,
    Role,
    PolicyDecision,
    SYSTEM_ROLES,
    get_permissions_for_roles,
)
from taskforce.core.domain.identity import (
    get_current_tenant,
    set_current_tenant,
    get_current_user,
    set_current_user,
    require_tenant,
    require_user,
    IdentityToken,
    AuthenticationResult,
    TenantScoped,
    SessionIdentity,
    AuditEvent,
    create_tenant_session_id,
    parse_tenant_session_id,
    create_anonymous_user,
    create_system_user,
    create_default_tenant,
)


class TestTenantContext:
    """Tests for TenantContext dataclass."""

    def test_create_tenant_context(self):
        """Test basic tenant context creation."""
        tenant = TenantContext(
            tenant_id="tenant-123",
            name="Test Tenant",
        )
        assert tenant.tenant_id == "tenant-123"
        assert tenant.name == "Test Tenant"
        assert tenant.settings == {}
        assert tenant.metadata == {}

    def test_tenant_context_with_settings(self):
        """Test tenant context with custom settings."""
        settings = {"max_agents": 10, "features": ["rag", "mcp"]}
        tenant = TenantContext(
            tenant_id="tenant-123",
            name="Test Tenant",
            settings=settings,
        )
        assert tenant.get_setting("max_agents") == 10
        assert tenant.get_setting("features") == ["rag", "mcp"]
        assert tenant.get_setting("nonexistent") is None
        assert tenant.get_setting("nonexistent", "default") == "default"

    def test_tenant_has_feature(self):
        """Test feature checking."""
        tenant = TenantContext(
            tenant_id="tenant-123",
            name="Test Tenant",
            settings={"features": ["rag", "mcp", "memory"]},
        )
        assert tenant.has_feature("rag") is True
        assert tenant.has_feature("mcp") is True
        assert tenant.has_feature("nonexistent") is False

    def test_tenant_context_is_immutable(self):
        """Test that TenantContext is frozen."""
        tenant = TenantContext(
            tenant_id="tenant-123",
            name="Test Tenant",
        )
        with pytest.raises(AttributeError):
            tenant.name = "New Name"


class TestUserContext:
    """Tests for UserContext dataclass."""

    def test_create_user_context(self):
        """Test basic user context creation."""
        user = UserContext(
            user_id="user-123",
            tenant_id="tenant-456",
            username="testuser",
        )
        assert user.user_id == "user-123"
        assert user.tenant_id == "tenant-456"
        assert user.username == "testuser"
        assert user.roles == set()
        assert user.permissions == set()

    def test_user_has_permission(self):
        """Test permission checking."""
        user = UserContext(
            user_id="user-123",
            tenant_id="tenant-456",
            username="testuser",
            permissions={Permission.AGENT_READ, Permission.AGENT_EXECUTE},
        )
        assert user.has_permission(Permission.AGENT_READ) is True
        assert user.has_permission(Permission.AGENT_EXECUTE) is True
        assert user.has_permission(Permission.AGENT_CREATE) is False

    def test_user_has_any_permission(self):
        """Test checking for any permission."""
        user = UserContext(
            user_id="user-123",
            tenant_id="tenant-456",
            username="testuser",
            permissions={Permission.AGENT_READ},
        )
        assert user.has_any_permission({Permission.AGENT_READ, Permission.AGENT_CREATE}) is True
        assert user.has_any_permission({Permission.AGENT_DELETE, Permission.AGENT_CREATE}) is False

    def test_user_has_all_permissions(self):
        """Test checking for all permissions."""
        user = UserContext(
            user_id="user-123",
            tenant_id="tenant-456",
            username="testuser",
            permissions={Permission.AGENT_READ, Permission.AGENT_EXECUTE, Permission.SESSION_READ},
        )
        assert user.has_all_permissions({Permission.AGENT_READ, Permission.AGENT_EXECUTE}) is True
        assert user.has_all_permissions({Permission.AGENT_READ, Permission.AGENT_CREATE}) is False

    def test_user_has_role(self):
        """Test role checking."""
        user = UserContext(
            user_id="user-123",
            tenant_id="tenant-456",
            username="testuser",
            roles={"admin", "operator"},
        )
        assert user.has_role("admin") is True
        assert user.has_role("operator") is True
        assert user.has_role("auditor") is False

    def test_user_is_admin(self):
        """Test admin checking."""
        admin_by_role = UserContext(
            user_id="user-123",
            tenant_id="tenant-456",
            username="admin",
            roles={"admin"},
        )
        assert admin_by_role.is_admin() is True

        admin_by_permission = UserContext(
            user_id="user-456",
            tenant_id="tenant-456",
            username="superuser",
            permissions={Permission.TENANT_MANAGE},
        )
        assert admin_by_permission.is_admin() is True

        regular_user = UserContext(
            user_id="user-789",
            tenant_id="tenant-456",
            username="regular",
            roles={"operator"},
        )
        assert regular_user.is_admin() is False


class TestRole:
    """Tests for Role dataclass."""

    def test_create_role(self):
        """Test role creation."""
        role = Role(
            role_id="custom-role",
            name="Custom Role",
            description="A custom role",
            permissions={Permission.AGENT_READ, Permission.AGENT_EXECUTE},
        )
        assert role.role_id == "custom-role"
        assert role.name == "Custom Role"
        assert Permission.AGENT_READ in role.permissions
        assert role.is_system_role is False

    def test_system_roles_exist(self):
        """Test that system roles are defined."""
        assert "admin" in SYSTEM_ROLES
        assert "agent_designer" in SYSTEM_ROLES
        assert "operator" in SYSTEM_ROLES
        assert "auditor" in SYSTEM_ROLES
        assert "viewer" in SYSTEM_ROLES

    def test_admin_role_has_comprehensive_permissions(self):
        """Test admin role has expected permissions."""
        admin = SYSTEM_ROLES["admin"]
        assert Permission.AGENT_CREATE in admin.permissions
        assert Permission.AGENT_DELETE in admin.permissions
        assert Permission.USER_MANAGE in admin.permissions
        assert admin.is_system_role is True


class TestPermissionHelpers:
    """Tests for permission helper functions."""

    def test_get_permissions_for_roles(self):
        """Test getting combined permissions for roles."""
        permissions = get_permissions_for_roles({"viewer"})
        assert Permission.AGENT_READ in permissions
        assert Permission.AGENT_CREATE not in permissions

    def test_get_permissions_for_multiple_roles(self):
        """Test combining permissions from multiple roles."""
        permissions = get_permissions_for_roles({"viewer", "operator"})
        # Should have viewer permissions
        assert Permission.AGENT_READ in permissions
        # Should also have operator permissions
        assert Permission.AGENT_EXECUTE in permissions
        assert Permission.SESSION_CREATE in permissions


class TestContextVariables:
    """Tests for context variable functions."""

    def test_set_and_get_tenant(self):
        """Test setting and getting tenant context."""
        tenant = TenantContext(tenant_id="test", name="Test")
        set_current_tenant(tenant)
        assert get_current_tenant() == tenant
        set_current_tenant(None)  # Cleanup
        assert get_current_tenant() is None

    def test_set_and_get_user(self):
        """Test setting and getting user context."""
        user = UserContext(user_id="user-1", tenant_id="tenant-1", username="test")
        set_current_user(user)
        assert get_current_user() == user
        set_current_user(None)  # Cleanup
        assert get_current_user() is None

    def test_require_tenant_raises_when_not_set(self):
        """Test require_tenant raises when no tenant."""
        set_current_tenant(None)
        with pytest.raises(RuntimeError, match="No tenant context"):
            require_tenant()

    def test_require_user_raises_when_not_set(self):
        """Test require_user raises when no user."""
        set_current_user(None)
        with pytest.raises(RuntimeError, match="No user context"):
            require_user()


class TestIdentityToken:
    """Tests for IdentityToken dataclass."""

    def test_create_token(self):
        """Test token creation."""
        now = datetime.now(timezone.utc)
        token = IdentityToken(
            token_id="token-123",
            token_type="jwt",
            subject="user-456",
            tenant_id="tenant-789",
            issued_at=now,
            expires_at=now + timedelta(hours=1),
        )
        assert token.token_id == "token-123"
        assert token.is_expired() is False

    def test_token_expiration(self):
        """Test token expiration checking."""
        now = datetime.now(timezone.utc)
        expired_token = IdentityToken(
            token_id="token-123",
            token_type="jwt",
            subject="user-456",
            tenant_id="tenant-789",
            issued_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
        )
        assert expired_token.is_expired() is True


class TestAuthenticationResult:
    """Tests for AuthenticationResult dataclass."""

    def test_successful_auth(self):
        """Test successful authentication result."""
        user = UserContext(user_id="user-1", tenant_id="tenant-1", username="test")
        tenant = TenantContext(tenant_id="tenant-1", name="Test")
        result = AuthenticationResult.authenticated(user, tenant)
        assert result.success is True
        assert result.user == user
        assert result.tenant == tenant

    def test_failed_auth(self):
        """Test failed authentication result."""
        result = AuthenticationResult.failed("Invalid token", "INVALID_TOKEN")
        assert result.success is False
        assert result.error == "Invalid token"
        assert result.error_code == "INVALID_TOKEN"


class TestTenantScoped:
    """Tests for TenantScoped wrapper."""

    def test_create_scoped_data(self):
        """Test creating tenant-scoped data."""
        scoped = TenantScoped(
            tenant_id="tenant-123",
            data={"key": "value"},
        )
        assert scoped.tenant_id == "tenant-123"
        assert scoped.data == {"key": "value"}

    def test_validate_access(self):
        """Test access validation."""
        scoped = TenantScoped(tenant_id="tenant-123", data="secret")

        matching_user = UserContext(
            user_id="user-1",
            tenant_id="tenant-123",
            username="test",
        )
        assert scoped.validate_access(matching_user) is True

        other_user = UserContext(
            user_id="user-2",
            tenant_id="tenant-999",
            username="other",
        )
        assert scoped.validate_access(other_user) is False


class TestSessionIdentity:
    """Tests for SessionIdentity dataclass."""

    def test_create_session_identity(self):
        """Test creating session identity."""
        session = SessionIdentity(
            session_id="session-123",
            tenant_id="tenant-456",
            user_id="user-789",
        )
        assert session.session_id == "session-123"
        assert session.tenant_id == "tenant-456"
        assert session.user_id == "user-789"

    def test_session_touch(self):
        """Test updating last accessed time."""
        session = SessionIdentity(
            session_id="session-123",
            tenant_id="tenant-456",
            user_id="user-789",
        )
        original_time = session.last_accessed_at
        session.touch()
        assert session.last_accessed_at >= original_time

    def test_session_serialization(self):
        """Test session to/from dict."""
        session = SessionIdentity(
            session_id="session-123",
            tenant_id="tenant-456",
            user_id="user-789",
            metadata={"key": "value"},
        )
        data = session.to_dict()
        restored = SessionIdentity.from_dict(data)
        assert restored.session_id == session.session_id
        assert restored.tenant_id == session.tenant_id
        assert restored.metadata == session.metadata


class TestSessionIdHelpers:
    """Tests for session ID helper functions."""

    def test_create_tenant_session_id(self):
        """Test creating namespaced session ID."""
        session_id = create_tenant_session_id("tenant-123", "session-456")
        assert session_id == "tenant-123:session-456"

    def test_create_tenant_session_id_generates_uuid(self):
        """Test that UUID is generated when not provided."""
        session_id = create_tenant_session_id("tenant-123")
        assert session_id.startswith("tenant-123:")
        assert len(session_id.split(":")[1]) == 36  # UUID length

    def test_parse_tenant_session_id(self):
        """Test parsing namespaced session ID."""
        tenant_id, session_id = parse_tenant_session_id("tenant-123:session-456")
        assert tenant_id == "tenant-123"
        assert session_id == "session-456"

    def test_parse_invalid_session_id(self):
        """Test parsing invalid session ID raises error."""
        with pytest.raises(ValueError, match="Invalid namespaced session ID"):
            parse_tenant_session_id("invalid-format")


class TestFactoryFunctions:
    """Tests for identity factory functions."""

    def test_create_anonymous_user(self):
        """Test creating anonymous user."""
        user = create_anonymous_user()
        assert user.user_id == "anonymous"
        assert user.tenant_id == "default"
        assert "viewer" in user.roles
        assert user.metadata.get("anonymous") is True

    def test_create_system_user(self):
        """Test creating system user."""
        user = create_system_user()
        assert user.user_id == "system"
        assert "admin" in user.roles
        assert user.metadata.get("system") is True

    def test_create_default_tenant(self):
        """Test creating default tenant."""
        tenant = create_default_tenant()
        assert tenant.tenant_id == "default"
        assert tenant.name == "Default Tenant"
        assert tenant.metadata.get("default") is True


class TestAuditEvent:
    """Tests for AuditEvent dataclass."""

    def test_create_audit_event(self):
        """Test creating audit event."""
        event = AuditEvent(
            event_id="event-123",
            event_type="auth",
            action="login",
            tenant_id="tenant-456",
            user_id="user-789",
        )
        assert event.event_id == "event-123"
        assert event.event_type == "auth"
        assert event.success is True

    def test_audit_event_to_dict(self):
        """Test audit event serialization."""
        event = AuditEvent(
            event_id="event-123",
            event_type="auth",
            action="login",
            tenant_id="tenant-456",
            user_id="user-789",
            details={"method": "jwt"},
        )
        data = event.to_dict()
        assert data["event_id"] == "event-123"
        assert data["details"]["method"] == "jwt"
        assert "timestamp" in data

    def test_audit_event_create_from_context(self):
        """Test creating audit event from context."""
        user = UserContext(
            user_id="user-123",
            tenant_id="tenant-456",
            username="test",
        )
        set_current_user(user)
        try:
            event = AuditEvent.create(
                event_type="access",
                action="agent_execute",
                resource_type="agent",
                resource_id="agent-789",
            )
            assert event.user_id == "user-123"
            assert event.tenant_id == "tenant-456"
            assert event.resource_type == "agent"
        finally:
            set_current_user(None)
