"""Policy enforcement decorators for application layer functions.

This module provides decorators and context managers for enforcing
RBAC policies on application-level operations.
"""

from functools import wraps
from typing import Callable, TypeVar, ParamSpec, Set, Optional, Any, Awaitable
import structlog

from taskforce.core.interfaces.identity import (
    Permission,
    ResourceType,
    UserContext,
    PolicyDecision,
)
from taskforce.core.domain.identity import get_current_user, require_user
from taskforce.application.policy.engine import get_policy_engine


logger = structlog.get_logger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


class PolicyViolationError(Exception):
    """Exception raised when a policy check fails."""

    def __init__(
        self,
        message: str,
        decision: Optional[PolicyDecision] = None,
        user_id: Optional[str] = None,
        action: Optional[Permission] = None,
    ):
        super().__init__(message)
        self.decision = decision
        self.user_id = user_id
        self.action = action


def require_permission(
    permission: Permission,
    resource_type: ResourceType = ResourceType.AGENT,
    resource_id_param: Optional[str] = None,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator to require a specific permission for a function.

    Usage:
        @require_permission(Permission.AGENT_EXECUTE)
        async def execute_agent(agent_id: str, mission: str):
            ...

    Args:
        permission: The required permission
        resource_type: The type of resource being accessed
        resource_id_param: Name of the parameter containing resource ID

    Returns:
        Decorated function
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            user = require_user()

            # Extract resource ID from kwargs if specified
            resource_id = None
            if resource_id_param and resource_id_param in kwargs:
                resource_id = kwargs[resource_id_param]

            engine = get_policy_engine()
            decision = await engine.evaluate(
                user=user,
                action=permission,
                resource_type=resource_type,
                resource_id=resource_id,
            )

            if not decision.allowed:
                logger.warning(
                    "policy.violation",
                    user_id=user.user_id,
                    permission=permission.value,
                    resource_type=resource_type.value,
                    resource_id=resource_id,
                    reason=decision.reason,
                )
                raise PolicyViolationError(
                    f"Permission denied: {permission.value}",
                    decision=decision,
                    user_id=user.user_id,
                    action=permission,
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def require_any_permission(
    permissions: Set[Permission],
    resource_type: ResourceType = ResourceType.AGENT,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator to require any of the specified permissions.

    Args:
        permissions: Set of acceptable permissions
        resource_type: The type of resource being accessed

    Returns:
        Decorated function
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            user = require_user()
            engine = get_policy_engine()

            # Check if any permission is allowed
            for permission in permissions:
                decision = await engine.evaluate(
                    user=user,
                    action=permission,
                    resource_type=resource_type,
                )
                if decision.allowed:
                    return await func(*args, **kwargs)

            # None of the permissions were allowed
            perm_names = [p.value for p in permissions]
            logger.warning(
                "policy.violation",
                user_id=user.user_id,
                required_any=perm_names,
                resource_type=resource_type.value,
            )
            raise PolicyViolationError(
                f"Permission denied: one of {perm_names} required",
                user_id=user.user_id,
            )

        return wrapper

    return decorator


def require_role(role: str) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator to require a specific role.

    Args:
        role: The required role name

    Returns:
        Decorated function
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            user = require_user()

            if not user.has_role(role):
                logger.warning(
                    "policy.role.violation",
                    user_id=user.user_id,
                    required_role=role,
                    user_roles=list(user.roles),
                )
                raise PolicyViolationError(
                    f"Role required: {role}",
                    user_id=user.user_id,
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


async def policy_check(
    permission: Permission,
    resource_type: ResourceType = ResourceType.AGENT,
    resource_id: Optional[str] = None,
    user: Optional[UserContext] = None,
) -> PolicyDecision:
    """Perform a policy check programmatically.

    This function can be used when decorators aren't suitable,
    for example when the check needs to be conditional.

    Usage:
        decision = await policy_check(
            permission=Permission.AGENT_DELETE,
            resource_type=ResourceType.AGENT,
            resource_id=agent_id,
        )
        if decision.allowed:
            # Proceed with deletion
            ...
        else:
            # Handle denial
            ...

    Args:
        permission: The permission to check
        resource_type: The type of resource being accessed
        resource_id: Optional specific resource identifier
        user: Optional user context (uses current user if not provided)

    Returns:
        PolicyDecision indicating whether the action is allowed
    """
    if user is None:
        user = require_user()

    engine = get_policy_engine()
    return await engine.evaluate(
        user=user,
        action=permission,
        resource_type=resource_type,
        resource_id=resource_id,
    )


async def check_and_raise(
    permission: Permission,
    resource_type: ResourceType = ResourceType.AGENT,
    resource_id: Optional[str] = None,
    user: Optional[UserContext] = None,
) -> None:
    """Check a permission and raise PolicyViolationError if denied.

    Args:
        permission: The permission to check
        resource_type: The type of resource being accessed
        resource_id: Optional specific resource identifier
        user: Optional user context (uses current user if not provided)

    Raises:
        PolicyViolationError: If the permission is denied
    """
    decision = await policy_check(
        permission=permission,
        resource_type=resource_type,
        resource_id=resource_id,
        user=user,
    )

    if not decision.allowed:
        actual_user = user or get_current_user()
        raise PolicyViolationError(
            f"Permission denied: {permission.value}",
            decision=decision,
            user_id=actual_user.user_id if actual_user else "unknown",
            action=permission,
        )


class PolicyContext:
    """Context manager for policy enforcement.

    Usage:
        async with PolicyContext(Permission.AGENT_EXECUTE, agent_id=agent_id) as ctx:
            if ctx.allowed:
                # Execute agent
                ...
            else:
                # Handle denial
                ...
    """

    def __init__(
        self,
        permission: Permission,
        resource_type: ResourceType = ResourceType.AGENT,
        resource_id: Optional[str] = None,
        user: Optional[UserContext] = None,
        raise_on_deny: bool = False,
    ):
        """Initialize the policy context.

        Args:
            permission: The permission to check
            resource_type: The type of resource being accessed
            resource_id: Optional specific resource identifier
            user: Optional user context
            raise_on_deny: Whether to raise an exception if denied
        """
        self.permission = permission
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.user = user
        self.raise_on_deny = raise_on_deny
        self.decision: Optional[PolicyDecision] = None

    @property
    def allowed(self) -> bool:
        """Whether the permission was allowed."""
        return self.decision is not None and self.decision.allowed

    async def __aenter__(self) -> "PolicyContext":
        """Perform the policy check on context entry."""
        self.decision = await policy_check(
            permission=self.permission,
            resource_type=self.resource_type,
            resource_id=self.resource_id,
            user=self.user,
        )

        if self.raise_on_deny and not self.decision.allowed:
            actual_user = self.user or get_current_user()
            raise PolicyViolationError(
                f"Permission denied: {self.permission.value}",
                decision=self.decision,
                user_id=actual_user.user_id if actual_user else "unknown",
                action=self.permission,
            )

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Clean up on context exit."""
        pass
