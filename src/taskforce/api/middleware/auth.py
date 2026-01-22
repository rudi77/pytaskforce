"""Authentication middleware for FastAPI.

This module provides authentication middleware and dependency injection
for securing API endpoints with JWT and API key authentication.
"""

from typing import Optional, Callable, Set, Awaitable
from functools import wraps
import structlog

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from taskforce.core.interfaces.identity import (
    IdentityProviderProtocol,
    Permission,
    TenantContext,
    UserContext,
)
from taskforce.core.domain.identity import (
    set_current_user,
    set_current_tenant,
    get_current_user,
    create_anonymous_user,
    create_default_tenant,
    AuditEvent,
)


logger = structlog.get_logger(__name__)

# Security schemes
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class AuthConfig:
    """Configuration for authentication middleware.

    Attributes:
        enabled: Whether authentication is enabled
        allow_anonymous: Whether to allow anonymous access (with limited permissions)
        exempt_paths: Paths that don't require authentication
        default_tenant_id: Default tenant for anonymous users
    """

    def __init__(
        self,
        enabled: bool = True,
        allow_anonymous: bool = False,
        exempt_paths: Optional[Set[str]] = None,
        default_tenant_id: str = "default",
    ):
        self.enabled = enabled
        self.allow_anonymous = allow_anonymous
        self.exempt_paths = exempt_paths or {
            "/health",
            "/health/",
            "/docs",
            "/docs/",
            "/openapi.json",
            "/redoc",
            "/redoc/",
        }
        self.default_tenant_id = default_tenant_id


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware for handling authentication on all requests.

    This middleware:
    1. Extracts authentication credentials from headers
    2. Validates tokens/API keys
    3. Sets up user/tenant context for the request
    4. Creates audit events for authentication
    """

    def __init__(
        self,
        app,
        identity_provider: IdentityProviderProtocol,
        config: Optional[AuthConfig] = None,
    ):
        """Initialize the authentication middleware.

        Args:
            app: The FastAPI application
            identity_provider: Provider for validating credentials
            config: Authentication configuration
        """
        super().__init__(app)
        self.identity_provider = identity_provider
        self.config = config or AuthConfig()
        self._default_tenant = create_default_tenant()

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process the request and handle authentication.

        Args:
            request: The incoming request
            call_next: The next middleware/handler

        Returns:
            The response
        """
        # Check if path is exempt
        if self._is_exempt_path(request.url.path):
            return await call_next(request)

        # Check if auth is disabled
        if not self.config.enabled:
            # Set up anonymous context
            user = create_anonymous_user(self.config.default_tenant_id)
            tenant = self._default_tenant
            set_current_user(user)
            set_current_tenant(tenant)
            response = await call_next(request)
            self._cleanup_context()
            return response

        # Try to authenticate
        user = None
        tenant = None
        auth_method = None

        # Try Bearer token first
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            user = await self.identity_provider.validate_token(token)
            if user:
                auth_method = "bearer"

        # Try API key if bearer didn't work
        if user is None:
            api_key = request.headers.get("X-API-Key")
            if api_key:
                user = await self.identity_provider.validate_api_key(api_key)
                if user:
                    auth_method = "api_key"

        # Handle authentication result
        if user is not None:
            # Get tenant context
            tenant = await self.identity_provider.get_tenant(user.tenant_id)
            if tenant is None:
                # Create a basic tenant context if not found
                tenant = TenantContext(
                    tenant_id=user.tenant_id,
                    name=f"Tenant {user.tenant_id}",
                )

            # Set context for the request
            set_current_user(user)
            set_current_tenant(tenant)

            # Log successful authentication
            logger.info(
                "auth.success",
                user_id=user.user_id,
                tenant_id=user.tenant_id,
                method=auth_method,
                path=request.url.path,
            )

            # Store user in request state for dependency injection
            request.state.user = user
            request.state.tenant = tenant

            try:
                response = await call_next(request)
                return response
            finally:
                self._cleanup_context()

        # No valid credentials
        if self.config.allow_anonymous:
            user = create_anonymous_user(self.config.default_tenant_id)
            tenant = self._default_tenant
            set_current_user(user)
            set_current_tenant(tenant)
            request.state.user = user
            request.state.tenant = tenant

            logger.debug(
                "auth.anonymous",
                path=request.url.path,
            )

            try:
                response = await call_next(request)
                return response
            finally:
                self._cleanup_context()

        # Authentication required but not provided
        logger.warning(
            "auth.failed",
            path=request.url.path,
            reason="no_credentials",
        )

        return Response(
            content='{"detail": "Authentication required"}',
            status_code=401,
            media_type="application/json",
            headers={"WWW-Authenticate": "Bearer"},
        )

    def _is_exempt_path(self, path: str) -> bool:
        """Check if a path is exempt from authentication.

        Args:
            path: The request path

        Returns:
            True if exempt, False otherwise
        """
        return path in self.config.exempt_paths

    def _cleanup_context(self) -> None:
        """Clean up context variables after request."""
        set_current_user(None)
        set_current_tenant(None)


# Dependency injection functions for FastAPI


async def get_optional_user(
    request: Request,
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    api_key: Optional[str] = Depends(api_key_header),
) -> Optional[UserContext]:
    """Get the current user from request state (optional).

    This dependency returns None if no user is authenticated.

    Args:
        request: The FastAPI request

    Returns:
        UserContext or None
    """
    return getattr(request.state, "user", None)


async def get_current_user_dependency(
    request: Request,
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    api_key: Optional[str] = Depends(api_key_header),
) -> UserContext:
    """Get the current authenticated user (required).

    This dependency raises HTTPException if no user is authenticated.

    Args:
        request: The FastAPI request

    Returns:
        UserContext

    Raises:
        HTTPException: If no user is authenticated
    """
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_tenant_dependency(request: Request) -> TenantContext:
    """Get the current tenant context (required).

    Args:
        request: The FastAPI request

    Returns:
        TenantContext

    Raises:
        HTTPException: If no tenant context is available
    """
    tenant = getattr(request.state, "tenant", None)
    if tenant is None:
        raise HTTPException(
            status_code=401,
            detail="Tenant context required",
        )
    return tenant


def require_permission(permission: Permission):
    """Dependency factory to require a specific permission.

    Usage:
        @router.get("/agents")
        async def list_agents(user: UserContext = Depends(require_permission(Permission.AGENT_READ))):
            ...

    Args:
        permission: The required permission

    Returns:
        FastAPI dependency function
    """

    async def check_permission(
        user: UserContext = Depends(get_current_user_dependency),
    ) -> UserContext:
        if not user.has_permission(permission):
            logger.warning(
                "permission.denied",
                user_id=user.user_id,
                permission=permission.value,
            )
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: {permission.value} required",
            )
        return user

    return check_permission


def require_any_permission(permissions: Set[Permission]):
    """Dependency factory to require any of the specified permissions.

    Args:
        permissions: Set of acceptable permissions

    Returns:
        FastAPI dependency function
    """

    async def check_permissions(
        user: UserContext = Depends(get_current_user_dependency),
    ) -> UserContext:
        if not user.has_any_permission(permissions):
            perm_names = [p.value for p in permissions]
            logger.warning(
                "permission.denied",
                user_id=user.user_id,
                required_any=perm_names,
            )
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: one of {perm_names} required",
            )
        return user

    return check_permissions


def require_role(role: str):
    """Dependency factory to require a specific role.

    Args:
        role: The required role name

    Returns:
        FastAPI dependency function
    """

    async def check_role(
        user: UserContext = Depends(get_current_user_dependency),
    ) -> UserContext:
        if not user.has_role(role):
            logger.warning(
                "role.denied",
                user_id=user.user_id,
                required_role=role,
            )
            raise HTTPException(
                status_code=403,
                detail=f"Role denied: {role} required",
            )
        return user

    return check_role


def require_admin():
    """Dependency to require admin access.

    Returns:
        FastAPI dependency function
    """

    async def check_admin(
        user: UserContext = Depends(get_current_user_dependency),
    ) -> UserContext:
        if not user.is_admin():
            logger.warning(
                "admin.denied",
                user_id=user.user_id,
            )
            raise HTTPException(
                status_code=403,
                detail="Admin access required",
            )
        return user

    return check_admin


def require_tenant_access(tenant_id_param: str = "tenant_id"):
    """Dependency factory to verify user has access to the specified tenant.

    This checks that the user's tenant matches the requested tenant ID.

    Args:
        tenant_id_param: Name of the path/query parameter containing tenant ID

    Returns:
        FastAPI dependency function
    """

    async def check_tenant(
        request: Request,
        user: UserContext = Depends(get_current_user_dependency),
    ) -> UserContext:
        # Get tenant ID from path or query params
        tenant_id = request.path_params.get(tenant_id_param) or request.query_params.get(
            tenant_id_param
        )

        if tenant_id and tenant_id != user.tenant_id:
            # Allow admins to access other tenants for management
            if not user.is_admin():
                logger.warning(
                    "tenant.access.denied",
                    user_id=user.user_id,
                    user_tenant=user.tenant_id,
                    requested_tenant=tenant_id,
                )
                raise HTTPException(
                    status_code=403,
                    detail="Access denied to this tenant",
                )

        return user

    return check_tenant
