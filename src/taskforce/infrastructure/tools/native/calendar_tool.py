"""Calendar tool for interacting with Google Calendar.

Provides list, create, update, delete operations for calendar events,
plus list_calendars to discover available calendars.
Promoted from the examples/personal_assistant to a native tool.
"""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING, Any

import structlog

from taskforce.core.domain.errors import ToolError, tool_error_payload
from taskforce.core.interfaces.tools import ApprovalRiskLevel

if TYPE_CHECKING:
    from taskforce.core.interfaces.auth import AuthManagerProtocol

logger = structlog.get_logger(__name__)


class CalendarTool:
    """Tool for interacting with Google Calendar.

    Supports listing upcoming events and creating new events.
    Requires Google Calendar API credentials.
    """

    def __init__(
        self,
        credentials_file: str | None = None,
        auth_manager: AuthManagerProtocol | None = None,
    ) -> None:
        self._credentials_file = credentials_file
        self._auth_manager = auth_manager

    @property
    def name(self) -> str:
        return "calendar"

    @property
    def description(self) -> str:
        return (
            "Interact with Google Calendar. "
            "Actions: list_calendars (discover available calendars), "
            "list (show upcoming events), create (create a new event), "
            "update (modify an existing event), delete (remove an event). "
            "Use calendar_id to target a specific calendar (default: 'primary'). "
            "Requires Google Calendar API credentials."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list_calendars", "list", "create", "update", "delete"],
                    "description": "Calendar action to perform",
                },
                "event_id": {
                    "type": "string",
                    "description": "Event ID (required for update and delete)",
                },
                "calendar_id": {
                    "type": "string",
                    "description": "Calendar ID (default: 'primary')",
                },
                "time_min": {
                    "type": "string",
                    "description": "ISO 8601 start time for listing events",
                },
                "time_max": {
                    "type": "string",
                    "description": "ISO 8601 end time for listing events",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of events to return (default: 10)",
                },
                "title": {
                    "type": "string",
                    "description": "Event title (for create)",
                },
                "start": {
                    "type": "string",
                    "description": "ISO 8601 start time (for create)",
                },
                "end": {
                    "type": "string",
                    "description": "ISO 8601 end time (for create)",
                },
                "description": {
                    "type": "string",
                    "description": "Event description (for create)",
                },
                "location": {
                    "type": "string",
                    "description": "Event location (for create)",
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
        action = kwargs.get("action", "")
        title = kwargs.get("title", "")
        return f"Tool: {self.name}\nOperation: {action}\nEvent: {title}"

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Execute a calendar action."""
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError:
            return {
                "success": False,
                "error": (
                    "Google Calendar API not available. Install with: "
                    "pip install google-api-python-client google-auth"
                ),
            }

        action = kwargs.pop("action", None)
        try:
            service = await self._build_service_async(build, Credentials)
            calendar_id = kwargs.pop("calendar_id", "primary")

            if action == "list_calendars":
                return await self._list_calendars(service)
            if action == "list":
                return await self._list_events(service, calendar_id, **kwargs)
            if action == "create":
                return await self._create_event(service, calendar_id, **kwargs)
            if action == "update":
                return await self._update_event(service, calendar_id, **kwargs)
            if action == "delete":
                return await self._delete_event(service, calendar_id, **kwargs)
            return {"success": False, "error": f"Unknown action: {action}"}
        except Exception as exc:
            return tool_error_payload(ToolError(f"{self.name} failed: {exc}", tool_name=self.name))

    async def _build_service_async(self, build: Any, credentials_cls: Any) -> Any:
        """Build the Google Calendar API service with auth_manager support.

        Tries the AuthManager first (if available), then falls back to
        the legacy file-based credential loading.
        """
        if self._auth_manager:
            token = await self._auth_manager.get_token("google")
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
                return build("calendar", "v3", credentials=creds)
        return self._build_service(build, credentials_cls)

    def _build_service(self, build: Any, credentials_cls: Any) -> Any:
        """Build the Google Calendar API service (legacy file-based).

        Looks for an OAuth token file (result of the authorization flow)
        at ``~/.taskforce/google_token.json`` first, then falls back to
        the legacy ``google_credentials.json`` location.
        """
        import json
        from pathlib import Path

        from google.auth.transport.requests import Request

        # Preferred: token file from OAuth flow.
        token_path = Path.home() / ".taskforce" / "google_token.json"
        creds_file = self._credentials_file

        if token_path.exists() and not creds_file:
            creds_file = str(token_path)
        elif not creds_file:
            legacy_path = Path.home() / ".taskforce" / "google_credentials.json"
            if legacy_path.exists():
                creds_file = str(legacy_path)
            else:
                raise ValueError(
                    "No credentials found. Run 'python scripts/google_auth.py' first, "
                    "or place a token file at ~/.taskforce/google_token.json"
                )

        creds_path = Path(creds_file)
        if not creds_path.exists():
            raise FileNotFoundError(f"Credentials file not found: {creds_path}")

        with open(creds_path) as f:
            creds_data = json.load(f)

        creds = credentials_cls.from_authorized_user_info(creds_data)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return build("calendar", "v3", credentials=creds)

    async def _list_events(self, service: Any, calendar_id: str, **kwargs: Any) -> dict[str, Any]:
        """List upcoming calendar events."""
        import asyncio
        from datetime import datetime

        time_min = kwargs.get("time_min", datetime.now(UTC).isoformat())
        time_max = kwargs.get("time_max")
        max_results = int(kwargs.get("max_results", 10))

        request_kwargs: dict[str, Any] = {
            "calendarId": calendar_id,
            "timeMin": time_min,
            "singleEvents": True,
            "orderBy": "startTime",
            "maxResults": max_results,
        }
        if time_max:
            request_kwargs["timeMax"] = time_max

        result = await asyncio.to_thread(lambda: service.events().list(**request_kwargs).execute())

        events = []
        for item in result.get("items", []):
            events.append(
                {
                    "id": item.get("id", ""),
                    "title": item.get("summary", ""),
                    "start": item.get("start", {}).get(
                        "dateTime", item.get("start", {}).get("date", "")
                    ),
                    "end": item.get("end", {}).get("dateTime", item.get("end", {}).get("date", "")),
                    "location": item.get("location", ""),
                    "description": item.get("description", ""),
                }
            )

        return {"success": True, "events": events, "count": len(events)}

    async def _create_event(self, service: Any, calendar_id: str, **kwargs: Any) -> dict[str, Any]:
        """Create a new calendar event."""
        import asyncio

        title = kwargs.get("title", "")
        start = kwargs.get("start", "")
        end = kwargs.get("end", "")

        if not title or not start or not end:
            return {
                "success": False,
                "error": "title, start, and end are required for creating events",
            }

        event_body: dict[str, Any] = {
            "summary": title,
            "start": {"dateTime": start},
            "end": {"dateTime": end},
        }
        if kwargs.get("description"):
            event_body["description"] = kwargs["description"]
        if kwargs.get("location"):
            event_body["location"] = kwargs["location"]

        created = await asyncio.to_thread(
            lambda: service.events().insert(calendarId=calendar_id, body=event_body).execute()
        )

        return {
            "success": True,
            "event_id": created.get("id", ""),
            "html_link": created.get("htmlLink", ""),
            "message": f"Event '{title}' created",
        }

    async def _list_calendars(self, service: Any) -> dict[str, Any]:
        """List all available calendars for the authenticated user."""
        import asyncio

        result = await asyncio.to_thread(lambda: service.calendarList().list().execute())

        calendars = []
        for item in result.get("items", []):
            calendars.append(
                {
                    "id": item.get("id", ""),
                    "summary": item.get("summary", ""),
                    "description": item.get("description", ""),
                    "primary": item.get("primary", False),
                    "access_role": item.get("accessRole", ""),
                }
            )

        return {"success": True, "calendars": calendars, "count": len(calendars)}

    async def _update_event(self, service: Any, calendar_id: str, **kwargs: Any) -> dict[str, Any]:
        """Update an existing calendar event."""
        import asyncio

        event_id = kwargs.get("event_id", "")
        if not event_id:
            return {"success": False, "error": "event_id is required for update"}

        # Fetch existing event first
        existing = await asyncio.to_thread(
            lambda: service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        )

        # Apply updates
        if kwargs.get("title"):
            existing["summary"] = kwargs["title"]
        if kwargs.get("start"):
            existing["start"] = {"dateTime": kwargs["start"]}
        if kwargs.get("end"):
            existing["end"] = {"dateTime": kwargs["end"]}
        if kwargs.get("description"):
            existing["description"] = kwargs["description"]
        if kwargs.get("location"):
            existing["location"] = kwargs["location"]

        updated = await asyncio.to_thread(
            lambda: service.events()
            .update(calendarId=calendar_id, eventId=event_id, body=existing)
            .execute()
        )

        return {
            "success": True,
            "event_id": updated.get("id", ""),
            "html_link": updated.get("htmlLink", ""),
            "message": f"Event '{updated.get('summary', '')}' updated",
        }

    async def _delete_event(self, service: Any, calendar_id: str, **kwargs: Any) -> dict[str, Any]:
        """Delete a calendar event."""
        import asyncio

        event_id = kwargs.get("event_id", "")
        if not event_id:
            return {"success": False, "error": "event_id is required for delete"}

        await asyncio.to_thread(
            lambda: service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        )

        return {
            "success": True,
            "message": f"Event '{event_id}' deleted",
        }

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters."""
        action = kwargs.get("action")
        valid_actions = ("list_calendars", "list", "create", "update", "delete")
        if action not in valid_actions:
            return False, f"action must be one of {valid_actions}"
        if action == "create":
            for field in ("title", "start", "end"):
                if not kwargs.get(field):
                    return False, f"Missing required parameter: {field}"
        if action in ("update", "delete"):
            if not kwargs.get("event_id"):
                return False, "event_id is required for update/delete"
        return True, None
