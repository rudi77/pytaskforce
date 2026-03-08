"""Gmail tool for interacting with Google Gmail API.

Provides list, read, draft, and send operations for Gmail messages.
Promoted from examples/personal_assistant to a native tool.
"""

from __future__ import annotations

import asyncio
import base64
from email.mime.text import MIMEText
from typing import Any

import structlog

from taskforce.core.domain.errors import ToolError, tool_error_payload
from taskforce.core.interfaces.tools import ApprovalRiskLevel

logger = structlog.get_logger(__name__)

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]


class GmailTool:
    """Tool for interacting with Google Gmail.

    Supports listing messages, reading a specific message, creating drafts,
    and sending emails. Requires Google Gmail API credentials.
    """

    def __init__(self, credentials_file: str | None = None) -> None:
        self._credentials_file = credentials_file

    @property
    def name(self) -> str:
        return "gmail"

    @property
    def description(self) -> str:
        return (
            "Interact with Google Gmail. Actions: list (search/list messages), "
            "read (get a specific message), draft (create a draft), "
            "send (send an email). Requires Google Gmail API credentials."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "read", "draft", "send"],
                    "description": "Gmail action to perform",
                },
                "user_id": {
                    "type": "string",
                    "description": "Gmail user ID (default: 'me')",
                },
                "query": {
                    "type": "string",
                    "description": "Gmail search query (for list action)",
                },
                "label_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Label IDs to filter by (for list action)",
                },
                "page_size": {
                    "type": "integer",
                    "description": "Maximum number of messages to return (default: 10)",
                },
                "message_id": {
                    "type": "string",
                    "description": "Message ID (for read action)",
                },
                "to": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Recipient email addresses (for draft/send)",
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject (for draft/send)",
                },
                "body": {
                    "type": "string",
                    "description": "Email body text (for draft/send)",
                },
            },
            "required": ["action"],
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
        """Generate a human-readable preview of the Gmail operation."""
        action = kwargs.get("action", "")
        subject = kwargs.get("subject", "")
        to = kwargs.get("to", [])
        to_str = ", ".join(to) if isinstance(to, list) else str(to)
        lines = [f"Tool: {self.name}", f"Operation: {action}"]
        if subject:
            lines.append(f"Subject: {subject}")
        if to_str:
            lines.append(f"To: {to_str}")
        return "\n".join(lines)

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters."""
        action = kwargs.get("action")
        if action not in ("list", "read", "draft", "send"):
            return False, "action must be one of: list, read, draft, send"
        if action == "read" and not kwargs.get("message_id"):
            return False, "message_id is required for read action"
        if action in ("draft", "send"):
            return _validate_compose_fields(kwargs)
        return True, None

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Execute a Gmail action."""
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError:
            return {
                "success": False,
                "error": (
                    "Google Gmail API not available. Install with: "
                    "uv sync --extra personal-assistant"
                ),
            }

        action = kwargs.pop("action", None)
        try:
            service = self._build_service(build, Credentials)
            user_id = kwargs.pop("user_id", "me")

            if action == "list":
                return await self._list_messages(service, user_id, **kwargs)
            if action == "read":
                return await self._read_message(service, user_id, **kwargs)
            if action == "draft":
                return await self._create_draft(service, user_id, **kwargs)
            if action == "send":
                return await self._send_message(service, user_id, **kwargs)
            return {"success": False, "error": f"Unknown action: {action}"}
        except Exception as exc:
            return tool_error_payload(
                ToolError(f"{self.name} failed: {exc}", tool_name=self.name)
            )

    def _build_service(self, build: Any, credentials_cls: Any) -> Any:
        """Build the Gmail API service."""
        import json
        import os
        from pathlib import Path

        from google.auth.transport.requests import Request

        creds_file = self._credentials_file
        if not creds_file:
            # Check environment variable
            env_file = os.environ.get("GOOGLE_TOKEN_FILE")
            if env_file and Path(env_file).exists():
                creds_file = env_file
            else:
                # Try default location
                default_path = Path.home() / ".taskforce" / "google_credentials.json"
                if default_path.exists():
                    creds_file = str(default_path)
                else:
                    raise ValueError(
                        "No credentials_file configured. Set the credentials_file parameter, "
                        "GOOGLE_TOKEN_FILE environment variable, "
                        "or place credentials at ~/.taskforce/google_credentials.json"
                    )

        creds_path = Path(creds_file)
        if not creds_path.exists():
            raise FileNotFoundError(f"Credentials file not found: {creds_path}")

        with open(creds_path) as f:
            creds_data = json.load(f)

        creds = credentials_cls.from_authorized_user_info(creds_data, GMAIL_SCOPES)

        # Refresh expired credentials if possible
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

        return build("gmail", "v1", credentials=creds)

    async def _list_messages(
        self, service: Any, user_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        """List Gmail messages based on search criteria."""
        query = kwargs.get("query")
        label_ids = kwargs.get("label_ids")
        page_size = int(kwargs.get("page_size", 10))

        request_kwargs: dict[str, Any] = {
            "userId": user_id,
            "maxResults": page_size,
        }
        if query:
            request_kwargs["q"] = query
        if label_ids:
            request_kwargs["labelIds"] = label_ids

        response = await asyncio.to_thread(
            lambda: service.users().messages().list(**request_kwargs).execute()
        )

        messages = response.get("messages", [])
        result_size = response.get("resultSizeEstimate", 0)

        return {
            "success": True,
            "messages": messages,
            "count": len(messages),
            "result_size_estimate": result_size,
        }

    async def _read_message(
        self, service: Any, user_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        """Fetch a single Gmail message with headers and body."""
        message_id = kwargs["message_id"]

        message = await asyncio.to_thread(
            lambda: service.users()
            .messages()
            .get(userId=user_id, id=message_id, format="full")
            .execute()
        )

        # Extract useful header fields
        headers = message.get("payload", {}).get("headers", [])
        header_map = {h["name"].lower(): h["value"] for h in headers}

        # Extract plain text body
        body_text = _extract_body_text(message.get("payload", {}))

        return {
            "success": True,
            "message_id": message.get("id", ""),
            "thread_id": message.get("threadId", ""),
            "subject": header_map.get("subject", ""),
            "from": header_map.get("from", ""),
            "to": header_map.get("to", ""),
            "date": header_map.get("date", ""),
            "snippet": message.get("snippet", ""),
            "body": body_text,
            "labels": message.get("labelIds", []),
        }

    async def _create_draft(
        self, service: Any, user_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        """Create a Gmail draft message."""
        raw_message = _encode_message(
            to=kwargs["to"],
            subject=kwargs["subject"],
            body=kwargs["body"],
        )
        draft = await asyncio.to_thread(
            lambda: service.users()
            .drafts()
            .create(userId=user_id, body={"message": {"raw": raw_message}})
            .execute()
        )

        return {
            "success": True,
            "draft_id": draft.get("id", ""),
            "message": f"Draft created with subject '{kwargs['subject']}'",
        }

    async def _send_message(
        self, service: Any, user_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        """Send a Gmail message immediately."""
        raw_message = _encode_message(
            to=kwargs["to"],
            subject=kwargs["subject"],
            body=kwargs["body"],
        )
        sent = await asyncio.to_thread(
            lambda: service.users()
            .messages()
            .send(userId=user_id, body={"raw": raw_message})
            .execute()
        )

        return {
            "success": True,
            "message_id": sent.get("id", ""),
            "thread_id": sent.get("threadId", ""),
            "message": f"Email sent to {', '.join(kwargs['to'])}",
        }


def _encode_message(to: list[str], subject: str, body: str) -> str:
    """Encode an email message to a Gmail API raw string."""
    message = MIMEText(body)
    message["to"] = ", ".join(to)
    message["subject"] = subject
    return base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")


def _extract_body_text(payload: dict[str, Any]) -> str:
    """Extract plain text body from Gmail message payload.

    Handles both simple and multipart message structures.
    """
    mime_type = payload.get("mimeType", "")

    # Simple text message
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        return ""

    # Multipart message - look for text/plain part
    parts = payload.get("parts", [])
    for part in parts:
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    # Nested multipart - recurse into first multipart section
    for part in parts:
        if part.get("mimeType", "").startswith("multipart/"):
            return _extract_body_text(part)

    return ""


def _validate_compose_fields(payload: dict[str, Any]) -> tuple[bool, str | None]:
    """Validate fields required for draft/send actions."""
    if not isinstance(payload.get("to"), list) or not payload.get("to"):
        return False, "to must be a non-empty list of email addresses"
    if not isinstance(payload.get("subject"), str) or not payload.get("subject"):
        return False, "subject must be a non-empty string"
    if not isinstance(payload.get("body"), str) or payload.get("body") is None:
        return False, "body must be a string"
    return True, None
