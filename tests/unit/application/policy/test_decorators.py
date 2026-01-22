"""Unit tests for policy decorators."""

import pytest
from unittest.mock import patch

from taskforce.application.policy.decorators import (
    require_permission,
    require_role,
    policy_check,
    check_and_raise,
    PolicyViolationError,
    PolicyContext,
)
from taskforce.application.policy.engine import PolicyEngine, PolicyConfig, set_policy_engine
from taskforce.core.interfaces.identity import (
    UserContext,
    Permission,
    ResourceType,
    get_permissions_for_roles,
)
from taskforce.core.domain.identity import set_current_user


class TestRequirePermissionDecorator:
    """Tests for require_permission decorator."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up a policy engine for tests."""
        engine = PolicyEngine(PolicyConfig())
        set_policy_engine(engine)

    @pytest.fixture
    def operator_user(self):
        """Create an operator user."""
        return UserContext(
            user_id="operator-1",
            tenant_id="tenant-1",
            username="operator",
            roles={"operator"},
            permissions=get_permissions_for_roles({"operator"}),
        )

    @pytest.fixture
    def viewer_user(self):
        """Create a viewer user."""
        return UserContext(
            user_id="viewer-1",
            tenant_id="tenant-1",
            username="viewer",
            roles={"viewer"},
            permissions=get_permissions_for_roles({"viewer"}),
        )

    @pytest.mark.asyncio
    async def test_decorator_allows_with_permission(self, operator_user):
        """Test that decorator allows when user has permission."""
        set_current_user(operator_user)
        try:
            @require_permission(Permission.AGENT_EXECUTE)
            async def execute_agent():
                return "executed"

            result = await execute_agent()
            assert result == "executed"
        finally:
            set_current_user(None)

    @pytest.mark.asyncio
    async def test_decorator_denies_without_permission(self, viewer_user):
        """Test that decorator denies when user lacks permission."""
        set_current_user(viewer_user)
        try:
            @require_permission(Permission.AGENT_CREATE)
            async def create_agent():
                return "created"

            with pytest.raises(PolicyViolationError) as exc_info:
                await create_agent()

            assert "Permission denied" in str(exc_info.value)
            assert exc_info.value.action == Permission.AGENT_CREATE
        finally:
            set_current_user(None)

    @pytest.mark.asyncio
    async def test_decorator_without_user_raises(self):
        """Test that decorator raises when no user is set."""
        set_current_user(None)

        @require_permission(Permission.AGENT_READ)
        async def read_agent():
            return "read"

        with pytest.raises(RuntimeError, match="No user context"):
            await read_agent()


class TestRequireRoleDecorator:
    """Tests for require_role decorator."""

    @pytest.fixture
    def admin_user(self):
        """Create an admin user."""
        return UserContext(
            user_id="admin-1",
            tenant_id="tenant-1",
            username="admin",
            roles={"admin"},
            permissions=get_permissions_for_roles({"admin"}),
        )

    @pytest.fixture
    def viewer_user(self):
        """Create a viewer user."""
        return UserContext(
            user_id="viewer-1",
            tenant_id="tenant-1",
            username="viewer",
            roles={"viewer"},
            permissions=get_permissions_for_roles({"viewer"}),
        )

    @pytest.mark.asyncio
    async def test_decorator_allows_with_role(self, admin_user):
        """Test that decorator allows when user has role."""
        set_current_user(admin_user)
        try:
            @require_role("admin")
            async def admin_action():
                return "admin"

            result = await admin_action()
            assert result == "admin"
        finally:
            set_current_user(None)

    @pytest.mark.asyncio
    async def test_decorator_denies_without_role(self, viewer_user):
        """Test that decorator denies when user lacks role."""
        set_current_user(viewer_user)
        try:
            @require_role("admin")
            async def admin_action():
                return "admin"

            with pytest.raises(PolicyViolationError) as exc_info:
                await admin_action()

            assert "Role required" in str(exc_info.value)
        finally:
            set_current_user(None)


class TestPolicyCheck:
    """Tests for policy_check function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up a policy engine for tests."""
        engine = PolicyEngine(PolicyConfig())
        set_policy_engine(engine)

    @pytest.fixture
    def operator_user(self):
        """Create an operator user."""
        return UserContext(
            user_id="operator-1",
            tenant_id="tenant-1",
            username="operator",
            roles={"operator"},
            permissions=get_permissions_for_roles({"operator"}),
        )

    @pytest.mark.asyncio
    async def test_policy_check_allowed(self, operator_user):
        """Test policy check when allowed."""
        set_current_user(operator_user)
        try:
            decision = await policy_check(Permission.AGENT_EXECUTE)
            assert decision.allowed is True
        finally:
            set_current_user(None)

    @pytest.mark.asyncio
    async def test_policy_check_denied(self, operator_user):
        """Test policy check when denied."""
        set_current_user(operator_user)
        try:
            decision = await policy_check(Permission.AGENT_CREATE)
            assert decision.allowed is False
        finally:
            set_current_user(None)

    @pytest.mark.asyncio
    async def test_policy_check_with_user_param(self, operator_user):
        """Test policy check with explicit user parameter."""
        # Don't set current user
        decision = await policy_check(
            Permission.AGENT_EXECUTE,
            user=operator_user,
        )
        assert decision.allowed is True


class TestCheckAndRaise:
    """Tests for check_and_raise function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up a policy engine for tests."""
        engine = PolicyEngine(PolicyConfig())
        set_policy_engine(engine)

    @pytest.fixture
    def viewer_user(self):
        """Create a viewer user."""
        return UserContext(
            user_id="viewer-1",
            tenant_id="tenant-1",
            username="viewer",
            roles={"viewer"},
            permissions=get_permissions_for_roles({"viewer"}),
        )

    @pytest.mark.asyncio
    async def test_check_and_raise_allowed(self, viewer_user):
        """Test that no exception is raised when allowed."""
        set_current_user(viewer_user)
        try:
            # Should not raise
            await check_and_raise(Permission.AGENT_READ)
        finally:
            set_current_user(None)

    @pytest.mark.asyncio
    async def test_check_and_raise_denied(self, viewer_user):
        """Test that exception is raised when denied."""
        set_current_user(viewer_user)
        try:
            with pytest.raises(PolicyViolationError):
                await check_and_raise(Permission.AGENT_DELETE)
        finally:
            set_current_user(None)


class TestPolicyContext:
    """Tests for PolicyContext context manager."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up a policy engine for tests."""
        engine = PolicyEngine(PolicyConfig())
        set_policy_engine(engine)

    @pytest.fixture
    def operator_user(self):
        """Create an operator user."""
        return UserContext(
            user_id="operator-1",
            tenant_id="tenant-1",
            username="operator",
            roles={"operator"},
            permissions=get_permissions_for_roles({"operator"}),
        )

    @pytest.mark.asyncio
    async def test_context_allowed(self, operator_user):
        """Test context manager when allowed."""
        set_current_user(operator_user)
        try:
            async with PolicyContext(Permission.AGENT_EXECUTE) as ctx:
                assert ctx.allowed is True
                assert ctx.decision is not None
        finally:
            set_current_user(None)

    @pytest.mark.asyncio
    async def test_context_denied(self, operator_user):
        """Test context manager when denied."""
        set_current_user(operator_user)
        try:
            async with PolicyContext(Permission.AGENT_CREATE) as ctx:
                assert ctx.allowed is False
        finally:
            set_current_user(None)

    @pytest.mark.asyncio
    async def test_context_raise_on_deny(self, operator_user):
        """Test context manager with raise_on_deny=True."""
        set_current_user(operator_user)
        try:
            with pytest.raises(PolicyViolationError):
                async with PolicyContext(
                    Permission.AGENT_CREATE,
                    raise_on_deny=True,
                ):
                    pass  # Should not reach here
        finally:
            set_current_user(None)


class TestPolicyViolationError:
    """Tests for PolicyViolationError exception."""

    def test_error_attributes(self):
        """Test that error has correct attributes."""
        from taskforce.core.interfaces.identity import PolicyDecision

        decision = PolicyDecision(
            allowed=False,
            reason="Test reason",
        )

        error = PolicyViolationError(
            "Permission denied",
            decision=decision,
            user_id="user-1",
            action=Permission.AGENT_CREATE,
        )

        assert error.decision == decision
        assert error.user_id == "user-1"
        assert error.action == Permission.AGENT_CREATE
        assert "Permission denied" in str(error)
