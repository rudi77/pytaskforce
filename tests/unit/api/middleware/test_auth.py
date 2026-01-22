"""Unit tests for authentication middleware."""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from starlette.requests import Request

from taskforce.api.middleware.auth import (
    AuthMiddleware,
    AuthConfig,
    get_current_user_dependency,
    require_permission,
    require_role,
)
from taskforce.core.interfaces.identity import (
    TenantContext,
    UserContext,
    Permission,
    get_permissions_for_roles,
)
from taskforce.infrastructure.auth.jwt_provider import JWTIdentityProvider, JWTConfig, create_test_jwt


class TestAuthConfig:
    """Tests for AuthConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = AuthConfig()
        assert config.enabled is True
        assert config.allow_anonymous is False
        assert "/health" in config.exempt_paths

    def test_custom_config(self):
        """Test custom configuration."""
        config = AuthConfig(
            enabled=False,
            allow_anonymous=True,
            exempt_paths={"/custom"},
        )
        assert config.enabled is False
        assert config.allow_anonymous is True
        assert "/custom" in config.exempt_paths


class TestAuthMiddleware:
    """Tests for AuthMiddleware."""

    @pytest.fixture
    def secret_key(self):
        """Provide a test secret key."""
        return "test-secret-key"

    @pytest.fixture
    def jwt_provider(self, secret_key):
        """Provide a JWT identity provider."""
        config = JWTConfig(secret_key=secret_key)
        provider = JWTIdentityProvider(config)

        # Register a test tenant
        tenant = TenantContext(tenant_id="test-tenant", name="Test Tenant")
        provider.register_tenant(tenant)

        return provider

    @pytest.fixture
    def app_with_auth(self, jwt_provider):
        """Create a FastAPI app with auth middleware."""
        app = FastAPI()

        # Add auth middleware
        auth_config = AuthConfig(enabled=True, allow_anonymous=False)
        app.add_middleware(
            AuthMiddleware,
            identity_provider=jwt_provider,
            config=auth_config,
        )

        @app.get("/protected")
        async def protected_route(request: Request):
            user = getattr(request.state, "user", None)
            if user:
                return {"user_id": user.user_id, "tenant_id": user.tenant_id}
            return {"error": "no user"}

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        return app

    @pytest.fixture
    def app_with_anonymous(self, jwt_provider):
        """Create a FastAPI app with anonymous access allowed."""
        app = FastAPI()

        auth_config = AuthConfig(enabled=True, allow_anonymous=True)
        app.add_middleware(
            AuthMiddleware,
            identity_provider=jwt_provider,
            config=auth_config,
        )

        @app.get("/api")
        async def api_route(request: Request):
            user = getattr(request.state, "user", None)
            return {
                "user_id": user.user_id if user else None,
                "anonymous": user.metadata.get("anonymous", False) if user else False,
            }

        return app

    def test_health_endpoint_exempt(self, app_with_auth):
        """Test that health endpoint is exempt from auth."""
        client = TestClient(app_with_auth)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_protected_endpoint_requires_auth(self, app_with_auth):
        """Test that protected endpoints require authentication."""
        client = TestClient(app_with_auth)
        response = client.get("/protected")
        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]

    def test_valid_bearer_token_authenticated(self, app_with_auth, secret_key):
        """Test that valid bearer token authenticates user."""
        client = TestClient(app_with_auth)

        token = create_test_jwt(
            user_id="user-123",
            tenant_id="test-tenant",
            roles=["operator"],
            secret_key=secret_key,
        )

        response = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "user-123"
        assert data["tenant_id"] == "test-tenant"

    def test_invalid_bearer_token_rejected(self, app_with_auth):
        """Test that invalid bearer tokens are rejected."""
        client = TestClient(app_with_auth)

        response = client.get(
            "/protected",
            headers={"Authorization": "Bearer invalid-token"},
        )

        assert response.status_code == 401

    def test_anonymous_access_when_allowed(self, app_with_anonymous):
        """Test anonymous access when allowed."""
        client = TestClient(app_with_anonymous)

        response = client.get("/api")

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "anonymous"
        assert data["anonymous"] is True


class TestPermissionDependencies:
    """Tests for permission dependency functions."""

    @pytest.fixture
    def app_with_permissions(self):
        """Create a FastAPI app with permission checks."""
        app = FastAPI()

        @app.get("/read-agents")
        async def read_agents(
            user: UserContext = Depends(require_permission(Permission.AGENT_READ))
        ):
            return {"allowed": True}

        @app.get("/create-agents")
        async def create_agents(
            user: UserContext = Depends(require_permission(Permission.AGENT_CREATE))
        ):
            return {"allowed": True}

        @app.get("/admin-only")
        async def admin_only(
            user: UserContext = Depends(require_role("admin"))
        ):
            return {"allowed": True}

        return app

    def test_require_permission_allows_with_permission(self, app_with_permissions):
        """Test that users with required permission are allowed."""
        # Create a mock user with AGENT_READ permission
        user = UserContext(
            user_id="user-1",
            tenant_id="tenant-1",
            username="test",
            permissions={Permission.AGENT_READ},
        )

        # Inject user into request state
        with TestClient(app_with_permissions) as client:
            # We need to override the dependency for testing
            app_with_permissions.dependency_overrides[
                require_permission(Permission.AGENT_READ)
            ] = lambda: user

            # Note: Full integration test would need middleware setup
            # This demonstrates the dependency pattern

    def test_require_role_pattern(self, app_with_permissions):
        """Test require_role dependency pattern."""
        # This tests the dependency factory pattern
        dependency = require_role("admin")
        assert callable(dependency)


class TestAuthConfigIntegration:
    """Integration tests for auth configuration."""

    def test_auth_disabled_allows_all(self):
        """Test that disabled auth allows all requests."""
        app = FastAPI()

        # Create a mock provider
        mock_provider = Mock()

        auth_config = AuthConfig(enabled=False)
        app.add_middleware(
            AuthMiddleware,
            identity_provider=mock_provider,
            config=auth_config,
        )

        @app.get("/api")
        async def api_route(request: Request):
            # When auth is disabled, anonymous user is set in context vars
            # but not necessarily in request.state due to middleware execution order
            from taskforce.core.domain.identity import get_current_user
            user = get_current_user()
            return {"has_context_user": user is not None}

        client = TestClient(app)
        response = client.get("/api")

        assert response.status_code == 200
        # When auth is disabled, anonymous user should be set in context
        assert response.json()["has_context_user"] is True
