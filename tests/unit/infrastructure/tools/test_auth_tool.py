"""Tests for AuthTool."""

from unittest.mock import AsyncMock

import pytest

from taskforce.core.domain.auth import AuthFlowResult, AuthProviderType, AuthStatus
from taskforce.infrastructure.tools.native.auth_tool import AuthTool


@pytest.fixture
def mock_auth_manager() -> AsyncMock:
    manager = AsyncMock()
    manager.authenticate = AsyncMock(
        return_value=AuthFlowResult(
            success=True,
            provider=AuthProviderType.GOOGLE,
            status=AuthStatus.ACTIVE,
        )
    )
    return manager


@pytest.fixture
def auth_tool(mock_auth_manager: AsyncMock) -> AuthTool:
    return AuthTool(auth_manager=mock_auth_manager)


class TestAuthTool:
    def test_tool_name(self, auth_tool: AuthTool):
        assert auth_tool.name == "authenticate"

    def test_requires_approval(self, auth_tool: AuthTool):
        assert auth_tool.requires_approval is True

    async def test_execute_success(
        self, auth_tool: AuthTool, mock_auth_manager: AsyncMock
    ):
        result = await auth_tool._execute(provider="google")
        assert result["success"] is True
        assert result["provider"] == "google"
        assert result["status"] == "active"
        mock_auth_manager.authenticate.assert_called_once()

    async def test_execute_passes_scopes(
        self, auth_tool: AuthTool, mock_auth_manager: AsyncMock
    ):
        await auth_tool._execute(
            provider="google",
            scopes=["calendar.readonly"],
            flow_type="oauth2_device",
        )
        call_kwargs = mock_auth_manager.authenticate.call_args[1]
        assert call_kwargs["scopes"] == ["calendar.readonly"]
        assert call_kwargs["flow_type"] == "oauth2_device"

    async def test_execute_failure(self, mock_auth_manager: AsyncMock):
        mock_auth_manager.authenticate.return_value = AuthFlowResult(
            success=False,
            provider=AuthProviderType.GOOGLE,
            status=AuthStatus.FAILED,
            error="Timed out",
        )
        tool = AuthTool(auth_manager=mock_auth_manager)
        result = await tool._execute(provider="google")
        assert result["success"] is False
        assert result["error"] == "Timed out"

    async def test_execute_without_auth_manager(self):
        tool = AuthTool(auth_manager=None)
        result = await tool._execute(provider="google")
        assert result["success"] is False
        assert "not configured" in result["error"]

    def test_approval_preview(self, auth_tool: AuthTool):
        preview = auth_tool.get_approval_preview(
            provider="google",
            flow_type="oauth2_device",
            scopes=["calendar.readonly"],
        )
        assert "google" in preview
        assert "oauth2_device" in preview
        assert "calendar.readonly" in preview
