"""Tests for OAuth2 Device Authorization Flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskforce.infrastructure.auth.oauth2_device_flow import OAuth2DeviceFlow


@pytest.fixture
def device_flow() -> OAuth2DeviceFlow:
    return OAuth2DeviceFlow()


@pytest.fixture
def mock_interaction() -> AsyncMock:
    return AsyncMock(return_value=None)


class TestOAuth2DeviceFlow:
    def test_flow_type(self, device_flow: OAuth2DeviceFlow):
        assert device_flow.flow_type == "oauth2_device"

    def test_resolve_endpoints_google(self, device_flow: OAuth2DeviceFlow):
        endpoints = device_flow._resolve_endpoints("google", None)
        assert "device_auth_url" in endpoints
        assert "token_url" in endpoints

    def test_resolve_endpoints_custom_metadata(self, device_flow: OAuth2DeviceFlow):
        meta = {
            "device_auth_url": "https://custom.example.com/device",
            "token_url": "https://custom.example.com/token",
        }
        endpoints = device_flow._resolve_endpoints("custom", meta)
        assert endpoints["device_auth_url"] == meta["device_auth_url"]

    def test_resolve_endpoints_unknown_provider_raises(
        self, device_flow: OAuth2DeviceFlow
    ):
        with pytest.raises(ValueError, match="No device flow endpoints"):
            device_flow._resolve_endpoints("unknown_provider", None)

    async def test_notify_user_sends_verification_url(
        self, device_flow: OAuth2DeviceFlow, mock_interaction: AsyncMock
    ):
        device_resp = {
            "verification_uri": "https://google.com/device",
            "user_code": "ABCD-1234",
            "device_code": "dc_123",
        }
        await device_flow._notify_user(device_resp, mock_interaction)
        mock_interaction.assert_called_once()
        message = mock_interaction.call_args[0][0]
        assert "https://google.com/device" in message
        assert "ABCD-1234" in message

    async def test_notify_user_prefers_verification_uri_complete(
        self, device_flow: OAuth2DeviceFlow, mock_interaction: AsyncMock
    ):
        device_resp = {
            "verification_uri": "https://google.com/device",
            "verification_uri_complete": "https://google.com/device?code=ABCD",
            "user_code": "ABCD-1234",
            "device_code": "dc_123",
        }
        await device_flow._notify_user(device_resp, mock_interaction)
        message = mock_interaction.call_args[0][0]
        assert "https://google.com/device?code=ABCD" in message

    def test_parse_token_response(self, device_flow: OAuth2DeviceFlow):
        data = {
            "access_token": "at_123",
            "refresh_token": "rt_456",
            "expires_in": 3600,
            "scope": "calendar.readonly gmail.readonly",
        }
        result = device_flow._parse_token_response(data, "google")
        assert result["access_token"] == "at_123"
        assert result["refresh_token"] == "rt_456"
        assert result["provider"] == "google"
        assert "calendar.readonly" in result["scopes"]

    async def test_token_request_pending_returns_none(
        self, device_flow: OAuth2DeviceFlow
    ):
        """authorization_pending should return None (keep polling)."""
        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value={"error": "authorization_pending"})

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await device_flow._token_request(
                "https://token.url",
                "client_id",
                "client_secret",
                "device_code",
                "urn:ietf:params:oauth:grant-type:device_code",
                "google",
            )
        assert result is None

    async def test_token_request_denied_raises(self, device_flow: OAuth2DeviceFlow):
        """access_denied should raise RuntimeError."""
        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value={"error": "access_denied"})

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(RuntimeError, match="access_denied"):
                await device_flow._token_request(
                    "https://token.url",
                    "client_id",
                    "client_secret",
                    "device_code",
                    "urn:ietf:params:oauth:grant-type:device_code",
                    "google",
                )
