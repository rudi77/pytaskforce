"""Calendar tool for interacting with Google Calendar.

Provides list and create operations for calendar events.
Promoted from the examples/personal_assistant to a native tool.
"""

from __future__ import annotations

from datetime import UTC
from typing import Any

import structlog

from taskforce.core.domain.errors import ToolError, tool_error_payload
from taskforce.core.interfaces.tools import ApprovalRiskLevel

logger = structlog.get_logger(__name__)


class CalendarTool:
    """Tool for interacting with Google Calendar.

    Supports listing upcoming events and creating new events.
    Requires Google Calendar API credentials.
    """

    def __init__(self, credentials_file: str | None = None) -> None:
        self._credentials_file = credentials_file

    @property
    def name(self) -> str:
        return "calendar"

    @property
    def description(self) -> str:
        return (
            "Interact with Google Calendar. List upcoming events or create new ones. "
            "Actions: list (show upcoming events), create (create a new event). "
            "Requires Google Calendar API credentials."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "create"],
                    "description": "Calendar action to perform",
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
            from google.oauth2.credentials import Credentials  # type: ignore[import-not-found]
            from googleapiclient.discovery import build  # type: ignore[import-not-found]
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
            service = self._build_service(build, Credentials)
            calendar_id = kwargs.pop("calendar_id", "primary")

            if action == "list":
                return await self._list_events(service, calendar_id, **kwargs)
            if action == "create":
                return await self._create_event(service, calendar_id, **kwargs)
            return {"success": False, "error": f"Unknown action: {action}"}
        except Exception as exc:
            return tool_error_payload(ToolError(f"{self.name} failed: {exc}", tool_name=self.name))

    def _build_service(self, build: Any, credentials_cls: Any) -> Any:
        """Build the Google Calendar API service."""
        import json
        from pathlib import Path

        creds_file = self._credentials_file
        if not creds_file:
            # Try default location
            default_path = Path.home() / ".taskforce" / "google_credentials.json"
            if default_path.exists():
                creds_file = str(default_path)
            else:
                raise ValueError(
                    "No credentials_file configured. Set the credentials_file parameter "
                    "or place credentials at ~/.taskforce/google_credentials.json"
                )

        creds_path = Path(creds_file)
        if not creds_path.exists():
            raise FileNotFoundError(f"Credentials file not found: {creds_path}")

        with open(creds_path) as f:
            creds_data = json.load(f)

        creds = credentials_cls.from_authorized_user_info(creds_data)
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

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters."""
        action = kwargs.get("action")
        if action not in ("list", "create"):
            return False, "action must be 'list' or 'create'"
        if action == "create":
            for field in ("title", "start", "end"):
                if not kwargs.get(field):
                    return False, f"Missing required parameter: {field}"
        return True, None
