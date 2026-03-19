"""Gmail tool for reading emails.

Provides list and read operations for Gmail messages.
Uses the same OAuth token as the calendar tool
(~/.taskforce/google_token.json).
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any

import structlog

from taskforce.core.domain.errors import ToolError, tool_error_payload
from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.tools.base_tool import BaseTool

logger = structlog.get_logger(__name__)


class GmailTool(BaseTool):
    """Tool for reading Gmail messages.

    Supports listing messages (with search queries) and reading
    individual messages. Requires Google OAuth credentials.
    """

    tool_name = "gmail"
    tool_description = (
        "Read Gmail messages. Actions: list (search/list emails), "
        "read (get full email content by ID). "
        "Use list with a query like 'is:unread' or 'from:someone@example.com' "
        "to find messages, then read to get the full content."
    )
    tool_parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "read"],
                "description": "Gmail action: list or read",
            },
            "query": {
                "type": "string",
                "description": (
                    "Gmail search query (for list). Examples: "
                    "'is:unread', 'from:boss@company.com', 'subject:invoice', "
                    "'newer_than:1d', 'is:unread category:primary'"
                ),
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum messages to return (default: 10, max: 25)",
            },
            "message_id": {
                "type": "string",
                "description": "Message ID (required for read action)",
            },
        },
        "required": ["action"],
    }
    tool_requires_approval = False
    tool_approval_risk_level = ApprovalRiskLevel.LOW
    tool_supports_parallelism = True

    async def _execute(self, **kwargs: Any) -> dict[str, Any]:
        """Execute a Gmail action."""
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError:
            return {
                "success": False,
                "error": (
                    "Google API not available. Install with: "
                    "uv sync --extra personal-assistant"
                ),
            }

        action = kwargs.get("action")
        if action not in ("list", "read"):
            return {"success": False, "error": "action must be 'list' or 'read'"}

        try:
            service = _build_service(build, Credentials)

            if action == "list":
                return await _list_messages(service, kwargs)
            return await _read_message(service, kwargs)
        except Exception as exc:
            return tool_error_payload(
                ToolError(f"gmail failed: {exc}", tool_name="gmail")
            )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        action = kwargs.get("action")
        if action not in ("list", "read"):
            return False, "action must be 'list' or 'read'"
        if action == "read" and not kwargs.get("message_id"):
            return False, "message_id is required for read action"
        return True, None


def _build_service(build: Any, credentials_cls: Any) -> Any:
    """Build Gmail API service using the shared OAuth token."""
    import json
    from pathlib import Path

    from google.auth.transport.requests import Request

    token_path = Path.home() / ".taskforce" / "google_token.json"
    if not token_path.exists():
        raise ValueError(
            "No credentials found. Run 'python scripts/google_auth.py' first."
        )

    with open(token_path) as f:
        creds_data = json.load(f)

    creds = credentials_cls.from_authorized_user_info(creds_data)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)


async def _list_messages(service: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """List Gmail messages matching a search query."""
    query = kwargs.get("query", "")
    max_results = min(int(kwargs.get("max_results", 10)), 25)

    result = await asyncio.to_thread(
        lambda: service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )

    message_ids = result.get("messages", [])
    if not message_ids:
        return {
            "success": True,
            "messages": [],
            "count": 0,
            "query": query,
        }

    # Fetch snippet/headers for each message for useful preview.
    messages = []
    for msg_ref in message_ids[:max_results]:
        msg = await asyncio.to_thread(
            lambda mid=msg_ref["id"]: service.users()
            .messages()
            .get(userId="me", id=mid, format="metadata", metadataHeaders=["From", "Subject", "Date"])
            .execute()
        )
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        messages.append({
            "id": msg["id"],
            "snippet": msg.get("snippet", ""),
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "labels": msg.get("labelIds", []),
        })

    return {
        "success": True,
        "messages": messages,
        "count": len(messages),
        "query": query,
    }


async def _read_message(service: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Read a single Gmail message by ID."""
    message_id = kwargs["message_id"]

    msg = await asyncio.to_thread(
        lambda: service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )

    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    body = _extract_body(msg.get("payload", {}))

    return {
        "success": True,
        "id": msg["id"],
        "from": headers.get("From", ""),
        "to": headers.get("To", ""),
        "subject": headers.get("Subject", ""),
        "date": headers.get("Date", ""),
        "body": body,
        "labels": msg.get("labelIds", []),
        "snippet": msg.get("snippet", ""),
    }


def _extract_body(payload: dict[str, Any]) -> str:
    """Extract plain text body from Gmail message payload."""
    # Direct body
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

    # Multipart — look for text/plain part
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
        # Nested multipart
        if part.get("parts"):
            result = _extract_body(part)
            if result:
                return result

    # Fallback: try text/html
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
            html = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
            # Strip HTML tags for plain text approximation
            import re
            return re.sub(r"<[^>]+>", "", html).strip()

    return "(no body content)"
