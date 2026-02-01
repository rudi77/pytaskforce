"""Gmail tool for the personal assistant plugin."""

from __future__ import annotations

from dataclasses import dataclass
from email.mime.text import MIMEText
import base64
from typing import Any

from personal_assistant.tools.tool_base import ApprovalRiskLevel


GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]


@dataclass(frozen=True)
class GmailAuthConfig:
    """Authentication inputs for Gmail API usage."""

    access_token: str | None
    token_file: str | None


class GmailTool:
    """Interact with Gmail using the Google API."""

    @property
    def name(self) -> str:
        return "gmail"

    @property
    def description(self) -> str:
        return (
            "Access Gmail messages and drafts. Actions: list, read, draft, send. "
            "Requires OAuth credentials."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "read", "draft", "send"],
                },
                "user_id": {
                    "type": "string",
                    "description": "Gmail user id (default 'me')",
                },
                "query": {"type": "string", "description": "Gmail search query"},
                "label_ids": {"type": "array", "items": {"type": "string"}},
                "page_size": {"type": "integer"},
                "message_id": {"type": "string"},
                "to": {"type": "array", "items": {"type": "string"}},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "access_token": {"type": "string"},
                "token_file": {"type": "string"},
            },
            "required": ["action"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.MEDIUM

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        action = kwargs.get("action")
        if action not in {"list", "read", "draft", "send"}:
            return False, "action must be one of: list, read, draft, send"
        if action == "read" and not kwargs.get("message_id"):
            return False, "message_id is required for read action"
        if action in {"draft", "send"}:
            return _validate_draft_fields(kwargs)
        return True, None

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        action = kwargs["action"]
        auth = GmailAuthConfig(
            access_token=kwargs.get("access_token"),
            token_file=kwargs.get("token_file"),
        )
        service = _build_gmail_service(auth)
        user_id = kwargs.get("user_id", "me")
        handlers = {
            "list": _list_messages,
            "read": _get_message,
            "draft": _create_draft,
            "send": _send_message,
        }
        return handlers[action](service, user_id, kwargs)


def _build_gmail_service(auth: GmailAuthConfig):
    """Build a Gmail API client from provided credentials."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    credentials = _load_credentials(auth)
    return build("gmail", "v1", credentials=credentials)


def _load_credentials(auth: GmailAuthConfig):
    """Load OAuth credentials from token or token file."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    if auth.access_token:
        creds = Credentials(token=auth.access_token, scopes=GMAIL_SCOPES)
    elif auth.token_file:
        creds = Credentials.from_authorized_user_file(auth.token_file, GMAIL_SCOPES)
    else:
        raise ValueError("Provide access_token or token_file for GmailTool")

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def _list_messages(service: Any, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """List Gmail messages based on search criteria."""
    request = service.users().messages().list(
        userId=user_id,
        q=payload.get("query"),
        labelIds=payload.get("label_ids"),
        maxResults=payload.get("page_size", 10),
    )
    response = request.execute()
    return {
        "success": True,
        "messages": response.get("messages", []),
        "result_size_estimate": response.get("resultSizeEstimate"),
    }


def _get_message(service: Any, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Fetch a single Gmail message."""
    message_id = payload["message_id"]
    message = service.users().messages().get(
        userId=user_id,
        id=message_id,
        format="full",
    ).execute()
    return {"success": True, "message": message}


def _create_draft(service: Any, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Create a Gmail draft message."""
    raw_message = _encode_message(
        to=payload["to"],
        subject=payload["subject"],
        body=payload["body"],
    )
    draft = service.users().drafts().create(
        userId=user_id,
        body={"message": {"raw": raw_message}},
    ).execute()
    return {"success": True, "draft": draft}


def _send_message(service: Any, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Send a Gmail message immediately."""
    raw_message = _encode_message(
        to=payload["to"],
        subject=payload["subject"],
        body=payload["body"],
    )
    message = service.users().messages().send(
        userId=user_id,
        body={"raw": raw_message},
    ).execute()
    return {"success": True, "message": message}


def _encode_message(to: list[str], subject: str, body: str) -> str:
    """Encode an email message to a Gmail API raw string."""
    message = MIMEText(body)
    message["to"] = ", ".join(to)
    message["subject"] = subject
    return base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")


def _validate_draft_fields(payload: dict[str, Any]) -> tuple[bool, str | None]:
    """Validate fields required for draft/send actions."""
    if not isinstance(payload.get("to"), list) or not payload.get("to"):
        return False, "to must be a non-empty list"
    if not isinstance(payload.get("subject"), str) or not payload.get("subject"):
        return False, "subject must be a non-empty string"
    if not isinstance(payload.get("body"), str) or payload.get("body") is None:
        return False, "body must be a string"
    return True, None
