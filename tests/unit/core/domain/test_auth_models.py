"""Tests for authentication domain models."""

from datetime import UTC, datetime, timedelta

from taskforce.core.domain.auth import (
    AuthFlowRequest,
    AuthFlowResult,
    AuthFlowType,
    AuthProviderType,
    AuthStatus,
    CredentialData,
    TokenData,
)


class TestAuthEnums:
    def test_provider_type_values(self):
        assert AuthProviderType.GOOGLE.value == "google"
        assert AuthProviderType.MICROSOFT.value == "microsoft"
        assert AuthProviderType.GITHUB.value == "github"
        assert AuthProviderType.CUSTOM.value == "custom"

    def test_flow_type_values(self):
        assert AuthFlowType.OAUTH2_DEVICE.value == "oauth2_device"
        assert AuthFlowType.OAUTH2_AUTH_CODE.value == "oauth2_auth_code"
        assert AuthFlowType.CREDENTIAL.value == "credential"

    def test_status_values(self):
        assert AuthStatus.ACTIVE.value == "active"
        assert AuthStatus.EXPIRED.value == "expired"
        assert AuthStatus.PENDING.value == "pending"


class TestTokenData:
    def test_is_expired_no_expiry(self):
        token = TokenData(
            provider=AuthProviderType.GOOGLE,
            access_token="abc",
        )
        assert not token.is_expired

    def test_is_expired_future(self):
        token = TokenData(
            provider=AuthProviderType.GOOGLE,
            access_token="abc",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        assert not token.is_expired

    def test_is_expired_past(self):
        token = TokenData(
            provider=AuthProviderType.GOOGLE,
            access_token="abc",
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert token.is_expired

    def test_to_dict_and_from_dict_roundtrip(self):
        token = TokenData(
            provider=AuthProviderType.GOOGLE,
            access_token="access123",
            refresh_token="refresh456",
            token_uri="https://oauth2.googleapis.com/token",
            client_id="client_id",
            client_secret="client_secret",
            scopes=["calendar.readonly"],
            expires_at=datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC),
            status=AuthStatus.ACTIVE,
        )
        data = token.to_dict()
        restored = TokenData.from_dict(data)

        assert restored.provider == token.provider
        assert restored.access_token == token.access_token
        assert restored.refresh_token == token.refresh_token
        assert restored.token_uri == token.token_uri
        assert restored.client_id == token.client_id
        assert restored.scopes == token.scopes
        assert restored.expires_at == token.expires_at
        assert restored.status == token.status

    def test_from_dict_minimal(self):
        data = {
            "provider": "google",
            "access_token": "abc",
        }
        token = TokenData.from_dict(data)
        assert token.provider == AuthProviderType.GOOGLE
        assert token.access_token == "abc"
        assert token.refresh_token is None
        assert token.expires_at is None
        assert token.status == AuthStatus.ACTIVE


class TestCredentialData:
    def test_to_dict_and_from_dict_roundtrip(self):
        cred = CredentialData(
            provider="my_service",
            username="user@example.com",
            password="secret123",
            metadata={"login_url": "https://example.com/login"},
        )
        data = cred.to_dict()
        restored = CredentialData.from_dict(data)

        assert restored.provider == cred.provider
        assert restored.username == cred.username
        assert restored.password == cred.password
        assert restored.metadata == cred.metadata


class TestAuthFlowRequest:
    def test_defaults(self):
        req = AuthFlowRequest(
            provider=AuthProviderType.GOOGLE,
            flow_type=AuthFlowType.OAUTH2_DEVICE,
        )
        assert req.scopes == []
        assert req.client_id == ""
        assert req.metadata == {}


class TestAuthFlowResult:
    def test_success_result(self):
        token = TokenData(
            provider=AuthProviderType.GOOGLE,
            access_token="abc",
        )
        result = AuthFlowResult(
            success=True,
            provider=AuthProviderType.GOOGLE,
            status=AuthStatus.ACTIVE,
            token=token,
        )
        assert result.success
        assert result.error is None
        assert result.token is not None

    def test_failure_result(self):
        result = AuthFlowResult(
            success=False,
            provider=AuthProviderType.GOOGLE,
            status=AuthStatus.FAILED,
            error="Flow timed out",
        )
        assert not result.success
        assert result.error == "Flow timed out"
        assert result.token is None
