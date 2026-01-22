"""Unit tests for RBAC Policy Engine."""

import pytest
from unittest.mock import AsyncMock

from taskforce.application.policy.engine import (
    PolicyEngine,
    PolicyConfig,
    PolicyRule,
    PolicyEffect,
    get_policy_engine,
    set_policy_engine,
)
from taskforce.core.interfaces.identity import (
    UserContext,
    Permission,
    ResourceType,
    get_permissions_for_roles,
)


class TestPolicyRule:
    """Tests for PolicyRule dataclass."""

    def test_create_rule(self):
        """Test creating a policy rule."""
        rule = PolicyRule(
            rule_id="test-rule",
            name="Test Rule",
            description="A test rule",
            effect=PolicyEffect.ALLOW,
        )
        assert rule.rule_id == "test-rule"
        assert rule.effect == PolicyEffect.ALLOW

    def test_matches_action_wildcard(self):
        """Test action matching with wildcard."""
        rule = PolicyRule(
            rule_id="r1",
            name="All Actions",
            description="",
            effect=PolicyEffect.ALLOW,
            actions={"*"},
        )
        assert rule.matches_action(Permission.AGENT_READ) is True
        assert rule.matches_action(Permission.AGENT_DELETE) is True

    def test_matches_action_specific(self):
        """Test action matching with specific actions."""
        rule = PolicyRule(
            rule_id="r1",
            name="Read Only",
            description="",
            effect=PolicyEffect.ALLOW,
            actions={"agent:read", "session:read"},
        )
        assert rule.matches_action(Permission.AGENT_READ) is True
        assert rule.matches_action(Permission.SESSION_READ) is True
        assert rule.matches_action(Permission.AGENT_DELETE) is False

    def test_matches_resource_wildcard(self):
        """Test resource matching with wildcard."""
        rule = PolicyRule(
            rule_id="r1",
            name="All Resources",
            description="",
            effect=PolicyEffect.ALLOW,
            resources={"*"},
        )
        assert rule.matches_resource(ResourceType.AGENT) is True
        assert rule.matches_resource(ResourceType.SESSION) is True

    def test_matches_resource_specific(self):
        """Test resource matching with specific types."""
        rule = PolicyRule(
            rule_id="r1",
            name="Agents Only",
            description="",
            effect=PolicyEffect.ALLOW,
            resources={"agent"},
        )
        assert rule.matches_resource(ResourceType.AGENT) is True
        assert rule.matches_resource(ResourceType.SESSION) is False

    def test_matches_roles(self):
        """Test role matching."""
        rule = PolicyRule(
            rule_id="r1",
            name="Admin Rule",
            description="",
            effect=PolicyEffect.ALLOW,
            roles={"admin", "operator"},
        )
        assert rule.matches_roles({"admin"}) is True
        assert rule.matches_roles({"operator"}) is True
        assert rule.matches_roles({"viewer"}) is False
        assert rule.matches_roles({"admin", "viewer"}) is True

    def test_matches_roles_none(self):
        """Test that None roles matches all."""
        rule = PolicyRule(
            rule_id="r1",
            name="All Roles",
            description="",
            effect=PolicyEffect.ALLOW,
            roles=None,
        )
        assert rule.matches_roles({"admin"}) is True
        assert rule.matches_roles({"viewer"}) is True


class TestPolicyEngine:
    """Tests for PolicyEngine."""

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

    @pytest.fixture
    def engine(self):
        """Create a policy engine with default config."""
        return PolicyEngine(PolicyConfig())

    @pytest.mark.asyncio
    async def test_admin_has_all_permissions(self, engine, admin_user):
        """Test that admin users have comprehensive permissions."""
        # Admin should be able to create agents
        decision = await engine.evaluate(
            user=admin_user,
            action=Permission.AGENT_CREATE,
            resource_type=ResourceType.AGENT,
        )
        assert decision.allowed is True

        # Admin should be able to manage users
        decision = await engine.evaluate(
            user=admin_user,
            action=Permission.USER_MANAGE,
            resource_type=ResourceType.USER,
        )
        assert decision.allowed is True

    @pytest.mark.asyncio
    async def test_operator_has_execute_permissions(self, engine, operator_user):
        """Test that operators can execute agents."""
        decision = await engine.evaluate(
            user=operator_user,
            action=Permission.AGENT_EXECUTE,
            resource_type=ResourceType.AGENT,
        )
        assert decision.allowed is True

    @pytest.mark.asyncio
    async def test_operator_cannot_create_agents(self, engine, operator_user):
        """Test that operators cannot create agents."""
        decision = await engine.evaluate(
            user=operator_user,
            action=Permission.AGENT_CREATE,
            resource_type=ResourceType.AGENT,
        )
        assert decision.allowed is False

    @pytest.mark.asyncio
    async def test_viewer_can_only_read(self, engine, viewer_user):
        """Test that viewers have read-only access."""
        # Should be able to read
        decision = await engine.evaluate(
            user=viewer_user,
            action=Permission.AGENT_READ,
            resource_type=ResourceType.AGENT,
        )
        assert decision.allowed is True

        # Should not be able to write
        decision = await engine.evaluate(
            user=viewer_user,
            action=Permission.AGENT_CREATE,
            resource_type=ResourceType.AGENT,
        )
        assert decision.allowed is False

    @pytest.mark.asyncio
    async def test_policy_disabled_allows_all(self, viewer_user):
        """Test that disabled policy allows all actions."""
        config = PolicyConfig(enabled=False)
        engine = PolicyEngine(config)

        decision = await engine.evaluate(
            user=viewer_user,
            action=Permission.AGENT_DELETE,
            resource_type=ResourceType.AGENT,
        )
        assert decision.allowed is True
        assert decision.matched_policy == "disabled"

    @pytest.mark.asyncio
    async def test_custom_deny_rule(self, admin_user):
        """Test that custom deny rules override permissions."""
        # Create a rule that denies deleting a specific agent
        deny_rule = PolicyRule(
            rule_id="deny-protected-agent",
            name="Deny Protected Agent Deletion",
            description="Cannot delete the protected agent",
            effect=PolicyEffect.DENY,
            actions={"agent:delete"},
            resources={"agent"},
            resource_ids={"protected-agent-id"},
        )

        config = PolicyConfig(custom_rules=[deny_rule])
        engine = PolicyEngine(config)

        # Admin should normally be able to delete
        decision = await engine.evaluate(
            user=admin_user,
            action=Permission.AGENT_DELETE,
            resource_type=ResourceType.AGENT,
            resource_id="normal-agent-id",
        )
        assert decision.allowed is True

        # But not the protected agent
        decision = await engine.evaluate(
            user=admin_user,
            action=Permission.AGENT_DELETE,
            resource_type=ResourceType.AGENT,
            resource_id="protected-agent-id",
        )
        assert decision.allowed is False
        assert "deny-protected-agent" in decision.matched_policy

    @pytest.mark.asyncio
    async def test_custom_allow_rule(self):
        """Test that custom allow rules grant permissions."""
        # Create a user with no permissions
        user = UserContext(
            user_id="limited-1",
            tenant_id="tenant-1",
            username="limited",
            roles={"custom_role"},
            permissions=set(),  # No permissions
        )

        # Create a rule that allows custom_role to read specific agents
        allow_rule = PolicyRule(
            rule_id="allow-custom-read",
            name="Allow Custom Role Read",
            description="Custom role can read specific agents",
            effect=PolicyEffect.ALLOW,
            actions={"agent:read"},
            resources={"agent"},
            roles={"custom_role"},
        )

        config = PolicyConfig(custom_rules=[allow_rule])
        engine = PolicyEngine(config)

        decision = await engine.evaluate(
            user=user,
            action=Permission.AGENT_READ,
            resource_type=ResourceType.AGENT,
        )
        assert decision.allowed is True

    @pytest.mark.asyncio
    async def test_rule_priority(self, admin_user):
        """Test that higher priority rules are evaluated first."""
        # Lower priority allow rule
        allow_rule = PolicyRule(
            rule_id="allow",
            name="Allow",
            description="",
            effect=PolicyEffect.ALLOW,
            priority=0,
        )

        # Higher priority deny rule
        deny_rule = PolicyRule(
            rule_id="deny",
            name="Deny",
            description="",
            effect=PolicyEffect.DENY,
            priority=10,
        )

        config = PolicyConfig(custom_rules=[allow_rule, deny_rule])
        engine = PolicyEngine(config)

        # The deny rule should win due to higher priority
        decision = await engine.evaluate(
            user=admin_user,
            action=Permission.AGENT_DELETE,
            resource_type=ResourceType.AGENT,
        )
        assert decision.allowed is False

    @pytest.mark.asyncio
    async def test_get_user_permissions(self, engine, operator_user):
        """Test getting all permissions for a user."""
        permissions = await engine.get_user_permissions(operator_user)

        assert Permission.AGENT_EXECUTE in permissions
        assert Permission.AGENT_READ in permissions
        assert Permission.AGENT_CREATE not in permissions

    @pytest.mark.asyncio
    async def test_audit_callback(self, operator_user):
        """Test that audit callback is called."""
        callback = AsyncMock()
        engine = PolicyEngine(
            PolicyConfig(audit_enabled=True),
            audit_callback=callback,
        )

        await engine.evaluate(
            user=operator_user,
            action=Permission.AGENT_EXECUTE,
            resource_type=ResourceType.AGENT,
        )

        callback.assert_called_once()

    def test_register_and_remove_rule(self, engine):
        """Test registering and removing rules."""
        rule = PolicyRule(
            rule_id="dynamic-rule",
            name="Dynamic Rule",
            description="",
            effect=PolicyEffect.ALLOW,
        )

        engine.register_rule(rule)
        assert any(r.rule_id == "dynamic-rule" for r in engine._rules)

        removed = engine.remove_rule("dynamic-rule")
        assert removed is True
        assert not any(r.rule_id == "dynamic-rule" for r in engine._rules)

        # Removing again should return False
        removed = engine.remove_rule("dynamic-rule")
        assert removed is False


class TestPolicySingleton:
    """Tests for policy engine singleton functions."""

    def test_get_and_set_engine(self):
        """Test getting and setting the default engine."""
        original = get_policy_engine()

        custom_engine = PolicyEngine(PolicyConfig(enabled=False))
        set_policy_engine(custom_engine)

        assert get_policy_engine() is custom_engine

        # Restore original
        set_policy_engine(original)
