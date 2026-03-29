"""Tests for GmailTool — send and draft actions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskforce.infrastructure.tools.native.email_tool import (
    GmailTool,
    _build_email_message,
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
