"""Send Notification Tool.

Allows agents to proactively send push notifications to users via
external communication channels (Telegram, Teams, Slack, etc.).
"""

from __future__ import annotations

from typing import Any

import structlog

from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.tools.base_tool import BaseTool


class SendNotificationTool(BaseTool):
    """Agent-invoked tool to send proactive push notifications.

    The tool delegates to the CommunicationGateway, which resolves
    the recipient via the RecipientRegistry and dispatches via the
    appropriate OutboundSender.

    The gateway instance is injected at creation time by the factory.
    """

    tool_name = "send_notification"
    tool_description = (
        "Send a proactive push notification to the user via an external "
        "communication channel (Telegram, Teams, etc.). "
        "Channel and recipient default to the configured values — just "
        "provide the message text."
    )
    tool_parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Notification message text.",
            },
            "channel": {
                "type": "string",
                "description": (
                    "Target channel (e.g. 'telegram'). "
                    "Optional — defaults to the configured default channel."
                ),
            },
            "recipient_id": {
                "type": "string",
                "description": (
                    "Recipient user ID. "
                    "Optional — defaults to the configured default recipient."
                ),
            },
            "metadata": {
                "type": "object",
                "description": (
                    "Optional channel-specific formatting options "
                    "(e.g. parse_mode for Telegram)."
                ),
            },
        },
        "required": ["message"],
    }
    tool_requires_approval = True
    tool_approval_risk_level = ApprovalRiskLevel.MEDIUM
    tool_supports_parallelism = True

    def __init__(
        self,
        gateway: Any = None,
        default_channel: str | None = None,
        default_recipient_id: str | None = None,
    ) -> None:
        self._gateway = gateway
        self._default_channel = default_channel
        self._default_recipient_id = default_recipient_id
        self._logger = structlog.get_logger()

    def get_approval_preview(self, **kwargs: Any) -> str:
        channel = kwargs.get("channel", "unknown")
        recipient = kwargs.get("recipient_id", "unknown")
        message = kwargs.get("message", "")
        preview = message[:120] + "..." if len(message) > 120 else message
        return (
            f"Tool: {self.name}\n"
            f"Operation: Send push notification\n"
            f"Channel: {channel}\n"
            f"Recipient: {recipient}\n"
            f"Message: {preview}"
        )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution.

        Extends the base validation with an additional check that the
        required string fields are not empty or whitespace-only.
        """
        # Run base schema validation first (required + type checks).
        valid, error = super().validate_params(**kwargs)
        if not valid:
            return valid, error

        # Additional check: required string fields must not be empty.
        for field in ("channel", "recipient_id", "message"):
            value = kwargs.get(field, "")
            if isinstance(value, str) and not value.strip():
                return False, f"Parameter '{field}' must not be empty"

        return True, None

    # Placeholder values the LLM sometimes generates instead of real IDs
    _PLACEHOLDER_IDS = frozenset({
        "current_session_user", "current_user", "user", "self",
        "default", "me", "sender", "",
    })

    async def _execute(
        self,
        message: str = "",
        channel: str = "",
        recipient_id: str = "",
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a push notification via the communication gateway.

        Falls back to configured defaults when channel or recipient_id
        are missing or contain placeholder values like 'current_session_user'.

        Args:
            message: Notification text.
            channel: Target channel (optional, defaults to config).
            recipient_id: User ID (optional, defaults to config).
            metadata: Optional formatting options.

        Returns:
            Dict with success status and delivery details.
        """
        # Resolve defaults for missing or placeholder values
        if not channel or channel.lower() in self._PLACEHOLDER_IDS:
            channel = self._default_channel or ""
        if not recipient_id or recipient_id.lower() in self._PLACEHOLDER_IDS:
            recipient_id = self._default_recipient_id or ""

        if not channel or not recipient_id:
            return {
                "success": False,
                "error": (
                    "No channel/recipient configured. "
                    "Set notifications.default_channel and "
                    "notifications.default_recipient_id in profile YAML."
                ),
            }

        if not self._gateway:
            self._logger.warning(
                "send_notification.no_gateway",
                channel=channel,
                recipient_id=recipient_id,
            )
            return {
                "success": False,
                "error": (
                    "Communication gateway not configured. "
                    "Ensure the gateway is injected into the tool."
                ),
            }

        from taskforce.core.domain.gateway import NotificationRequest

        request = NotificationRequest(
            channel=channel,
            recipient_id=recipient_id,
            message=message,
            metadata=metadata or {},
        )

        self._logger.info(
            "send_notification.sending",
            channel=channel,
            recipient_id=recipient_id,
            message_preview=message[:80],
        )

        result = await self._gateway.send_notification(request)

        if result.success:
            self._logger.info(
                "send_notification.success",
                channel=result.channel,
                recipient_id=result.recipient_id,
            )
            return {
                "success": True,
                "channel": result.channel,
                "recipient_id": result.recipient_id,
                "message": f"Notification sent to {result.recipient_id} via {result.channel}",
            }

        self._logger.error(
            "send_notification.failed",
            channel=result.channel,
            recipient_id=result.recipient_id,
            error=result.error,
        )
        return {
            "success": False,
            "error": result.error or "Unknown delivery error",
            "channel": result.channel,
            "recipient_id": result.recipient_id,
        }
