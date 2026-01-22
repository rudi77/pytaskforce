"""Unit tests for JWT identity provider."""

import pytest
from datetime import datetime, timezone, timedelta

from taskforce.infrastructure.auth.jwt_provider import (
    JWTIdentityProvider,
    JWTConfig,
    create_test_jwt,
)
from taskforce.core.interfaces.identity import TenantContext, Permission


class TestJWTConfig:
    """Tests for JWTConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = JWTConfig()
        assert config.secret_key is None
        assert config.algorithms == ["HS256"]
        assert config.tenant_claim == "tenant_id"
        assert config.roles_claim == "roles"

    def test_custom_config(self):
        """Test custom configuration."""
        config = JWTConfig(
            secret_key="test-secret",
            issuer="test-issuer",
            audience="test-audience",
        )
        assert config.secret_key == "test-secret"
        assert config.issuer == "test-issuer"
        assert config.audience == "test-audience"


class TestJWTIdentityProvider:
    """Tests for JWTIdentityProvider."""

    @pytest.fixture
    def secret_key(self):
        """Provide a test secret key."""
        return "test-secret-key-for-jwt-signing"

    @pytest.fixture
    def config(self, secret_key):
        """Provide a test JWT config."""
        return JWTConfig(secret_key=secret_key)

    @pytest.fixture
    def provider(self, config):
        """Provide a test JWT identity provider."""
        return JWTIdentityProvider(config)

    @pytest.mark.asyncio
    async def test_validate_valid_token(self, provider, secret_key):
        """Test validation of a valid JWT token."""
        token = create_test_jwt(
            user_id="user-123",
            tenant_id="tenant-456",
            roles=["operator"],
            secret_key=secret_key,
        )

        user = await provider.validate_token(token)

        assert user is not None
        assert user.user_id == "user-123"
        assert user.tenant_id == "tenant-456"
        assert "operator" in user.roles
        assert user.has_permission(Permission.AGENT_EXECUTE)

    @pytest.mark.asyncio
    async def test_validate_token_with_multiple_roles(self, provider, secret_key):
        """Test token with multiple roles."""
        token = create_test_jwt(
            user_id="user-123",
            tenant_id="tenant-456",
            roles=["admin", "agent_designer"],
            secret_key=secret_key,
        )

        user = await provider.validate_token(token)

        assert user is not None
        assert "admin" in user.roles
        assert "agent_designer" in user.roles
        # Admin permissions
        assert user.has_permission(Permission.USER_MANAGE)
        # Agent designer permissions
        assert user.has_permission(Permission.AGENT_CREATE)

    @pytest.mark.asyncio
    async def test_validate_expired_token(self, provider, secret_key):
        """Test validation rejects expired tokens."""
        token = create_test_jwt(
            user_id="user-123",
            tenant_id="tenant-456",
            roles=["operator"],
            secret_key=secret_key,
            expires_in_seconds=-3600,  # Expired 1 hour ago
        )

        user = await provider.validate_token(token)

        assert user is None

    @pytest.mark.asyncio
    async def test_validate_invalid_signature(self, provider, secret_key):
        """Test validation rejects tokens with invalid signatures."""
        token = create_test_jwt(
            user_id="user-123",
            tenant_id="tenant-456",
            roles=["operator"],
            secret_key="wrong-secret-key",
        )

        user = await provider.validate_token(token)

        assert user is None

    @pytest.mark.asyncio
    async def test_validate_malformed_token(self, provider):
        """Test validation rejects malformed tokens."""
        user = await provider.validate_token("not-a-valid-jwt")
        assert user is None

        user = await provider.validate_token("only.two.parts")
        assert user is None

        user = await provider.validate_token("")
        assert user is None

    @pytest.mark.asyncio
    async def test_validate_token_wrong_issuer(self, secret_key):
        """Test validation rejects tokens with wrong issuer."""
        config = JWTConfig(secret_key=secret_key, issuer="expected-issuer")
        provider = JWTIdentityProvider(config)

        token = create_test_jwt(
            user_id="user-123",
            tenant_id="tenant-456",
            roles=["operator"],
            secret_key=secret_key,
            iss="wrong-issuer",
        )

        user = await provider.validate_token(token)
        assert user is None

    @pytest.mark.asyncio
    async def test_validate_api_key_returns_none(self, provider):
        """Test that API key validation returns None for JWT provider."""
        user = await provider.validate_api_key("any-key")
        assert user is None

    @pytest.mark.asyncio
    async def test_get_tenant(self, provider):
        """Test tenant retrieval."""
        tenant = TenantContext(tenant_id="test-tenant", name="Test Tenant")
        provider.register_tenant(tenant)

        result = await provider.get_tenant("test-tenant")
        assert result is not None
        assert result.tenant_id == "test-tenant"

        result = await provider.get_tenant("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_user(self, provider, secret_key):
        """Test user retrieval after validation."""
        from taskforce.core.interfaces.identity import UserContext, get_permissions_for_roles

        user = UserContext(
            user_id="user-123",
            tenant_id="tenant-456",
            username="testuser",
            roles={"operator"},
            permissions=get_permissions_for_roles({"operator"}),
        )
        provider.register_user(user)

        result = await provider.get_user("user-123", "tenant-456")
        assert result is not None
        assert result.user_id == "user-123"

        result = await provider.get_user("nonexistent", "tenant-456")
        assert result is None

    @pytest.mark.asyncio
    async def test_token_with_extra_claims(self, provider, secret_key):
        """Test that extra claims are preserved in attributes."""
        token = create_test_jwt(
            user_id="user-123",
            tenant_id="tenant-456",
            roles=["operator"],
            secret_key=secret_key,
            department="engineering",
            team="platform",
        )

        user = await provider.validate_token(token)

        assert user is not None
        assert user.get_attribute("department") == "engineering"
        assert user.get_attribute("team") == "platform"


class TestCreateTestJWT:
    """Tests for the test JWT creation utility."""

    def test_create_basic_jwt(self):
        """Test creating a basic JWT."""
        token = create_test_jwt(
            user_id="user-1",
            tenant_id="tenant-1",
            roles=["operator"],
            secret_key="secret",
        )

        # Should have 3 parts separated by dots
        parts = token.split(".")
        assert len(parts) == 3

    def test_create_jwt_with_extra_claims(self):
        """Test creating a JWT with extra claims."""
        token = create_test_jwt(
            user_id="user-1",
            tenant_id="tenant-1",
            roles=["admin"],
            secret_key="secret",
            custom_claim="custom_value",
        )

        assert token is not None
        # Verify the token can be decoded
        import base64
        import json

        payload_b64 = token.split(".")[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload_b64 = payload_b64.replace("-", "+").replace("_", "/")
        payload = json.loads(base64.b64decode(payload_b64))

        assert payload["custom_claim"] == "custom_value"
