"""Tests for CalendarTool.

Covers tool metadata properties, parameter validation, execute with mocked
Google Calendar responses, and error handling for missing credentials,
unknown actions, and API failures.
"""

from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.tools.native.calendar_tool import CalendarTool


@pytest.fixture(autouse=True)
def _mock_google_libs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure google.oauth2.credentials and googleapiclient.discovery are importable."""
    google = types.ModuleType("google")
    oauth2 = types.ModuleType("google.oauth2")
    credentials = types.ModuleType("google.oauth2.credentials")
    credentials.Credentials = MagicMock()  # type: ignore[attr-defined]
    google.oauth2 = oauth2  # type: ignore[attr-defined]
    oauth2.credentials = credentials  # type: ignore[attr-defined]

    googleapiclient = types.ModuleType("googleapiclient")
    discovery = types.ModuleType("googleapiclient.discovery")
    discovery.build = MagicMock()  # type: ignore[attr-defined]
    googleapiclient.discovery = discovery  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.oauth2", oauth2)
    monkeypatch.setitem(sys.modules, "google.oauth2.credentials", credentials)
    monkeypatch.setitem(sys.modules, "googleapiclient", googleapiclient)
    monkeypatch.setitem(sys.modules, "googleapiclient.discovery", discovery)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_events_list_response(items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build a fake Google Calendar events().list().execute() response."""
    return {"items": items or []}


def _fake_event_item(
    event_id: str = "evt1",
    summary: str = "Team Standup",
    start_dt: str = "2026-02-23T09:00:00Z",
    end_dt: str = "2026-02-23T09:30:00Z",
    location: str = "",
    description: str = "",
) -> dict[str, Any]:
    return {
        "id": event_id,
        "summary": summary,
        "start": {"dateTime": start_dt},
        "end": {"dateTime": end_dt},
        "location": location,
        "description": description,
    }


def _fake_insert_response(
    event_id: str = "created1",
    html_link: str = "https://calendar.google.com/event/created1",
) -> dict[str, Any]:
    return {"id": event_id, "htmlLink": html_link}


def _build_mock_service(
    list_response: dict[str, Any] | None = None,
    insert_response: dict[str, Any] | None = None,
) -> MagicMock:
    """Create a mock Google Calendar API service object."""
    service = MagicMock()

    # events().list(**kwargs).execute() chain
    list_execute = MagicMock(return_value=list_response or _fake_events_list_response())
    list_call = MagicMock()
    list_call.execute = list_execute
    service.events.return_value.list.return_value = list_call

    # events().insert(calendarId=..., body=...).execute() chain
    insert_execute = MagicMock(return_value=insert_response or _fake_insert_response())
    insert_call = MagicMock()
    insert_call.execute = insert_execute
    service.events.return_value.insert.return_value = insert_call

    return service


# ---------------------------------------------------------------------------
# Metadata / Properties
# ---------------------------------------------------------------------------


class TestCalendarToolProperties:
    """Tests for CalendarTool metadata and static properties."""

    @pytest.fixture
    def tool(self) -> CalendarTool:
        return CalendarTool()

    def test_name(self, tool: CalendarTool) -> None:
        assert tool.name == "calendar"

    def test_description_mentions_calendar(self, tool: CalendarTool) -> None:
        assert "calendar" in tool.description.lower()

    def test_description_mentions_actions(self, tool: CalendarTool) -> None:
        desc = tool.description.lower()
        assert "list" in desc
        assert "create" in desc

    def test_parameters_schema_is_object(self, tool: CalendarTool) -> None:
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "action" in schema["properties"]
        assert "action" in schema["required"]

    def test_parameters_schema_action_enum(self, tool: CalendarTool) -> None:
        action_prop = tool.parameters_schema["properties"]["action"]
        assert set(action_prop["enum"]) == {"list", "create"}

    def test_parameters_schema_has_expected_keys(self, tool: CalendarTool) -> None:
        props = tool.parameters_schema["properties"]
        expected = {
            "action", "calendar_id", "time_min", "time_max", "max_results",
            "title", "start", "end", "description", "location",
        }
        assert expected == set(props.keys())

    def test_requires_approval(self, tool: CalendarTool) -> None:
        assert tool.requires_approval is True

    def test_approval_risk_level(self, tool: CalendarTool) -> None:
        assert tool.approval_risk_level == ApprovalRiskLevel.MEDIUM

    def test_supports_parallelism(self, tool: CalendarTool) -> None:
        assert tool.supports_parallelism is True

    def test_get_approval_preview(self, tool: CalendarTool) -> None:
        preview = tool.get_approval_preview(action="create", title="Meeting")
        assert "calendar" in preview
        assert "create" in preview
        assert "Meeting" in preview

    def test_get_approval_preview_list(self, tool: CalendarTool) -> None:
        preview = tool.get_approval_preview(action="list")
        assert "list" in preview

    def test_default_credentials_file_is_none(self) -> None:
        tool = CalendarTool()
        assert tool._credentials_file is None

    def test_custom_credentials_file(self) -> None:
        tool = CalendarTool(credentials_file="/path/to/creds.json")
        assert tool._credentials_file == "/path/to/creds.json"


# ---------------------------------------------------------------------------
# Validate Params
# ---------------------------------------------------------------------------


class TestCalendarToolValidateParams:
    """Tests for CalendarTool.validate_params."""

    @pytest.fixture
    def tool(self) -> CalendarTool:
        return CalendarTool()

    def test_valid_list_action(self, tool: CalendarTool) -> None:
        valid, error = tool.validate_params(action="list")
        assert valid is True
        assert error is None

    def test_valid_create_action(self, tool: CalendarTool) -> None:
        valid, error = tool.validate_params(
            action="create",
            title="Meeting",
            start="2026-02-23T09:00:00",
            end="2026-02-23T10:00:00",
        )
        assert valid is True
        assert error is None

    def test_invalid_action(self, tool: CalendarTool) -> None:
        valid, error = tool.validate_params(action="delete")
        assert valid is False
        assert error is not None

    def test_create_missing_title(self, tool: CalendarTool) -> None:
        valid, error = tool.validate_params(
            action="create", start="2026-02-23T09:00:00", end="2026-02-23T10:00:00"
        )
        assert valid is False
        assert "title" in error

    def test_create_missing_start(self, tool: CalendarTool) -> None:
        valid, error = tool.validate_params(
            action="create", title="Meeting", end="2026-02-23T10:00:00"
        )
        assert valid is False
        assert "start" in error

    def test_create_missing_end(self, tool: CalendarTool) -> None:
        valid, error = tool.validate_params(
            action="create", title="Meeting", start="2026-02-23T09:00:00"
        )
        assert valid is False
        assert "end" in error

    def test_list_with_optional_params(self, tool: CalendarTool) -> None:
        valid, error = tool.validate_params(
            action="list", time_min="2026-02-23T00:00:00Z", max_results=5
        )
        assert valid is True
        assert error is None


# ---------------------------------------------------------------------------
# Execute - Google API Not Installed
# ---------------------------------------------------------------------------


class TestCalendarToolMissingDependency:
    """Tests for CalendarTool when google-api-python-client is missing."""

    async def test_import_error_returns_graceful_failure(self) -> None:
        """When google packages are not installed, return a helpful error."""
        tool = CalendarTool()

        # Patch the google imports to simulate ImportError
        with patch.dict("sys.modules", {"google": None, "google.oauth2": None}):
            import builtins

            original_import = builtins.__import__

            def _import_raiser(name: str, *args: Any, **kwargs: Any) -> Any:
                if name.startswith("google"):
                    raise ImportError(f"No module named '{name}'")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=_import_raiser):
                result = await tool.execute(action="list")

        assert result["success"] is False
        assert "not available" in result["error"].lower() or "install" in result["error"].lower()


# ---------------------------------------------------------------------------
# Execute - List Events
# ---------------------------------------------------------------------------


class TestCalendarToolListEvents:
    """Tests for listing calendar events with a mocked Google API service."""

    @pytest.fixture
    def mock_service(self) -> MagicMock:
        items = [
            _fake_event_item(
                event_id="e1",
                summary="Standup",
                start_dt="2026-02-23T09:00:00Z",
                end_dt="2026-02-23T09:30:00Z",
            ),
            _fake_event_item(
                event_id="e2",
                summary="Lunch",
                start_dt="2026-02-23T12:00:00Z",
                end_dt="2026-02-23T13:00:00Z",
                location="Cafeteria",
            ),
        ]
        return _build_mock_service(list_response=_fake_events_list_response(items))

    async def test_list_events_success(self, mock_service: MagicMock) -> None:
        tool = CalendarTool(credentials_file="/fake/creds.json")
        tool._build_service = MagicMock(return_value=mock_service)

        result = await tool.execute(action="list")

        assert result["success"] is True
        assert result["count"] == 2
        assert result["events"][0]["title"] == "Standup"
        assert result["events"][1]["location"] == "Cafeteria"

    async def test_list_events_empty(self) -> None:
        mock_service = _build_mock_service(list_response=_fake_events_list_response([]))
        tool = CalendarTool(credentials_file="/fake/creds.json")
        tool._build_service = MagicMock(return_value=mock_service)

        result = await tool.execute(action="list")

        assert result["success"] is True
        assert result["count"] == 0
        assert result["events"] == []

    async def test_list_events_with_time_range(self, mock_service: MagicMock) -> None:
        tool = CalendarTool(credentials_file="/fake/creds.json")
        tool._build_service = MagicMock(return_value=mock_service)

        result = await tool.execute(
            action="list",
            time_min="2026-02-23T00:00:00Z",
            time_max="2026-02-23T23:59:59Z",
            max_results=5,
        )

        assert result["success"] is True

    async def test_list_events_custom_calendar_id(
        self, mock_service: MagicMock
    ) -> None:
        """Passing calendar_id selects the correct calendar for listing."""
        tool = CalendarTool(credentials_file="/fake/creds.json")
        tool._build_service = MagicMock(return_value=mock_service)

        result = await tool.execute(action="list", calendar_id="work@group.calendar.google.com")

        assert result["success"] is True

    async def test_list_events_extracts_date_only_events(self) -> None:
        """Events with date-only (all-day) fields should also be handled."""
        items = [
            {
                "id": "allday1",
                "summary": "Holiday",
                "start": {"date": "2026-02-24"},
                "end": {"date": "2026-02-25"},
            }
        ]
        mock_service = _build_mock_service(list_response=_fake_events_list_response(items))
        tool = CalendarTool(credentials_file="/fake/creds.json")
        tool._build_service = MagicMock(return_value=mock_service)

        result = await tool.execute(action="list")

        assert result["success"] is True
        assert result["count"] == 1
        assert result["events"][0]["start"] == "2026-02-24"
        assert result["events"][0]["end"] == "2026-02-25"


# ---------------------------------------------------------------------------
# Execute - Create Event
# ---------------------------------------------------------------------------


class TestCalendarToolCreateEvent:
    """Tests for creating calendar events with a mocked Google API service."""

    @pytest.fixture
    def mock_service(self) -> MagicMock:
        return _build_mock_service(
            insert_response=_fake_insert_response(event_id="new1", html_link="https://cal/new1")
        )

    async def test_create_event_success(self, mock_service: MagicMock) -> None:
        tool = CalendarTool(credentials_file="/fake/creds.json")
        tool._build_service = MagicMock(return_value=mock_service)

        result = await tool.execute(
            action="create",
            title="Sprint Planning",
            start="2026-02-24T10:00:00Z",
            end="2026-02-24T11:00:00Z",
            description="Plan the next sprint",
            location="Room 42",
        )

        assert result["success"] is True
        assert result["event_id"] == "new1"
        assert result["html_link"] == "https://cal/new1"
        assert "Sprint Planning" in result["message"]

    async def test_create_event_minimal(self, mock_service: MagicMock) -> None:
        """Creating an event with just title, start, and end (no description/location)."""
        tool = CalendarTool(credentials_file="/fake/creds.json")
        tool._build_service = MagicMock(return_value=mock_service)

        result = await tool.execute(
            action="create",
            title="Quick Sync",
            start="2026-02-24T14:00:00Z",
            end="2026-02-24T14:30:00Z",
        )

        assert result["success"] is True
        assert result["event_id"] == "new1"

    async def test_create_event_missing_title(self, mock_service: MagicMock) -> None:
        tool = CalendarTool(credentials_file="/fake/creds.json")
        tool._build_service = MagicMock(return_value=mock_service)

        result = await tool.execute(
            action="create",
            start="2026-02-24T10:00:00Z",
            end="2026-02-24T11:00:00Z",
        )

        assert result["success"] is False
        assert "required" in result["error"].lower()

    async def test_create_event_missing_start(self, mock_service: MagicMock) -> None:
        tool = CalendarTool(credentials_file="/fake/creds.json")
        tool._build_service = MagicMock(return_value=mock_service)

        result = await tool.execute(
            action="create",
            title="Meeting",
            end="2026-02-24T11:00:00Z",
        )

        assert result["success"] is False

    async def test_create_event_missing_end(self, mock_service: MagicMock) -> None:
        tool = CalendarTool(credentials_file="/fake/creds.json")
        tool._build_service = MagicMock(return_value=mock_service)

        result = await tool.execute(
            action="create",
            title="Meeting",
            start="2026-02-24T10:00:00Z",
        )

        assert result["success"] is False


# ---------------------------------------------------------------------------
# Execute - Error Handling
# ---------------------------------------------------------------------------


class TestCalendarToolErrorHandling:
    """Tests for error handling in CalendarTool.execute."""

    async def test_unknown_action(self) -> None:
        tool = CalendarTool(credentials_file="/fake/creds.json")
        mock_service = _build_mock_service()
        tool._build_service = MagicMock(return_value=mock_service)

        result = await tool.execute(action="delete")

        assert result["success"] is False
        assert "unknown" in result["error"].lower() or "Unknown" in result["error"]

    async def test_build_service_raises(self) -> None:
        tool = CalendarTool(credentials_file="/fake/creds.json")
        tool._build_service = MagicMock(side_effect=ValueError("Bad credentials"))

        result = await tool.execute(action="list")

        assert result["success"] is False
        assert "Bad credentials" in str(result.get("error", ""))

    async def test_service_api_error_on_list(self) -> None:
        mock_service = _build_mock_service()
        mock_service.events.return_value.list.return_value.execute.side_effect = RuntimeError(
            "API quota exceeded"
        )
        tool = CalendarTool(credentials_file="/fake/creds.json")
        tool._build_service = MagicMock(return_value=mock_service)

        result = await tool.execute(action="list")

        assert result["success"] is False

    async def test_service_api_error_on_create(self) -> None:
        mock_service = _build_mock_service()
        mock_service.events.return_value.insert.return_value.execute.side_effect = RuntimeError(
            "Insufficient permissions"
        )
        tool = CalendarTool(credentials_file="/fake/creds.json")
        tool._build_service = MagicMock(return_value=mock_service)

        result = await tool.execute(
            action="create",
            title="Test",
            start="2026-02-24T10:00:00Z",
            end="2026-02-24T11:00:00Z",
        )

        assert result["success"] is False

    async def test_credentials_file_not_found(self) -> None:
        """Test that missing credentials file is handled gracefully."""
        tool = CalendarTool(credentials_file="/nonexistent/path/creds.json")

        mock_build = MagicMock()
        mock_creds = MagicMock()

        with patch.object(
            tool,
            "_build_service",
            side_effect=FileNotFoundError(
                "Credentials file not found: /nonexistent/path/creds.json"
            ),
        ):
            with patch.dict(
                "sys.modules",
                {
                    "google": MagicMock(),
                    "google.oauth2": MagicMock(),
                    "google.oauth2.credentials": MagicMock(),
                    "googleapiclient": MagicMock(),
                    "googleapiclient.discovery": MagicMock(),
                },
            ):
                import builtins

                original_import = builtins.__import__

                def _safe_import(name: str, *args: Any, **kwargs: Any) -> Any:
                    if name == "google.oauth2.credentials":
                        m = MagicMock()
                        m.Credentials = mock_creds
                        return m
                    if name == "googleapiclient.discovery":
                        m = MagicMock()
                        m.build = mock_build
                        return m
                    return original_import(name, *args, **kwargs)

                with patch("builtins.__import__", side_effect=_safe_import):
                    result = await tool.execute(action="list")

        assert result["success"] is False
