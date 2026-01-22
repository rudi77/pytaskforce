"""RBAC Policy Engine implementation.

This module implements the policy engine that evaluates access decisions
based on user roles, permissions, and configurable policy rules.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Set, Callable, Awaitable
from enum import Enum
import structlog
import yaml
from pathlib import Path

from taskforce.core.interfaces.identity import (
    PolicyEngineProtocol,
    PolicyDecision,
    UserContext,
    Permission,
    ResourceType,
    Role,
    SYSTEM_ROLES,
)
from taskforce.core.domain.identity import AuditEvent


logger = structlog.get_logger(__name__)


class PolicyEffect(Enum):
    """Effect of a policy rule."""

    ALLOW = "allow"
    DENY = "deny"


@dataclass
class PolicyRule:
    """A single policy rule for access control.

    Attributes:
        rule_id: Unique identifier for this rule
        name: Human-readable rule name
        description: Description of what this rule does
        effect: Whether this rule allows or denies access
        actions: Set of actions this rule applies to (or "*" for all)
        resources: Set of resource types this rule applies to (or "*" for all)
        resource_ids: Optional specific resource IDs (None = all)
        roles: Roles this rule applies to (None = all)
        conditions: Optional conditions for rule evaluation
        priority: Rule priority (higher = evaluated first)
    """

    rule_id: str
    name: str
    description: str
    effect: PolicyEffect
    actions: Set[str] = field(default_factory=lambda: {"*"})
    resources: Set[str] = field(default_factory=lambda: {"*"})
    resource_ids: Optional[Set[str]] = None
    roles: Optional[Set[str]] = None
    conditions: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0

    def matches_action(self, action: Permission) -> bool:
        """Check if this rule applies to the given action."""
        if "*" in self.actions:
            return True
        return action.value in self.actions

    def matches_resource(self, resource_type: ResourceType) -> bool:
        """Check if this rule applies to the given resource type."""
        if "*" in self.resources:
            return True
        return resource_type.value in self.resources

    def matches_resource_id(self, resource_id: Optional[str]) -> bool:
        """Check if this rule applies to the given resource ID."""
        if self.resource_ids is None:
            return True  # Applies to all resources
        if resource_id is None:
            return True  # No specific resource, rule applies
        return resource_id in self.resource_ids

    def matches_roles(self, user_roles: Set[str]) -> bool:
        """Check if this rule applies to any of the user's roles."""
        if self.roles is None:
            return True  # Applies to all roles
        return bool(user_roles & self.roles)


@dataclass
class PolicyConfig:
    """Configuration for the policy engine.

    Attributes:
        enabled: Whether policy enforcement is enabled
        default_effect: Default effect when no rules match
        audit_enabled: Whether to log policy decisions
        custom_rules: List of custom policy rules
        role_definitions: Custom role definitions
    """

    enabled: bool = True
    default_effect: PolicyEffect = PolicyEffect.DENY
    audit_enabled: bool = True
    custom_rules: List[PolicyRule] = field(default_factory=list)
    role_definitions: Dict[str, Role] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str) -> "PolicyConfig":
        """Load policy configuration from a YAML file.

        Args:
            path: Path to the YAML configuration file

        Returns:
            PolicyConfig instance
        """
        config_path = Path(path)
        if not config_path.exists():
            logger.warning("policy.config.not_found", path=path)
            return cls()

        with open(config_path, "r") as f:
            data = yaml.safe_load(f) or {}

        rbac_config = data.get("rbac", {})

        # Parse custom rules
        custom_rules = []
        for rule_data in rbac_config.get("rules", []):
            rule = PolicyRule(
                rule_id=rule_data.get("id", f"rule-{len(custom_rules)}"),
                name=rule_data.get("name", "Unnamed Rule"),
                description=rule_data.get("description", ""),
                effect=PolicyEffect(rule_data.get("effect", "deny")),
                actions=set(rule_data.get("actions", ["*"])),
                resources=set(rule_data.get("resources", ["*"])),
                resource_ids=set(rule_data["resource_ids"])
                if "resource_ids" in rule_data
                else None,
                roles=set(rule_data["roles"]) if "roles" in rule_data else None,
                conditions=rule_data.get("conditions", {}),
                priority=rule_data.get("priority", 0),
            )
            custom_rules.append(rule)

        return cls(
            enabled=rbac_config.get("enabled", True),
            default_effect=PolicyEffect(rbac_config.get("default_effect", "deny")),
            audit_enabled=rbac_config.get("audit_enabled", True),
            custom_rules=custom_rules,
        )


class PolicyEngine:
    """RBAC Policy Engine implementing PolicyEngineProtocol.

    This engine evaluates access requests against defined policies
    to determine if an action should be allowed. It supports:

    - Role-based access control with predefined system roles
    - Custom policy rules loaded from configuration
    - Priority-based rule evaluation
    - Audit logging of all policy decisions
    """

    def __init__(
        self,
        config: Optional[PolicyConfig] = None,
        audit_callback: Optional[Callable[[AuditEvent], Awaitable[None]]] = None,
    ):
        """Initialize the policy engine.

        Args:
            config: Policy configuration
            audit_callback: Optional async callback for audit events
        """
        self.config = config or PolicyConfig()
        self._audit_callback = audit_callback

        # Combine system roles with custom roles
        self._roles: Dict[str, Role] = {**SYSTEM_ROLES}
        self._roles.update(self.config.role_definitions)

        # Sort rules by priority (highest first)
        self._rules = sorted(
            self.config.custom_rules, key=lambda r: r.priority, reverse=True
        )

        logger.info(
            "policy.engine.initialized",
            enabled=self.config.enabled,
            num_rules=len(self._rules),
            num_roles=len(self._roles),
        )

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
        # If policy enforcement is disabled, allow everything
        if not self.config.enabled:
            return PolicyDecision(
                allowed=True,
                reason="Policy enforcement disabled",
                matched_policy="disabled",
            )

        # First, check if user has the permission through their roles
        if user.has_permission(action):
            decision = PolicyDecision(
                allowed=True,
                reason=f"User has permission {action.value} via roles",
                matched_policy="role_permission",
                audit_info={
                    "user_id": user.user_id,
                    "roles": list(user.roles),
                    "action": action.value,
                    "resource_type": resource_type.value,
                    "resource_id": resource_id,
                },
            )

            # Check custom rules for explicit denies
            for rule in self._rules:
                if self._rule_matches(rule, user, action, resource_type, resource_id):
                    if rule.effect == PolicyEffect.DENY:
                        decision = PolicyDecision(
                            allowed=False,
                            reason=f"Denied by rule: {rule.name}",
                            matched_policy=rule.rule_id,
                            audit_info={
                                "user_id": user.user_id,
                                "action": action.value,
                                "resource_type": resource_type.value,
                                "resource_id": resource_id,
                                "rule_id": rule.rule_id,
                            },
                        )
                        break

            await self._audit_decision(user, action, resource_type, resource_id, decision)
            return decision

        # User doesn't have permission via roles, check custom allow rules
        for rule in self._rules:
            if self._rule_matches(rule, user, action, resource_type, resource_id):
                if rule.effect == PolicyEffect.ALLOW:
                    decision = PolicyDecision(
                        allowed=True,
                        reason=f"Allowed by rule: {rule.name}",
                        matched_policy=rule.rule_id,
                        audit_info={
                            "user_id": user.user_id,
                            "action": action.value,
                            "resource_type": resource_type.value,
                            "resource_id": resource_id,
                            "rule_id": rule.rule_id,
                        },
                    )
                    await self._audit_decision(
                        user, action, resource_type, resource_id, decision
                    )
                    return decision

        # No permission and no matching allow rule - deny
        decision = PolicyDecision(
            allowed=False,
            reason=f"User lacks permission {action.value}",
            matched_policy="default_deny",
            audit_info={
                "user_id": user.user_id,
                "roles": list(user.roles),
                "action": action.value,
                "resource_type": resource_type.value,
                "resource_id": resource_id,
            },
        )

        await self._audit_decision(user, action, resource_type, resource_id, decision)
        return decision

    async def get_user_permissions(
        self,
        user: UserContext,
        resource_type: Optional[ResourceType] = None,
    ) -> Set[Permission]:
        """Get all permissions for a user.

        Args:
            user: The user to get permissions for
            resource_type: Optional filter for resource type

        Returns:
            Set of permissions the user has
        """
        # Start with permissions from roles
        permissions = set(user.permissions)

        # Add permissions from custom allow rules
        for rule in self._rules:
            if rule.effect == PolicyEffect.ALLOW and rule.matches_roles(user.roles):
                if resource_type is None or rule.matches_resource(resource_type):
                    # Add the actions as permissions if they're valid
                    for action_str in rule.actions:
                        if action_str != "*":
                            try:
                                perm = Permission(action_str)
                                permissions.add(perm)
                            except ValueError:
                                pass  # Not a valid permission enum value

        return permissions

    def register_rule(self, rule: PolicyRule) -> None:
        """Register a new policy rule.

        Args:
            rule: The policy rule to register
        """
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority, reverse=True)
        logger.info("policy.rule.registered", rule_id=rule.rule_id, name=rule.name)

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a policy rule by ID.

        Args:
            rule_id: The ID of the rule to remove

        Returns:
            True if rule was found and removed
        """
        for i, rule in enumerate(self._rules):
            if rule.rule_id == rule_id:
                self._rules.pop(i)
                logger.info("policy.rule.removed", rule_id=rule_id)
                return True
        return False

    def register_role(self, role: Role) -> None:
        """Register a custom role.

        Args:
            role: The role to register
        """
        self._roles[role.name] = role
        logger.info("policy.role.registered", role_id=role.role_id, name=role.name)

    def get_role(self, role_name: str) -> Optional[Role]:
        """Get a role by name.

        Args:
            role_name: The role name

        Returns:
            Role if found, None otherwise
        """
        return self._roles.get(role_name)

    def _rule_matches(
        self,
        rule: PolicyRule,
        user: UserContext,
        action: Permission,
        resource_type: ResourceType,
        resource_id: Optional[str],
    ) -> bool:
        """Check if a rule matches the given request.

        Args:
            rule: The rule to check
            user: The user making the request
            action: The action being requested
            resource_type: The resource type
            resource_id: The resource ID

        Returns:
            True if the rule matches
        """
        return (
            rule.matches_action(action)
            and rule.matches_resource(resource_type)
            and rule.matches_resource_id(resource_id)
            and rule.matches_roles(user.roles)
        )

    async def _audit_decision(
        self,
        user: UserContext,
        action: Permission,
        resource_type: ResourceType,
        resource_id: Optional[str],
        decision: PolicyDecision,
    ) -> None:
        """Log a policy decision for audit.

        Args:
            user: The user who made the request
            action: The action that was evaluated
            resource_type: The resource type
            resource_id: The resource ID
            decision: The policy decision
        """
        if not self.config.audit_enabled:
            return

        event = AuditEvent.create(
            event_type="policy",
            action=f"evaluate:{action.value}",
            user=user,
            resource_type=resource_type.value,
            resource_id=resource_id,
            success=decision.allowed,
            details={
                "reason": decision.reason,
                "matched_policy": decision.matched_policy,
            },
        )

        logger.info(
            "policy.decision",
            user_id=user.user_id,
            action=action.value,
            resource_type=resource_type.value,
            resource_id=resource_id,
            allowed=decision.allowed,
            reason=decision.reason,
        )

        if self._audit_callback:
            await self._audit_callback(event)


# Singleton instance for convenience
_default_engine: Optional[PolicyEngine] = None


def get_policy_engine() -> PolicyEngine:
    """Get the default policy engine instance.

    Returns:
        The default PolicyEngine instance
    """
    global _default_engine
    if _default_engine is None:
        _default_engine = PolicyEngine()
    return _default_engine


def set_policy_engine(engine: PolicyEngine) -> None:
    """Set the default policy engine instance.

    Args:
        engine: The PolicyEngine to use as default
    """
    global _default_engine
    _default_engine = engine
