"""Authenticate Tool.

Allows agents to explicitly authenticate with external services
(Google, Microsoft, GitHub, etc.) before accessing protected resources.
Delegates to the :class:`~taskforce.application.auth_manager.AuthManager`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.tools.base_tool import BaseTool

if TYPE_CHECKING:
    from taskforce.core.interfaces.auth import AuthManagerProtocol

logger = structlog.get_logger(__name__)


class AuthTool(BaseTool):
    """Agent-invoked tool for explicit authentication.

    Initiates an OAuth2 flow (device or auth code) or credential
    retrieval if no valid token exists for the requested provider.
    The auth manager handles token refresh, storage, and user
    interaction via the Communication Gateway.
    """

    tool_name = "authenticate"
    tool_description = (
        "Authenticate with an external service (Google, Microsoft, GitHub). "
        "Initiates an OAuth2 flow if no valid token exists. "
        "The user will be asked to authenticate via their preferred channel "
        "(Telegram, Teams, CLI, etc.). "
        "Use before accessing protected APIs (calendar, email, etc.)."
    )
    tool_parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "provider": {
                "type": "string",
                "enum": ["google", "microsoft", "github"],
                "description": "Service provider to authenticate with.",
            },
            "scopes": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "OAuth2 scopes to request "
                    "(e.g. ['https://www.googleapis.com/auth/calendar.readonly']). "
                    "Defaults to the provider's configured scopes."
                ),
            },
            "flow_type": {
                "type": "string",
                "enum": ["oauth2_device", "oauth2_auth_code", "credential"],
                "description": (
                    "Authentication flow type. Defaults to 'oauth2_device' "
                    "(recommended for headless/remote scenarios)."
                ),
            },
            "channel": {
                "type": "string",
                "description": (
                    "Communication channel for user interaction during auth "
                    "(e.g. 'telegram'). Optional — uses configured default."
                ),
            },
            "recipient_id": {
                "type": "string",
                "description": (
                    "Recipient ID on the communication channel. "
                    "Optional — uses configured default."
                ),
            },
        },
        "required": ["provider"],
    }
    tool_requires_approval = True
    tool_approval_risk_level = ApprovalRiskLevel.HIGH
    tool_supports_parallelism = False

    def __init__(self, auth_manager: AuthManagerProtocol | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._auth_manager = auth_manager

    def get_approval_preview(self, **kwargs: Any) -> str:
        """Return a human-readable preview of the auth action."""
        provider = kwargs.get("provider", "unknown")
        flow = kwargs.get("flow_type", "oauth2_device")
        scopes = kwargs.get("scopes", [])
        scope_str = ", ".join(scopes) if scopes else "provider defaults"
        return (
            f"Tool: {self.name}\n"
            f"Operation: Authenticate with {provider}\n"
            f"Flow: {flow}\n"
            f"Scopes: {scope_str}"
        )

    async def _execute(self, **kwargs: Any) -> dict[str, Any]:
        """Execute the authentication flow.

        Args:
            **kwargs: Tool parameters (provider, scopes, flow_type, etc.).

        Returns:
            Dictionary with success status and provider info.
        """
        if self._auth_manager is None:
            return {
                "success": False,
                "error": (
                    "Auth manager not configured. " "Add an 'auth' section to the profile YAML."
                ),
            }

        provider = kwargs["provider"]
        scopes = kwargs.get("scopes")
        flow_type = kwargs.get("flow_type")
        channel = kwargs.get("channel")
        recipient_id = kwargs.get("recipient_id")

        result = await self._auth_manager.authenticate(
            provider=provider,
            scopes=scopes,
            flow_type=flow_type,
            channel=channel,
            recipient_id=recipient_id,
        )

        return {
            "success": result.success,
            "provider": result.provider.value,
            "status": result.status.value,
            "error": result.error,
        }
