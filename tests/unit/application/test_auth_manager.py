"""Tests for AuthManager service."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.auth import (
    AuthFlowType,
    AuthProviderType,
    AuthStatus,
    TokenData,
)
from taskforce.application.auth_manager import AuthManager


@pytest.fixture
def mock_token_store() -> AsyncMock:
    store = AsyncMock()
    store.save_token = AsyncMock()
    store.load_token = AsyncMock(return_value=None)
    store.delete_token = AsyncMock()
    store.list_providers = AsyncMock(return_value=[])
    return store


@pytest.fixture
def mock_device_flow() -> AsyncMock:
    flow = AsyncMock()
    flow.flow_type = "oauth2_device"
    flow.execute = AsyncMock(
        return_value={
            "provider": "google",
            "access_token": "new_access",
            "refresh_token": "new_refresh",
            "scopes": ["calendar.readonly"],
            "status": "active",
        }
    )
    return flow


@pytest.fixture
def provider_configs() -> dict:
    return {
        "google": {
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "default_flow": "oauth2_device",
            "default_scopes": ["calendar.readonly"],
        }
    }


@pytest.fixture
def auth_manager(
    mock_token_store: AsyncMock,
    mock_device_flow: AsyncMock,
    provider_configs: dict,
) -> AuthManager:
    return AuthManager(
        token_store=mock_token_store,
        auth_flows={"oauth2_device": mock_device_flow},
        provider_configs=provider_configs,
    )


class TestAuthManager:
    async def test_authenticate_returns_existing_valid_token(
        self, auth_manager: AuthManager, mock_token_store: AsyncMock
    ):
        """If a valid token exists, return it without running a flow."""
        valid_token = TokenData(
            provider=AuthProviderType.GOOGLE,
            access_token="valid_access",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        mock_token_store.load_token.return_value = valid_token.to_dict()

        result = await auth_manager.authenticate("google")

        assert result.success
        assert result.token.access_token == "valid_access"
        assert result.status == AuthStatus.ACTIVE

    async def test_authenticate_runs_flow_when_no_token(
        self,
        auth_manager: AuthManager,
        mock_token_store: AsyncMock,
        mock_device_flow: AsyncMock,
    ):
        """If no token exists, initiate the auth flow."""
        mock_token_store.load_token.return_value = None

        result = await auth_manager.authenticate("google")

        assert result.success
        mock_device_flow.execute.assert_called_once()
        mock_token_store.save_token.assert_called_once()

    async def test_authenticate_refreshes_expired_token(
        self, auth_manager: AuthManager, mock_token_store: AsyncMock
    ):
        """If token is expired but has refresh_token, try refresh."""
        expired_token = TokenData(
            provider=AuthProviderType.GOOGLE,
            access_token="expired_access",
            refresh_token="refresh_123",
            token_uri="https://oauth2.googleapis.com/token",
            client_id="cid",
            client_secret="cs",
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        mock_token_store.load_token.return_value = expired_token.to_dict()

        # Mock the HTTP refresh call.
        import aiohttp

        mock_resp = AsyncMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = AsyncMock(
            return_value={
                "access_token": "refreshed_access",
                "expires_in": 3600,
            }
        )
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.post = MagicMock(return_value=mock_resp)

        from unittest.mock import patch

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await auth_manager.authenticate("google")

        assert result.success
        assert result.token.access_token == "refreshed_access"

    async def test_authenticate_unknown_flow_type_fails(
        self, auth_manager: AuthManager, mock_token_store: AsyncMock
    ):
        """Unknown flow type returns a failure result."""
        mock_token_store.load_token.return_value = None

        result = await auth_manager.authenticate(
            "google", flow_type="unknown_flow"
        )

        assert not result.success
        assert "Unknown auth flow type" in result.error

    async def test_get_token_returns_none_when_not_stored(
        self, auth_manager: AuthManager, mock_token_store: AsyncMock
    ):
        mock_token_store.load_token.return_value = None
        result = await auth_manager.get_token("google")
        assert result is None

    async def test_get_token_returns_valid_token(
        self, auth_manager: AuthManager, mock_token_store: AsyncMock
    ):
        valid_token = TokenData(
            provider=AuthProviderType.GOOGLE,
            access_token="access",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        mock_token_store.load_token.return_value = valid_token.to_dict()

        result = await auth_manager.get_token("google")
        assert result is not None
        assert result.access_token == "access"

    async def test_revoke_deletes_token(
        self, auth_manager: AuthManager, mock_token_store: AsyncMock
    ):
        result = await auth_manager.revoke("google")
        assert result is True
        mock_token_store.delete_token.assert_called_once_with("google")

    async def test_authenticate_uses_provider_default_scopes(
        self,
        auth_manager: AuthManager,
        mock_token_store: AsyncMock,
        mock_device_flow: AsyncMock,
    ):
        """When no scopes provided, use provider's default_scopes."""
        mock_token_store.load_token.return_value = None

        await auth_manager.authenticate("google")

        call_kwargs = mock_device_flow.execute.call_args[1]
        assert call_kwargs["scopes"] == ["calendar.readonly"]
