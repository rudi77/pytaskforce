"""Calendar event source that polls Google Calendar for upcoming events.

Detects upcoming events and publishes AgentEvents when events are
within the configured lookahead window.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from taskforce.core.domain.agent_event import AgentEvent, AgentEventType
from taskforce.core.utils.time import utc_now
from taskforce.infrastructure.event_sources.base import PollingEventSource

logger = structlog.get_logger(__name__)


class CalendarEventSource(PollingEventSource):
    """Polls Google Calendar API for upcoming events.

    Requires either an OAuth2 credentials file or an access token.
    Falls back to a no-op if google-api-python-client is not installed.

    Configuration (via butler profile YAML)::

        event_sources:
          - type: calendar
            provider: google
            poll_interval_minutes: 5
            lookahead_minutes: 60
            calendar_id: primary
            credentials_file: ~/.taskforce/google_credentials.json
    """

    def __init__(
        self,
        poll_interval_seconds: float = 300.0,
        lookahead_minutes: int = 60,
        calendar_id: str = "primary",
        credentials_file: str | None = None,
        event_callback: Callable[[AgentEvent], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__(
            source_name="calendar",
            poll_interval_seconds=poll_interval_seconds,
            event_callback=event_callback,
        )
        self._lookahead = timedelta(minutes=lookahead_minutes)
        self._calendar_id = calendar_id
        self._credentials_file = credentials_file
        self._seen_event_ids: set[str] = set()

    async def _poll_once(self) -> list[AgentEvent]:
        """Poll Google Calendar for upcoming events."""
        try:
            from google.oauth2.credentials import Credentials  # type: ignore[import-not-found]
            from googleapiclient.discovery import build  # type: ignore[import-not-found]
        except ImportError:
            logger.debug(
                "calendar_source.google_api_not_installed",
                hint="Install google-api-python-client and google-auth for calendar support",
            )
            return []

        try:
            service = self._build_service(build, Credentials)
            return await self._fetch_upcoming_events(service)
        except Exception as exc:
            logger.warning("calendar_source.poll_failed", error=str(exc))
            return []

    def _build_service(self, build: Any, credentials_cls: Any) -> Any:
        """Build the Google Calendar API service."""
        import json
        from pathlib import Path

        if not self._credentials_file:
            raise ValueError("No credentials_file configured for calendar source")

        creds_path = Path(self._credentials_file)
        if not creds_path.exists():
            raise FileNotFoundError(f"Credentials file not found: {creds_path}")

        with open(creds_path) as f:
            creds_data = json.load(f)

        creds = credentials_cls.from_authorized_user_info(creds_data)
        return build("calendar", "v3", credentials=creds)

    async def _fetch_upcoming_events(self, service: Any) -> list[AgentEvent]:
        """Fetch upcoming events and convert to AgentEvents."""
        import asyncio

        now = utc_now()
        time_min = now.isoformat()
        time_max = (now + self._lookahead).isoformat()

        result = await asyncio.to_thread(
            lambda: service.events()
            .list(
                calendarId=self._calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        agent_events: list[AgentEvent] = []
        for item in result.get("items", []):
            event_id = item.get("id", "")
            if event_id in self._seen_event_ids:
                continue
            self._seen_event_ids.add(event_id)

            start_str = item.get("start", {}).get("dateTime", item.get("start", {}).get("date", ""))
            if start_str:
                start_time = datetime.fromisoformat(start_str)
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=UTC)
                minutes_until = max(0, (start_time - now).total_seconds() / 60)
            else:
                minutes_until = -1

            agent_events.append(
                AgentEvent(
                    source="calendar",
                    event_type=AgentEventType.CALENDAR_UPCOMING,
                    payload={
                        "calendar_event_id": event_id,
                        "title": item.get("summary", ""),
                        "description": item.get("description", ""),
                        "start": start_str,
                        "end": item.get("end", {}).get(
                            "dateTime", item.get("end", {}).get("date", "")
                        ),
                        "location": item.get("location", ""),
                        "minutes_until": round(minutes_until, 1),
                        "attendees": [a.get("email", "") for a in item.get("attendees", [])],
                    },
                    metadata={
                        "calendar_id": self._calendar_id,
                        "html_link": item.get("htmlLink", ""),
                    },
                )
            )

        if agent_events:
            logger.info(
                "calendar_source.events_found",
                count=len(agent_events),
                calendar_id=self._calendar_id,
            )

        return agent_events

    def clear_seen(self) -> None:
        """Reset the seen event cache (useful for testing)."""
        self._seen_event_ids.clear()
