"""Tests for GmailTool.

Covers tool metadata properties, parameter validation, execute with mocked
Gmail API responses, and error handling for missing credentials,
unknown actions, and API failures.
"""

from __future__ import annotations

import base64
import sys
import types
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.tools.native.gmail_tool import GmailTool


@pytest.fixture(autouse=True)
def _mock_google_libs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure google.oauth2.credentials and googleapiclient.discovery are importable."""
    google = types.ModuleType("google")
    google_auth = types.ModuleType("google.auth")
    google_auth_transport = types.ModuleType("google.auth.transport")
    google_auth_transport_requests = types.ModuleType("google.auth.transport.requests")
    google_auth_transport_requests.Request = MagicMock()  # type: ignore[attr-defined]
    oauth2 = types.ModuleType("google.oauth2")
    credentials = types.ModuleType("google.oauth2.credentials")
    credentials.Credentials = MagicMock()  # type: ignore[attr-defined]
    google.oauth2 = oauth2  # type: ignore[attr-defined]
    google.auth = google_auth  # type: ignore[attr-defined]
    oauth2.credentials = credentials  # type: ignore[attr-defined]
    google_auth.transport = google_auth_transport  # type: ignore[attr-defined]
    google_auth_transport.requests = google_auth_transport_requests  # type: ignore[attr-defined]

    googleapiclient = types.ModuleType("googleapiclient")
    discovery = types.ModuleType("googleapiclient.discovery")
    discovery.build = MagicMock()  # type: ignore[attr-defined]
    googleapiclient.discovery = discovery  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", google_auth)
    monkeypatch.setitem(sys.modules, "google.auth.transport", google_auth_transport)
    monkeypatch.setitem(sys.modules, "google.auth.transport.requests", google_auth_transport_requests)
    monkeypatch.setitem(sys.modules, "google.oauth2", oauth2)
    monkeypatch.setitem(sys.modules, "google.oauth2.credentials", credentials)
    monkeypatch.setitem(sys.modules, "googleapiclient", googleapiclient)
    monkeypatch.setitem(sys.modules, "googleapiclient.discovery", discovery)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_list_response(
    messages: list[dict[str, Any]] | None = None,
    result_size: int = 0,
) -> dict[str, Any]:
    return {
        "messages": messages or [],
        "resultSizeEstimate": result_size,
    }


def _fake_message(
    message_id: str = "msg1",
    thread_id: str = "thread1",
    subject: str = "Hello",
    from_addr: str = "alice@example.com",
    to_addr: str = "bob@example.com",
    body_text: str = "Hi there!",
    snippet: str = "Hi there!",
    labels: list[str] | None = None,
) -> dict[str, Any]:
    body_data = base64.urlsafe_b64encode(body_text.encode()).decode()
    return {
        "id": message_id,
        "threadId": thread_id,
        "snippet": snippet,
        "labelIds": labels or ["INBOX"],
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": from_addr},
                {"name": "To", "value": to_addr},
                {"name": "Date", "value": "Mon, 23 Feb 2026 09:00:00 +0000"},
            ],
            "body": {"data": body_data},
        },
    }


def _build_mock_service(
    list_response: dict[str, Any] | None = None,
    get_response: dict[str, Any] | None = None,
    draft_response: dict[str, Any] | None = None,
    send_response: dict[str, Any] | None = None,
) -> MagicMock:
    """Create a mock Gmail API service object."""
    service = MagicMock()

    # users().messages().list().execute()
    list_execute = MagicMock(return_value=list_response or _fake_list_response())
    service.users.return_value.messages.return_value.list.return_value.execute = list_execute

    # users().messages().get().execute()
    get_execute = MagicMock(return_value=get_response or _fake_message())
    service.users.return_value.messages.return_value.get.return_value.execute = get_execute

    # users().drafts().create().execute()
    draft_execute = MagicMock(return_value=draft_response or {"id": "draft1"})
    service.users.return_value.drafts.return_value.create.return_value.execute = draft_execute

    # users().messages().send().execute()
    send_execute = MagicMock(
        return_value=send_response or {"id": "sent1", "threadId": "thread_sent1"}
    )
    service.users.return_value.messages.return_value.send.return_value.execute = send_execute

    return service


# ---------------------------------------------------------------------------
# Metadata / Properties
# ---------------------------------------------------------------------------


class TestGmailToolProperties:
    """Tests for GmailTool metadata and static properties."""

    @pytest.fixture
    def tool(self) -> GmailTool:
        return GmailTool()

    def test_name(self, tool: GmailTool) -> None:
        assert tool.name == "gmail"

    def test_description_mentions_gmail(self, tool: GmailTool) -> None:
        assert "gmail" in tool.description.lower()

    def test_description_mentions_actions(self, tool: GmailTool) -> None:
        desc = tool.description.lower()
        assert "list" in desc
        assert "read" in desc
        assert "draft" in desc
        assert "send" in desc

    def test_parameters_schema_is_object(self, tool: GmailTool) -> None:
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "action" in schema["properties"]
        assert "action" in schema["required"]

    def test_parameters_schema_action_enum(self, tool: GmailTool) -> None:
        action_prop = tool.parameters_schema["properties"]["action"]
        assert set(action_prop["enum"]) == {"list", "read", "draft", "send"}

    def test_parameters_schema_has_expected_keys(self, tool: GmailTool) -> None:
        props = tool.parameters_schema["properties"]
        expected = {
            "action", "user_id", "query", "label_ids", "page_size",
            "message_id", "to", "subject", "body",
        }
        assert expected == set(props.keys())

    def test_requires_approval(self, tool: GmailTool) -> None:
        assert tool.requires_approval is True

    def test_approval_risk_level(self, tool: GmailTool) -> None:
        assert tool.approval_risk_level == ApprovalRiskLevel.MEDIUM

    def test_supports_parallelism(self, tool: GmailTool) -> None:
        assert tool.supports_parallelism is True

    def test_get_approval_preview_send(self, tool: GmailTool) -> None:
        preview = tool.get_approval_preview(
            action="send", subject="Hello", to=["bob@example.com"]
        )
        assert "gmail" in preview
        assert "send" in preview
        assert "Hello" in preview
        assert "bob@example.com" in preview

    def test_get_approval_preview_list(self, tool: GmailTool) -> None:
        preview = tool.get_approval_preview(action="list")
        assert "list" in preview

    def test_default_credentials_file_is_none(self) -> None:
        tool = GmailTool()
        assert tool._credentials_file is None

    def test_custom_credentials_file(self) -> None:
        tool = GmailTool(credentials_file="/path/to/creds.json")
        assert tool._credentials_file == "/path/to/creds.json"


# ---------------------------------------------------------------------------
# Validate Params
# ---------------------------------------------------------------------------


class TestGmailToolValidateParams:
    """Tests for GmailTool.validate_params."""

    @pytest.fixture
    def tool(self) -> GmailTool:
        return GmailTool()

    def test_valid_list_action(self, tool: GmailTool) -> None:
        valid, error = tool.validate_params(action="list")
        assert valid is True
        assert error is None

    def test_valid_read_action(self, tool: GmailTool) -> None:
        valid, error = tool.validate_params(action="read", message_id="msg1")
        assert valid is True
        assert error is None

    def test_valid_draft_action(self, tool: GmailTool) -> None:
        valid, error = tool.validate_params(
            action="draft",
            to=["bob@example.com"],
            subject="Test",
            body="Hello",
        )
        assert valid is True
        assert error is None

    def test_valid_send_action(self, tool: GmailTool) -> None:
        valid, error = tool.validate_params(
            action="send",
            to=["bob@example.com"],
            subject="Test",
            body="Hello",
        )
        assert valid is True
        assert error is None

    def test_invalid_action(self, tool: GmailTool) -> None:
        valid, error = tool.validate_params(action="delete")
        assert valid is False
        assert error is not None

    def test_read_missing_message_id(self, tool: GmailTool) -> None:
        valid, error = tool.validate_params(action="read")
        assert valid is False
        assert "message_id" in error

    def test_draft_missing_to(self, tool: GmailTool) -> None:
        valid, error = tool.validate_params(
            action="draft", subject="Test", body="Hello"
        )
        assert valid is False
        assert "to" in error

    def test_send_missing_subject(self, tool: GmailTool) -> None:
        valid, error = tool.validate_params(
            action="send", to=["bob@example.com"], body="Hello"
        )
        assert valid is False
        assert "subject" in error

    def test_send_missing_body(self, tool: GmailTool) -> None:
        valid, error = tool.validate_params(
            action="send", to=["bob@example.com"], subject="Test"
        )
        assert valid is False
        assert "body" in error

    def test_send_empty_to_list(self, tool: GmailTool) -> None:
        valid, error = tool.validate_params(
            action="send", to=[], subject="Test", body="Hello"
        )
        assert valid is False
        assert "to" in error

    def test_list_with_optional_params(self, tool: GmailTool) -> None:
        valid, error = tool.validate_params(
            action="list", query="is:unread", page_size=5
        )
        assert valid is True
        assert error is None


# ---------------------------------------------------------------------------
# Execute - Google API Not Installed
# ---------------------------------------------------------------------------


class TestGmailToolMissingDependency:
    """Tests for GmailTool when google-api-python-client is missing."""

    async def test_import_error_returns_graceful_failure(self) -> None:
        tool = GmailTool()

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
# Execute - List Messages
# ---------------------------------------------------------------------------


class TestGmailToolListMessages:
    """Tests for listing Gmail messages with a mocked Gmail API service."""

    @pytest.fixture
    def mock_service(self) -> MagicMock:
        messages = [{"id": "msg1", "threadId": "t1"}, {"id": "msg2", "threadId": "t2"}]
        return _build_mock_service(
            list_response=_fake_list_response(messages=messages, result_size=2)
        )

    async def test_list_messages_success(self, mock_service: MagicMock) -> None:
        tool = GmailTool(credentials_file="/fake/creds.json")
        tool._build_service = MagicMock(return_value=mock_service)

        result = await tool.execute(action="list")

        assert result["success"] is True
        assert result["count"] == 2
        assert result["result_size_estimate"] == 2

    async def test_list_messages_empty(self) -> None:
        mock_service = _build_mock_service(list_response=_fake_list_response())
        tool = GmailTool(credentials_file="/fake/creds.json")
        tool._build_service = MagicMock(return_value=mock_service)

        result = await tool.execute(action="list")

        assert result["success"] is True
        assert result["count"] == 0

    async def test_list_messages_with_query(self, mock_service: MagicMock) -> None:
        tool = GmailTool(credentials_file="/fake/creds.json")
        tool._build_service = MagicMock(return_value=mock_service)

        result = await tool.execute(action="list", query="is:unread", page_size=5)

        assert result["success"] is True


# ---------------------------------------------------------------------------
# Execute - Read Message
# ---------------------------------------------------------------------------


class TestGmailToolReadMessage:
    """Tests for reading a Gmail message with a mocked Gmail API service."""

    async def test_read_message_success(self) -> None:
        msg = _fake_message(
            message_id="msg1",
            subject="Test Subject",
            from_addr="alice@example.com",
            body_text="Hello World",
        )
        mock_service = _build_mock_service(get_response=msg)
        tool = GmailTool(credentials_file="/fake/creds.json")
        tool._build_service = MagicMock(return_value=mock_service)

        result = await tool.execute(action="read", message_id="msg1")

        assert result["success"] is True
        assert result["message_id"] == "msg1"
        assert result["subject"] == "Test Subject"
        assert result["from"] == "alice@example.com"
        assert result["body"] == "Hello World"

    async def test_read_message_multipart(self) -> None:
        """Reading a multipart message extracts text/plain part."""
        body_data = base64.urlsafe_b64encode(b"Plain text body").decode()
        msg = {
            "id": "msg2",
            "threadId": "t2",
            "snippet": "Plain text...",
            "labelIds": ["INBOX"],
            "payload": {
                "mimeType": "multipart/alternative",
                "headers": [
                    {"name": "Subject", "value": "Multipart"},
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "To", "value": "recipient@example.com"},
                ],
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {"data": body_data},
                    },
                    {
                        "mimeType": "text/html",
                        "body": {"data": base64.urlsafe_b64encode(b"<p>HTML</p>").decode()},
                    },
                ],
            },
        }
        mock_service = _build_mock_service(get_response=msg)
        tool = GmailTool(credentials_file="/fake/creds.json")
        tool._build_service = MagicMock(return_value=mock_service)

        result = await tool.execute(action="read", message_id="msg2")

        assert result["success"] is True
        assert result["body"] == "Plain text body"


# ---------------------------------------------------------------------------
# Execute - Draft
# ---------------------------------------------------------------------------


class TestGmailToolDraft:
    """Tests for creating Gmail drafts."""

    async def test_create_draft_success(self) -> None:
        mock_service = _build_mock_service(draft_response={"id": "draft_123"})
        tool = GmailTool(credentials_file="/fake/creds.json")
        tool._build_service = MagicMock(return_value=mock_service)

        result = await tool.execute(
            action="draft",
            to=["bob@example.com"],
            subject="Test Draft",
            body="Draft content",
        )

        assert result["success"] is True
        assert result["draft_id"] == "draft_123"
        assert "Test Draft" in result["message"]


# ---------------------------------------------------------------------------
# Execute - Send
# ---------------------------------------------------------------------------


class TestGmailToolSend:
    """Tests for sending Gmail messages."""

    async def test_send_message_success(self) -> None:
        mock_service = _build_mock_service(
            send_response={"id": "sent_1", "threadId": "thread_sent_1"}
        )
        tool = GmailTool(credentials_file="/fake/creds.json")
        tool._build_service = MagicMock(return_value=mock_service)

        result = await tool.execute(
            action="send",
            to=["bob@example.com"],
            subject="Hello Bob",
            body="Hi there!",
        )

        assert result["success"] is True
        assert result["message_id"] == "sent_1"
        assert "bob@example.com" in result["message"]


# ---------------------------------------------------------------------------
# Execute - Error Handling
# ---------------------------------------------------------------------------


class TestGmailToolErrorHandling:
    """Tests for error handling in GmailTool.execute."""

    async def test_unknown_action(self) -> None:
        tool = GmailTool(credentials_file="/fake/creds.json")
        mock_service = _build_mock_service()
        tool._build_service = MagicMock(return_value=mock_service)

        result = await tool.execute(action="archive")

        assert result["success"] is False

    async def test_build_service_raises(self) -> None:
        tool = GmailTool(credentials_file="/fake/creds.json")
        tool._build_service = MagicMock(side_effect=ValueError("Bad credentials"))

        result = await tool.execute(action="list")

        assert result["success"] is False
        assert "Bad credentials" in str(result.get("error", ""))

    async def test_service_api_error_on_list(self) -> None:
        mock_service = _build_mock_service()
        mock_service.users.return_value.messages.return_value.list.return_value.execute.side_effect = (
            RuntimeError("API quota exceeded")
        )
        tool = GmailTool(credentials_file="/fake/creds.json")
        tool._build_service = MagicMock(return_value=mock_service)

        result = await tool.execute(action="list")

        assert result["success"] is False

    async def test_service_api_error_on_send(self) -> None:
        mock_service = _build_mock_service()
        mock_service.users.return_value.messages.return_value.send.return_value.execute.side_effect = (
            RuntimeError("Insufficient permissions")
        )
        tool = GmailTool(credentials_file="/fake/creds.json")
        tool._build_service = MagicMock(return_value=mock_service)

        result = await tool.execute(
            action="send",
            to=["bob@example.com"],
            subject="Test",
            body="Hello",
        )

        assert result["success"] is False

    async def test_credentials_file_not_found(self) -> None:
        tool = GmailTool(credentials_file="/nonexistent/path/creds.json")

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
                        m.Credentials = MagicMock()
                        return m
                    if name == "googleapiclient.discovery":
                        m = MagicMock()
                        m.build = MagicMock()
                        return m
                    return original_import(name, *args, **kwargs)

                with patch("builtins.__import__", side_effect=_safe_import):
                    result = await tool.execute(action="list")

        assert result["success"] is False
