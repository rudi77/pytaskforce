"""Gmail tool for reading and sending emails.

Provides list, read, send, and draft operations for Gmail messages.
Uses the same OAuth token as the calendar tool
(~/.taskforce/google_token.json).

The ``list`` action supports a ``since_last_check`` flag that filters
out messages already reported in a previous call, enabling reliable
periodic email-check scheduler jobs without duplicate notifications.
"""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from taskforce.core.domain.errors import ToolError, tool_error_payload
from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.tools.base_tool import BaseTool

if TYPE_CHECKING:
    from taskforce.core.interfaces.auth import AuthManagerProtocol

logger = structlog.get_logger(__name__)

# Default location for the seen-message-IDs state file.
#
# Pre-#213 this was ``.taskforce/gmail_seen.json`` (single top-level
# file shared across every user). The new default groups butler-
# specific state under ``.taskforce/butler/`` so a future
# ``calendar_last_check.json`` etc. can sit alongside without
# cluttering the top level. Enterprise plugins route this directory
# per-(tenant, user) via ``set_butler_state_dir_override`` so
# multi-user deployments don't share seen-id tracking across users.
_DEFAULT_BUTLER_DIR = Path(".taskforce") / "butler"
_SEEN_FILE_NAME = "gmail_seen.json"
# Cap the persisted set so the file doesn't grow unbounded.
_MAX_SEEN_IDS = 500


def _resolve_seen_path() -> Path:
    """Resolve the gmail_seen.json path for the *current* request scope.

    Consults :func:`taskforce.application.infrastructure_overrides.get_butler_state_dir_override`
    at write-time so a process-shared tool instance can still route
    per-(tenant, user). Falls back to ``.taskforce/butler/gmail_seen.json``
    when no override is installed (single-user dev / standalone).

    The override may raise — for example when the resolver runs
    before tenant context is bound. We swallow the error and fall
    back to the default rather than corrupting the dedup state with
    an exception during a routine email check; the override emits
    its own log line in that case.
    """
    try:
        from taskforce.application.infrastructure_overrides import (
            get_butler_state_dir_override,
        )

        override = get_butler_state_dir_override()
        if override is not None:
            base = override()
            if base is not None:
                return Path(base) / _SEEN_FILE_NAME
    except Exception:  # pragma: no cover — defensive
        logger.warning(
            "butler.email.seen_path_override_failed",
            exc_info=True,
        )
    return _DEFAULT_BUTLER_DIR / _SEEN_FILE_NAME


class GmailTool(BaseTool):
    """Tool for reading and sending Gmail messages.

    Supports listing, reading, sending, and drafting messages.
    Requires Google OAuth credentials with gmail.send scope.
    """

    tool_name = "gmail"
    tool_description = (
        "Gmail email tool. Actions: list (search/list emails), "
        "read (get full email content by ID), labels (list all Gmail labels/folders), "
        "send (send an email), draft (create a draft without sending). "
        "Use labels to discover folders, then list with a query to find messages. "
        "For periodic checks, use since_last_check=true with list to only "
        "see emails that haven't been reported yet."
    )
    tool_parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "read", "labels", "send", "draft"],
                "description": "Gmail action: list, read, labels, send, or draft",
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
            "since_last_check": {
                "type": "boolean",
                "description": (
                    "Only return messages not seen in a previous call (for list). "
                    "Use this for periodic scheduled checks to avoid duplicates."
                ),
            },
            "message_id": {
                "type": "string",
                "description": "Message ID (required for read action)",
            },
            "to": {
                "type": "string",
                "description": "Recipient email address (required for send/draft)",
            },
            "subject": {
                "type": "string",
                "description": "Email subject line (required for send/draft)",
            },
            "body": {
                "type": "string",
                "description": "Email body text (required for send/draft)",
            },
            "cc": {
                "type": "string",
                "description": "CC recipients (comma-separated, optional)",
            },
        },
        "required": ["action"],
    }
    tool_requires_approval = False
    tool_approval_risk_level = ApprovalRiskLevel.LOW
    tool_supports_parallelism = True

    def __init__(self, auth_manager: AuthManagerProtocol | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._auth_manager = auth_manager

    async def _execute(self, **kwargs: Any) -> dict[str, Any]:
        """Execute a Gmail action."""
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError:
            return {
                "success": False,
                "error": (
                    "Google API not available. Run: uv sync"
                ),
            }

        action = kwargs.get("action")
        valid_actions = ("list", "read", "labels", "send", "draft")
        if action not in valid_actions:
            return {"success": False, "error": f"action must be one of: {', '.join(valid_actions)}"}

        try:
            service = await _build_service_async(build, Credentials, self._auth_manager)

            if action == "labels":
                return await _list_labels(service)
            if action == "list":
                return await _list_messages(service, kwargs)
            if action == "send":
                return await _send_message(service, kwargs)
            if action == "draft":
                return await _create_draft(service, kwargs)
            return await _read_message(service, kwargs)
        except Exception as exc:
            return tool_error_payload(ToolError(f"gmail failed: {exc}", tool_name="gmail"))

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        action = kwargs.get("action")
        valid_actions = ("list", "read", "labels", "send", "draft")
        if action not in valid_actions:
            return False, f"action must be one of: {', '.join(valid_actions)}"
        if action == "read" and not kwargs.get("message_id"):
            return False, "message_id is required for read action"
        if action in ("send", "draft"):
            if not kwargs.get("to"):
                return False, "'to' is required for send/draft"
            if not kwargs.get("subject"):
                return False, "'subject' is required for send/draft"
            if not kwargs.get("body"):
                return False, "'body' is required for send/draft"
        return True, None

    @property
    def requires_approval(self) -> bool:
        """Send/draft require approval, read operations don't."""
        return False

    def approval_risk_level_for(self, **kwargs: Any) -> ApprovalRiskLevel:
        """Return HIGH risk for send (actually sends email), LOW for read ops."""
        action = kwargs.get("action", "")
        if action == "send":
            return ApprovalRiskLevel.HIGH
        if action == "draft":
            return ApprovalRiskLevel.MEDIUM
        return ApprovalRiskLevel.LOW


async def _build_service_async(build: Any, credentials_cls: Any, auth_manager: Any = None) -> Any:
    """Build Gmail API service, preferring AuthManager if available."""
    if auth_manager:
        token = await auth_manager.get_token("google")
        if token:
            creds = credentials_cls.from_authorized_user_info(
                {
                    "token": token.access_token,
                    "refresh_token": token.refresh_token,
                    "token_uri": token.token_uri,
                    "client_id": token.client_id,
                    "client_secret": token.client_secret,
                }
            )
            return build("gmail", "v1", credentials=creds)
    # 2. Fall back to legacy token file (~/.taskforce/google_token.json).
    try:
        return _build_service(build, credentials_cls)
    except Exception as legacy_exc:
        raise ValueError(
            "Google authentication expired or revoked. "
            "The user needs to re-run 'python scripts/google_auth.py' to refresh the token. "
            "Tell the user about this and do NOT retry — manual action is required."
        ) from legacy_exc


def _build_service(build: Any, credentials_cls: Any) -> Any:
    """Build Gmail API service using the shared OAuth token (legacy)."""
    import json
    from pathlib import Path

    from google.auth.transport.requests import Request

    token_path = Path.home() / ".taskforce" / "google_token.json"
    if not token_path.exists():
        raise ValueError("No credentials found. Run 'python scripts/google_auth.py' first.")

    with open(token_path, encoding="utf-8") as f:
        creds_data = json.load(f)

    creds = credentials_cls.from_authorized_user_info(creds_data)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)


async def _list_labels(service: Any) -> dict[str, Any]:
    """List all Gmail labels (folders/categories)."""
    result = await asyncio.to_thread(lambda: service.users().labels().list(userId="me").execute())
    labels = []
    for label in result.get("labels", []):
        labels.append(
            {
                "id": label["id"],
                "name": label["name"],
                "type": label.get("type", ""),
            }
        )
    labels.sort(key=lambda lbl: lbl["name"])
    return {"success": True, "labels": labels, "count": len(labels)}


async def _list_messages(service: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """List Gmail messages matching a search query.

    When ``since_last_check`` is *True*, previously reported message IDs
    are filtered out and the current set is persisted so the next call
    only returns genuinely new messages.
    """
    query = kwargs.get("query", "")
    max_results = min(int(kwargs.get("max_results", 10)), 25)
    since_last_check = bool(kwargs.get("since_last_check", False))

    result = await asyncio.to_thread(
        lambda: service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )

    message_refs = result.get("messages", [])
    if not message_refs:
        return {
            "success": True,
            "messages": [],
            "count": 0,
            "query": query,
            "since_last_check": since_last_check,
        }

    # --- dedup filtering ---
    seen_ids: set[str] = set()
    if since_last_check:
        seen_ids = _load_seen_ids()
        message_refs = [m for m in message_refs if m["id"] not in seen_ids]
        if not message_refs:
            return {
                "success": True,
                "messages": [],
                "count": 0,
                "query": query,
                "since_last_check": True,
                "info": "No new messages since last check.",
            }

    # Fetch snippet/headers for each message for useful preview.
    messages = []
    for msg_ref in message_refs[:max_results]:
        msg = await asyncio.to_thread(
            lambda mid=msg_ref["id"]: service.users()
            .messages()
            .get(
                userId="me", id=mid, format="metadata", metadataHeaders=["From", "Subject", "Date"]
            )
            .execute()
        )
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        messages.append(
            {
                "id": msg["id"],
                "snippet": msg.get("snippet", ""),
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "labels": msg.get("labelIds", []),
            }
        )

    # --- persist seen IDs ---
    if since_last_check:
        new_ids = {m["id"] for m in messages}
        _save_seen_ids(seen_ids | new_ids)

    return {
        "success": True,
        "messages": messages,
        "count": len(messages),
        "query": query,
        "since_last_check": since_last_check,
    }


# ---------------------------------------------------------------------------
# Seen-ID persistence (simple JSON file)
# ---------------------------------------------------------------------------


def _load_seen_ids(path: Path | None = None) -> set[str]:
    """Load previously seen message IDs from disk.

    When ``path`` is ``None`` the active per-scope path is resolved
    via :func:`_resolve_seen_path` (enterprise plugins route this
    per-(tenant, user); standalone falls back to ``.taskforce/butler/``).
    Tests can still pass an explicit path to pin the location.
    """
    p = path or _resolve_seen_path()
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return set(data.get("seen_ids", []))
    except Exception:
        return set()


def _save_seen_ids(ids: set[str], path: Path | None = None) -> None:
    """Persist seen message IDs to disk, pruning if necessary."""
    p = path or _resolve_seen_path()
    # Prune to cap — keep the most recent IDs (arbitrary, but bounded).
    id_list = list(ids)
    if len(id_list) > _MAX_SEEN_IDS:
        id_list = id_list[-_MAX_SEEN_IDS:]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"seen_ids": id_list}), encoding="utf-8")


async def _read_message(service: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Read a single Gmail message by ID."""
    message_id = kwargs["message_id"]

    msg = await asyncio.to_thread(
        lambda: service.users().messages().get(userId="me", id=message_id, format="full").execute()
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


def _build_email_message(kwargs: dict[str, Any]) -> str:
    """Build an RFC 2822 email message from parameters."""
    from email.mime.text import MIMEText

    msg = MIMEText(kwargs["body"], "plain", "utf-8")
    msg["To"] = kwargs["to"]
    msg["Subject"] = kwargs["subject"]
    if kwargs.get("cc"):
        msg["Cc"] = kwargs["cc"]
    return msg.as_string()


async def _send_message(service: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Send an email via Gmail API."""
    raw_message = _build_email_message(kwargs)
    encoded = base64.urlsafe_b64encode(raw_message.encode("utf-8")).decode("ascii")

    result = await asyncio.to_thread(
        lambda: service.users()
        .messages()
        .send(userId="me", body={"raw": encoded})
        .execute()
    )

    return {
        "success": True,
        "message_id": result.get("id", ""),
        "to": kwargs["to"],
        "subject": kwargs["subject"],
        "info": "Email sent successfully.",
    }


async def _create_draft(service: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Create a draft email in Gmail without sending."""
    raw_message = _build_email_message(kwargs)
    encoded = base64.urlsafe_b64encode(raw_message.encode("utf-8")).decode("ascii")

    result = await asyncio.to_thread(
        lambda: service.users()
        .drafts()
        .create(userId="me", body={"message": {"raw": encoded}})
        .execute()
    )

    return {
        "success": True,
        "draft_id": result.get("id", ""),
        "to": kwargs["to"],
        "subject": kwargs["subject"],
        "info": "Draft created. Open Gmail to review and send.",
    }
