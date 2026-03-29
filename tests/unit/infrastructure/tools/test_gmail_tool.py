"""Tests for GmailTool — send, draft, and since_last_check dedup."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskforce.infrastructure.tools.native.email_tool import (
    GmailTool,
    _build_email_message,
    _load_seen_ids,
    _save_seen_ids,
)


class TestBuildEmailMessage:
    """Tests for email RFC 2822 message construction."""

    def test_basic_message(self):
        msg = _build_email_message({
            "to": "test@example.com",
            "subject": "Hello",
            "body": "World",
        })
        assert "To: test@example.com" in msg
        assert "Subject: Hello" in msg
        # Body is base64-encoded by MIMEText
        assert "text/plain" in msg

    def test_message_with_cc(self):
        msg = _build_email_message({
            "to": "a@b.com",
            "subject": "Test",
            "body": "Body",
            "cc": "c@d.com, e@f.com",
        })
        assert "Cc: c@d.com, e@f.com" in msg

    def test_message_without_cc(self):
        msg = _build_email_message({
            "to": "a@b.com",
            "subject": "Test",
            "body": "Body",
        })
        assert "Cc:" not in msg

    def test_unicode_body(self):
        msg = _build_email_message({
            "to": "a@b.com",
            "subject": "Ümlaute",
            "body": "Grüße aus Österreich",
        })
        assert "a@b.com" in msg


class TestGmailToolValidation:
    """Tests for parameter validation."""

    def test_validate_send_requires_to(self):
        tool = GmailTool()
        ok, err = tool.validate_params(action="send", subject="Hi", body="Test")
        assert not ok
        assert "to" in err

    def test_validate_send_requires_subject(self):
        tool = GmailTool()
        ok, err = tool.validate_params(action="send", to="a@b.com", body="Test")
        assert not ok
        assert "subject" in err

    def test_validate_send_requires_body(self):
        tool = GmailTool()
        ok, err = tool.validate_params(action="send", to="a@b.com", subject="Hi")
        assert not ok
        assert "body" in err

    def test_validate_send_all_params(self):
        tool = GmailTool()
        ok, err = tool.validate_params(action="send", to="a@b.com", subject="Hi", body="Test")
        assert ok
        assert err is None

    def test_validate_draft_same_as_send(self):
        tool = GmailTool()
        ok, err = tool.validate_params(action="draft", to="a@b.com", subject="Hi", body="Test")
        assert ok

    def test_validate_read_still_works(self):
        tool = GmailTool()
        ok, err = tool.validate_params(action="read", message_id="abc123")
        assert ok

    def test_validate_list_still_works(self):
        tool = GmailTool()
        ok, err = tool.validate_params(action="list")
        assert ok


# ---------------------------------------------------------------------------
# Seen-ID persistence tests
# ---------------------------------------------------------------------------


class TestSeenIdPersistence:
    """Tests for the since_last_check dedup mechanism."""

    def test_load_returns_empty_when_no_file(self, tmp_path: Path) -> None:
        assert _load_seen_ids(tmp_path / "nope.json") == set()

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        p = tmp_path / "seen.json"
        ids = {"msg_1", "msg_2", "msg_3"}
        _save_seen_ids(ids, p)
        loaded = _load_seen_ids(p)
        assert loaded == ids

    def test_save_prunes_beyond_max(self, tmp_path: Path) -> None:
        p = tmp_path / "seen.json"
        big_set = {f"msg_{i}" for i in range(1000)}
        _save_seen_ids(big_set, p)
        loaded = _load_seen_ids(p)
        assert len(loaded) == 500  # _MAX_SEEN_IDS

    def test_load_handles_corrupt_file(self, tmp_path: Path) -> None:
        p = tmp_path / "seen.json"
        p.write_text("not json!", encoding="utf-8")
        assert _load_seen_ids(p) == set()

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        p = tmp_path / "sub" / "dir" / "seen.json"
        _save_seen_ids({"msg_1"}, p)
        assert p.exists()
        assert _load_seen_ids(p) == {"msg_1"}


# ---------------------------------------------------------------------------
# Integration-style test for _list_messages with since_last_check
# ---------------------------------------------------------------------------


def _mock_gmail_service(message_ids: list[str]) -> MagicMock:
    """Build a mock Gmail service that returns given message IDs."""
    service = MagicMock()

    # messages().list().execute()
    list_result = {"messages": [{"id": mid} for mid in message_ids]}
    service.users().messages().list().execute.return_value = list_result

    # messages().get().execute() — return minimal metadata per message
    def _get_side_effect(userId: str = "me", id: str = "", **kw: object) -> MagicMock:
        m = MagicMock()
        m.execute.return_value = {
            "id": id,
            "snippet": f"snippet for {id}",
            "labelIds": ["UNREAD"],
            "payload": {
                "headers": [
                    {"name": "From", "value": f"sender-{id}@example.com"},
                    {"name": "Subject", "value": f"Subject {id}"},
                    {"name": "Date", "value": "Sat, 29 Mar 2026 10:00:00 +0000"},
                ]
            },
        }
        return m

    service.users().messages().get.side_effect = _get_side_effect
    return service


class TestListMessagesSinceLastCheck:
    """Tests for the since_last_check dedup in _list_messages."""

    @patch("taskforce.infrastructure.tools.native.email_tool._DEFAULT_SEEN_PATH")
    async def test_first_call_returns_all_and_persists(self, mock_path: MagicMock, tmp_path: Path) -> None:
        from taskforce.infrastructure.tools.native.email_tool import _list_messages

        seen_path = tmp_path / "seen.json"
        with patch("taskforce.infrastructure.tools.native.email_tool._DEFAULT_SEEN_PATH", seen_path):
            service = _mock_gmail_service(["msg_a", "msg_b"])
            result = await _list_messages(service, {"query": "is:unread", "since_last_check": True})

        assert result["count"] == 2
        assert result["since_last_check"] is True
        # IDs should now be persisted
        persisted = _load_seen_ids(seen_path)
        assert "msg_a" in persisted
        assert "msg_b" in persisted

    @patch("taskforce.infrastructure.tools.native.email_tool._DEFAULT_SEEN_PATH")
    async def test_second_call_filters_seen(self, mock_path: MagicMock, tmp_path: Path) -> None:
        from taskforce.infrastructure.tools.native.email_tool import _list_messages

        seen_path = tmp_path / "seen.json"
        with patch("taskforce.infrastructure.tools.native.email_tool._DEFAULT_SEEN_PATH", seen_path):
            # First call — sees msg_a, msg_b
            service = _mock_gmail_service(["msg_a", "msg_b"])
            await _list_messages(service, {"query": "is:unread", "since_last_check": True})

            # Second call — msg_b still there, msg_c is new
            service = _mock_gmail_service(["msg_b", "msg_c"])
            result = await _list_messages(service, {"query": "is:unread", "since_last_check": True})

        assert result["count"] == 1
        assert result["messages"][0]["id"] == "msg_c"

    @patch("taskforce.infrastructure.tools.native.email_tool._DEFAULT_SEEN_PATH")
    async def test_no_new_messages_returns_empty(self, mock_path: MagicMock, tmp_path: Path) -> None:
        from taskforce.infrastructure.tools.native.email_tool import _list_messages

        seen_path = tmp_path / "seen.json"
        with patch("taskforce.infrastructure.tools.native.email_tool._DEFAULT_SEEN_PATH", seen_path):
            service = _mock_gmail_service(["msg_a"])
            await _list_messages(service, {"query": "is:unread", "since_last_check": True})

            # Same messages again
            service = _mock_gmail_service(["msg_a"])
            result = await _list_messages(service, {"query": "is:unread", "since_last_check": True})

        assert result["count"] == 0
        assert "No new messages" in result.get("info", "")

    async def test_without_flag_returns_all_every_time(self) -> None:
        from taskforce.infrastructure.tools.native.email_tool import _list_messages

        service = _mock_gmail_service(["msg_x"])
        result = await _list_messages(service, {"query": "is:unread"})
        assert result["count"] == 1
        assert result.get("since_last_check") is False
