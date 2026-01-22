"""Unit tests for API key identity provider."""

import pytest
from datetime import datetime, timezone, timedelta

from taskforce.infrastructure.auth.api_key_provider import (
    APIKeyProvider,
    APIKeyRecord,
)
from taskforce.core.interfaces.identity import TenantContext, Permission


class TestAPIKeyRecord:
    """Tests for APIKeyRecord dataclass."""

    def test_create_record(self):
        """Test creating an API key record."""
        record = APIKeyRecord(
            key_id="key-123",
            key_hash="somehash",
            tenant_id="tenant-456",
            user_id="user-789",
            name="Test Key",
        )
        assert record.key_id == "key-123"
        assert record.is_active is True
        assert record.is_valid() is True

    def test_record_expiration(self):
        """Test API key expiration checking."""
        # Non-expired key
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        record = APIKeyRecord(
            key_id="key-1",
            key_hash="hash",
            tenant_id="t",
            user_id="u",
            name="Test",
            expires_at=future,
        )
        assert record.is_expired() is False
        assert record.is_valid() is True

        # Expired key
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        expired_record = APIKeyRecord(
            key_id="key-2",
            key_hash="hash",
            tenant_id="t",
            user_id="u",
            name="Test",
            expires_at=past,
        )
        assert expired_record.is_expired() is True
        assert expired_record.is_valid() is False

    def test_record_inactive(self):
        """Test inactive API key."""
        record = APIKeyRecord(
            key_id="key-1",
            key_hash="hash",
            tenant_id="t",
            user_id="u",
            name="Test",
            is_active=False,
        )
        assert record.is_valid() is False


class TestAPIKeyProvider:
    """Tests for APIKeyProvider."""

    @pytest.fixture
    def provider(self):
        """Provide a test API key provider."""
        return APIKeyProvider()

    @pytest.mark.asyncio
    async def test_create_and_validate_key(self, provider):
        """Test creating and validating an API key."""
        plaintext_key, record = provider.create_api_key(
            tenant_id="tenant-123",
            user_id="user-456",
            name="Test API Key",
            roles={"operator"},
        )

        # Verify key format
        assert plaintext_key.startswith("tf_")
        assert len(plaintext_key) > 10

        # Validate the key
        user = await provider.validate_api_key(plaintext_key)

        assert user is not None
        assert user.user_id == "user-456"
        assert user.tenant_id == "tenant-123"
        assert "operator" in user.roles
        assert user.has_permission(Permission.AGENT_EXECUTE)

    @pytest.mark.asyncio
    async def test_validate_invalid_key(self, provider):
        """Test validation rejects invalid keys."""
        # Wrong prefix
        user = await provider.validate_api_key("invalid_key")
        assert user is None

        # Correct prefix but not registered
        user = await provider.validate_api_key("tf_nonexistent_key")
        assert user is None

    @pytest.mark.asyncio
    async def test_validate_revoked_key(self, provider):
        """Test validation rejects revoked keys."""
        plaintext_key, record = provider.create_api_key(
            tenant_id="tenant-123",
            user_id="user-456",
            name="Test Key",
        )

        # Revoke the key
        success = provider.revoke_api_key(record.key_id)
        assert success is True

        # Validation should fail
        user = await provider.validate_api_key(plaintext_key)
        assert user is None

    @pytest.mark.asyncio
    async def test_validate_expired_key(self, provider):
        """Test validation rejects expired keys."""
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        plaintext_key, record = provider.create_api_key(
            tenant_id="tenant-123",
            user_id="user-456",
            name="Expired Key",
            expires_at=past,
        )

        user = await provider.validate_api_key(plaintext_key)
        assert user is None

    @pytest.mark.asyncio
    async def test_list_api_keys(self, provider):
        """Test listing API keys for a tenant."""
        # Create keys for different tenants
        provider.create_api_key(
            tenant_id="tenant-1",
            user_id="user-1",
            name="Key 1",
        )
        provider.create_api_key(
            tenant_id="tenant-1",
            user_id="user-2",
            name="Key 2",
        )
        provider.create_api_key(
            tenant_id="tenant-2",
            user_id="user-3",
            name="Key 3",
        )

        # List keys for tenant-1
        keys = provider.list_api_keys("tenant-1")
        assert len(keys) == 2

        # List keys for tenant-2
        keys = provider.list_api_keys("tenant-2")
        assert len(keys) == 1

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_key(self, provider):
        """Test revoking a non-existent key."""
        success = provider.revoke_api_key("nonexistent-key-id")
        assert success is False

    @pytest.mark.asyncio
    async def test_validate_token_delegates_to_api_key(self, provider):
        """Test that validate_token delegates to validate_api_key."""
        plaintext_key, record = provider.create_api_key(
            tenant_id="tenant-123",
            user_id="user-456",
            name="Test Key",
        )

        user = await provider.validate_token(plaintext_key)
        assert user is not None
        assert user.user_id == "user-456"

    @pytest.mark.asyncio
    async def test_key_with_multiple_roles(self, provider):
        """Test API key with multiple roles."""
        plaintext_key, record = provider.create_api_key(
            tenant_id="tenant-123",
            user_id="service-account",
            name="Service Key",
            roles={"admin", "operator"},
        )

        user = await provider.validate_api_key(plaintext_key)

        assert user is not None
        assert "admin" in user.roles
        assert "operator" in user.roles
        assert user.has_permission(Permission.USER_MANAGE)  # Admin permission
        assert user.has_permission(Permission.AGENT_EXECUTE)  # Operator permission

    @pytest.mark.asyncio
    async def test_key_metadata(self, provider):
        """Test API key with metadata."""
        plaintext_key, record = provider.create_api_key(
            tenant_id="tenant-123",
            user_id="service-account",
            name="Service Key",
            metadata={"environment": "production", "service": "worker"},
        )

        user = await provider.validate_api_key(plaintext_key)

        assert user is not None
        assert user.get_attribute("environment") == "production"
        assert user.get_attribute("service") == "worker"

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
    async def test_last_used_tracking(self, provider):
        """Test that last_used_at is updated on validation."""
        plaintext_key, record = provider.create_api_key(
            tenant_id="tenant-123",
            user_id="user-456",
            name="Test Key",
        )

        # Initially last_used_at is None
        assert record.last_used_at is None

        # Validate the key
        await provider.validate_api_key(plaintext_key)

        # Last used should be updated
        assert record.last_used_at is not None
