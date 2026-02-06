"""Send Notification Tool.

Allows agents to proactively send push notifications to users via
external communication channels (Telegram, Teams, Slack, etc.).
"""

from __future__ import annotations

from typing import Any

import structlog

from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol


class SendNotificationTool(ToolProtocol):
    """Agent-invoked tool to send proactive push notifications.

    The tool delegates to the CommunicationGateway, which resolves
    the recipient via the RecipientRegistry and dispatches via the
    appropriate OutboundSender.

    The gateway instance is injected at creation time by the factory.
    """

    def __init__(self, gateway: Any = None) -> None:
        self._gateway = gateway
        self._logger = structlog.get_logger()

    @property
    def name(self) -> str:
        return "send_notification"

    @property
    def description(self) -> str:
        return (
            "Send a proactive push notification to a user via an external "
            "communication channel (Telegram, Teams, etc.). "
            "Requires the recipient to have previously interacted with the system. "
            "Use this when you need to notify a user about results, alerts, or updates."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "description": (
                        "Target communication channel " "(e.g. 'telegram', 'teams', 'slack')"
                    ),
                },
                "recipient_id": {
                    "type": "string",
                    "description": (
                        "User ID of the notification recipient. "
                        "This is the application-level user ID, not the "
                        "channel-specific ID."
                    ),
                },
                "message": {
                    "type": "string",
                    "description": "Notification message text.",
                },
                "metadata": {
                    "type": "object",
                    "description": (
                        "Optional channel-specific formatting options "
                        "(e.g. parse_mode for Telegram)."
                    ),
                },
            },
            "required": ["channel", "recipient_id", "message"],
        }

    @property
    def requires_approval(self) -> bool:
        return True

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.MEDIUM

    @property
    def supports_parallelism(self) -> bool:
        return True

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

    async def execute(
        self,
        channel: str,
        recipient_id: str,
        message: str,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a push notification via the communication gateway.

        Args:
            channel: Target channel (e.g. 'telegram').
            recipient_id: Application-level user ID.
            message: Notification text.
            metadata: Optional formatting options.

        Returns:
            Dict with success status and delivery details.
        """
        if not self._gateway:
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

        result = await self._gateway.send_notification(request)

        if result.success:
            return {
                "success": True,
                "channel": result.channel,
                "recipient_id": result.recipient_id,
                "message": f"Notification sent to {result.recipient_id} via {result.channel}",
            }
        return {
            "success": False,
            "error": result.error or "Unknown delivery error",
            "channel": result.channel,
            "recipient_id": result.recipient_id,
        }

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        for field in ("channel", "recipient_id", "message"):
            if field not in kwargs:
                return False, f"Missing required parameter: {field}"
            if not isinstance(kwargs[field], str):
                return False, f"Parameter '{field}' must be a string"
            if not kwargs[field].strip():
                return False, f"Parameter '{field}' must not be empty"
        return True, None
