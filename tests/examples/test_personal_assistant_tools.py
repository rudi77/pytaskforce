"""Tests for personal assistant tool validation helpers."""

from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
sys.path.append(str(root / "examples" / "personal_assistant"))

from personal_assistant.tools.calendar_tools import (  # noqa: E402
    GoogleCalendarTool,
)
from personal_assistant.tools.email_tools import (  # noqa: E402
    GmailTool,
    _encode_message,
)


def test_gmail_tool_validate_list_action() -> None:
    tool = GmailTool()
    ok, error = tool.validate_params(action="list")
    assert ok
    assert error is None


def test_gmail_tool_validate_send_requires_fields() -> None:
    tool = GmailTool()
    ok, error = tool.validate_params(
        action="send",
        to=["a@example.com"],
        subject="",
        body="hi",
    )
    assert not ok
    assert error is not None


def test_google_calendar_tool_validate_create() -> None:
    tool = GoogleCalendarTool()
    ok, error = tool.validate_params(
        action="create",
        title="Sync",
        start="2025-01-01T10:00:00Z",
        end="2025-01-01T11:00:00Z",
    )
    assert ok
    assert error is None


def test_encode_message_returns_string() -> None:
    encoded = _encode_message(to=["a@example.com"], subject="Hi", body="Hello")
    assert isinstance(encoded, str)
    assert encoded
