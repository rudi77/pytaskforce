"""Send Notification Tool.

Allows agents to proactively send push notifications to users via
external communication channels (Telegram, Teams, Slack, etc.).

Supports optional file attachments (PDF, photo, audio) that are
uploaded via the channel's native file-upload API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.tools.base_tool import BaseTool


class SendNotificationTool(BaseTool):
    """Agent-invoked tool to send proactive push notifications.

    The tool delegates to the CommunicationGateway, which resolves
    the recipient via the RecipientRegistry and dispatches via the
    appropriate OutboundSender.

    Supports optional file attachments — pass a list of local file paths
    in the ``attachments`` parameter and the gateway will upload them via
    the channel's native file API (Telegram sendDocument/sendPhoto/sendAudio).

    The gateway instance is injected at creation time by the factory.
    """

    tool_name = "send_notification"
    tool_description = (
        "Send a proactive push notification to the user via an external "
        "communication channel (Telegram, Teams, etc.). "
        "Channel and recipient default to the configured values — just "
        "provide the message text. "
        "To attach files (PDFs, photos, audio), pass a list of local file "
        "paths in the 'attachments' parameter; the type is auto-detected "
        "from the file extension."
    )
    tool_parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": (
                    "Notification message text. When attachments are "
                    "present, this is used as the caption of the first file."
                ),
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
            "attachments": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional list of local file paths to upload with the "
                    "notification. The sender auto-detects the media type "
                    "from the file extension (images → photo, audio → audio, "
                    "everything else → document)."
                ),
            },
            "metadata": {
                "type": "object",
                "description": (
                    "Optional channel-specific formatting options "
                    "(e.g. parse_mode for Telegram, attachment_type to "
                    "force a specific upload endpoint)."
                ),
            },
        },
        "required": ["message"],
    }
    tool_requires_approval = True
    tool_approval_risk_level = ApprovalRiskLevel.MEDIUM
    tool_supports_parallelism = True
    # Auto-approve when invoked from a scheduler-fired workflow run
    # (issue #177): the operator already vetted the workflow at design
    # time, and at 06:00 nobody is at the keyboard to grant interactive
    # approval — without this opt-in the approval queue silently times
    # out after 5 minutes and the message is never sent.
    tool_auto_approve_for_origins = frozenset({"scheduled_workflow"})

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
        attachments = kwargs.get("attachments") or []
        preview = message[:120] + "..." if len(message) > 120 else message
        lines = [
            f"Tool: {self.name}",
            "Operation: Send push notification",
            f"Channel: {channel}",
            f"Recipient: {recipient}",
            f"Message: {preview}",
        ]
        if attachments:
            lines.append(f"Attachments: {len(attachments)}")
            for i, p in enumerate(attachments[:3]):
                lines.append(f"  {i + 1}. {p}")
            if len(attachments) > 3:
                lines.append(f"  … +{len(attachments) - 3} more")
        return "\n".join(lines)

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution.

        Extends the base validation with these additional rules:
        - channel/recipient_id, when provided, must not be empty/whitespace.
        - message may be empty ONLY if at least one attachment is present
          (the attachment itself carries the notification).
        - attachments, when provided, must be a list of non-empty strings.
        """
        # Run base schema validation first (required + type checks).
        valid, error = super().validate_params(**kwargs)
        if not valid:
            return valid, error

        attachments = kwargs.get("attachments") or []
        if not isinstance(attachments, list):
            return False, "Parameter 'attachments' must be a list of file paths"
        for p in attachments:
            if not isinstance(p, str) or not p.strip():
                return False, "Every attachment path must be a non-empty string"

        # Message must be non-empty UNLESS attachments provide the payload.
        message = kwargs.get("message", "")
        if isinstance(message, str) and not message.strip() and not attachments:
            return (
                False,
                "Parameter 'message' must not be empty (unless 'attachments' "
                "is provided).",
            )

        # Channel/recipient_id are optional at the tool level; defaults fill in.
        for field in ("channel", "recipient_id"):
            value = kwargs.get(field, None)
            if isinstance(value, str) and value and not value.strip():
                return False, f"Parameter '{field}' must not be whitespace-only"

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
        attachments: list[str] | None = None,
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
            attachments: Optional list of local file paths to upload.
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
            self._logger.error(
                "send_notification.no_defaults",
                provided_channel=channel,
                provided_recipient=recipient_id,
                default_channel=self._default_channel,
                default_recipient_id=self._default_recipient_id,
            )
            return {
                "success": False,
                "error": (
                    "No channel/recipient configured. "
                    "Set notifications.default_channel and "
                    "notifications.default_recipient_id in profile YAML."
                ),
            }

        if not self._gateway:
            self._logger.error(
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

        # Resolve attachment paths: allow relative paths (resolved against
        # CWD), validate each exists before handing to the gateway.
        resolved_attachments: list[str] = []
        if attachments:
            for raw_path in attachments:
                p = Path(raw_path)
                if not p.is_absolute():
                    p = Path.cwd() / p
                p = p.resolve()
                if not p.is_file():
                    self._logger.error(
                        "send_notification.attachment_missing",
                        provided_path=raw_path,
                        resolved_path=str(p),
                        cwd=str(Path.cwd()),
                    )
                    return {
                        "success": False,
                        "error": (
                            f"Attachment not found: {raw_path}. "
                            f"Resolved to: {p}. "
                            f"CWD: {Path.cwd()}."
                        ),
                    }
                resolved_attachments.append(str(p))

        from taskforce.core.domain.gateway import NotificationRequest

        request = NotificationRequest(
            channel=channel,
            recipient_id=recipient_id,
            message=message,
            metadata=metadata or {},
            attachments=resolved_attachments,
        )

        self._logger.info(
            "send_notification.sending",
            channel=channel,
            recipient_id=recipient_id,
            message_preview=message[:80],
            attachment_count=len(request.attachments),
        )

        result = await self._gateway.send_notification(request)

        if result.success:
            self._logger.info(
                "send_notification.success",
                channel=result.channel,
                recipient_id=result.recipient_id,
                attachment_count=len(request.attachments),
            )
            summary = (
                f"Notification sent to {result.recipient_id} via {result.channel}"
            )
            if request.attachments:
                summary += f" with {len(request.attachments)} attachment(s)"
            return {
                "success": True,
                "channel": result.channel,
                "recipient_id": result.recipient_id,
                "attachment_count": len(request.attachments),
                "message": summary,
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
