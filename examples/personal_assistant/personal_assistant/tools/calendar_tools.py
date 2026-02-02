"""Google Calendar tool for the personal assistant plugin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from personal_assistant.tools.tool_base import ApprovalRiskLevel


CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]


@dataclass(frozen=True)
class CalendarAuthConfig:
    """Authentication inputs for Google Calendar API usage."""

    access_token: str | None
    token_file: str | None


class GoogleCalendarTool:
    """Interact with Google Calendar using the Google API."""

    @property
    def name(self) -> str:
        return "google_calendar"

    @property
    def description(self) -> str:
        return (
            "List or create calendar events. Actions: list, create. "
            "Requires OAuth credentials."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "create"]},
                "calendar_id": {"type": "string", "description": "Calendar ID"},
                "time_min": {"type": "string", "description": "ISO start time"},
                "time_max": {"type": "string", "description": "ISO end time"},
                "max_results": {"type": "integer"},
                "title": {"type": "string"},
                "start": {"type": "string", "description": "ISO start time"},
                "end": {"type": "string", "description": "ISO end time"},
                "location": {"type": "string"},
                "attendees": {"type": "array", "items": {"type": "string"}},
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
        if action not in {"list", "create"}:
            return False, "action must be one of: list, create"
        if action == "create":
            return _validate_create_fields(kwargs)
        return True, None

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        action = kwargs["action"]
        auth = CalendarAuthConfig(
            access_token=kwargs.get("access_token"),
            token_file=kwargs.get("token_file"),
        )
        service = _build_calendar_service(auth)
        calendar_id = kwargs.get("calendar_id", "primary")
        if action == "list":
            return _list_events(service, calendar_id, kwargs)
        return _create_event(service, calendar_id, kwargs)


def _build_calendar_service(auth: CalendarAuthConfig):
    """Build a Google Calendar API client from provided credentials."""
    from googleapiclient.discovery import build

    credentials = _load_credentials(auth)
    return build("calendar", "v3", credentials=credentials)


def _load_credentials(auth: CalendarAuthConfig):
    """Load OAuth credentials from token, token file, or environment variables.

    Priority order:
    1. access_token parameter
    2. token_file parameter
    3. GOOGLE_ACCESS_TOKEN environment variable
    4. GOOGLE_TOKEN_FILE environment variable
    """
    import os

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    access_token = auth.access_token or os.environ.get("GOOGLE_ACCESS_TOKEN")
    token_file = auth.token_file or os.environ.get("GOOGLE_TOKEN_FILE")

    if access_token:
        # Pure access token - no refresh possible
        return Credentials(token=access_token, scopes=CALENDAR_SCOPES)
    elif token_file:
        creds = Credentials.from_authorized_user_file(token_file, CALENDAR_SCOPES)
        # Only refresh if we have the necessary fields (from token_file)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return creds
    else:
        raise ValueError(
            "Provide access_token or token_file for GoogleCalendarTool, "
            "or set GOOGLE_ACCESS_TOKEN / GOOGLE_TOKEN_FILE environment variables"
        )


def _list_events(service: Any, calendar_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """List Google Calendar events in a time range."""
    response = service.events().list(
        calendarId=calendar_id,
        timeMin=payload.get("time_min"),
        timeMax=payload.get("time_max"),
        maxResults=payload.get("max_results", 10),
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return {"success": True, "events": response.get("items", [])}


def _create_event(service: Any, calendar_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Create a Google Calendar event."""
    event_body = {
        "summary": payload["title"],
        "start": {"dateTime": payload["start"]},
        "end": {"dateTime": payload["end"]},
        "location": payload.get("location"),
        "attendees": _format_attendees(payload.get("attendees")),
    }
    event = service.events().insert(calendarId=calendar_id, body=event_body).execute()
    return {"success": True, "event": event}


def _format_attendees(attendees: list[str] | None) -> list[dict[str, str]]:
    """Format attendee emails for the Google Calendar API."""
    if not attendees:
        return []
    return [{"email": attendee} for attendee in attendees]


def _validate_create_fields(payload: dict[str, Any]) -> tuple[bool, str | None]:
    """Validate fields required for create action."""
    for field in ("title", "start", "end"):
        if not isinstance(payload.get(field), str) or not payload.get(field):
            return False, f"{field} must be a non-empty string"
    return True, None
