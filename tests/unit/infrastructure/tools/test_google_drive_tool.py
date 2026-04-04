"""Tests for GoogleDriveTool.

Covers tool metadata properties, parameter validation, all 8 actions
with mocked Google Drive responses, and error handling for missing
credentials, unknown actions, and API failures.
"""

from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.tools.native.google_drive_tool import GoogleDriveTool


@pytest.fixture(autouse=True)
def _mock_google_libs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure google.oauth2.credentials and googleapiclient are importable."""
    google = types.ModuleType("google")
    google_auth = types.ModuleType("google.auth")
    google_auth_transport = types.ModuleType("google.auth.transport")
    google_auth_transport_requests = types.ModuleType("google.auth.transport.requests")
    google_auth_transport_requests.Request = MagicMock()  # type: ignore[attr-defined]
    google_auth_transport.requests = google_auth_transport_requests  # type: ignore[attr-defined]
    google_auth.transport = google_auth_transport  # type: ignore[attr-defined]

    oauth2 = types.ModuleType("google.oauth2")
    credentials = types.ModuleType("google.oauth2.credentials")
    credentials.Credentials = MagicMock()  # type: ignore[attr-defined]
    google.oauth2 = oauth2  # type: ignore[attr-defined]
    google.auth = google_auth  # type: ignore[attr-defined]
    oauth2.credentials = credentials  # type: ignore[attr-defined]

    googleapiclient = types.ModuleType("googleapiclient")
    discovery = types.ModuleType("googleapiclient.discovery")
    discovery.build = MagicMock()  # type: ignore[attr-defined]
    googleapiclient.discovery = discovery  # type: ignore[attr-defined]

    http_mod = types.ModuleType("googleapiclient.http")
    http_mod.MediaInMemoryUpload = MagicMock()  # type: ignore[attr-defined]
    googleapiclient.http = http_mod  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", google_auth)
    monkeypatch.setitem(sys.modules, "google.auth.transport", google_auth_transport)
    monkeypatch.setitem(
        sys.modules, "google.auth.transport.requests", google_auth_transport_requests
    )
    monkeypatch.setitem(sys.modules, "google.oauth2", oauth2)
    monkeypatch.setitem(sys.modules, "google.oauth2.credentials", credentials)
    monkeypatch.setitem(sys.modules, "googleapiclient", googleapiclient)
    monkeypatch.setitem(sys.modules, "googleapiclient.discovery", discovery)
    monkeypatch.setitem(sys.modules, "googleapiclient.http", http_mod)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_file_item(
    file_id: str = "file1",
    name: str = "report.txt",
    mime_type: str = "text/plain",
    modified_time: str = "2026-03-20T10:00:00Z",
    size: str = "1024",
) -> dict[str, Any]:
    return {
        "id": file_id,
        "name": name,
        "mimeType": mime_type,
        "modifiedTime": modified_time,
        "size": size,
    }


def _fake_list_response(items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"files": items or []}


def _build_mock_service(
    list_response: dict[str, Any] | None = None,
    get_response: dict[str, Any] | None = None,
    get_media_response: bytes | None = None,
    export_response: bytes | None = None,
    create_response: dict[str, Any] | None = None,
    update_response: dict[str, Any] | None = None,
) -> MagicMock:
    """Build a mock Drive service with chainable method calls."""
    service = MagicMock()

    # files().list().execute()
    service.files().list().execute.return_value = list_response or _fake_list_response()

    # files().get(fileId=..., fields=...).execute()
    service.files().get().execute.return_value = get_response or _fake_file_item()

    # files().get_media(fileId=...).execute()
    service.files().get_media().execute.return_value = get_media_response or b"file content"

    # files().export(fileId=..., mimeType=...).execute()
    service.files().export().execute.return_value = export_response or b"exported content"

    # files().create(body=..., media_body=..., fields=...).execute()
    service.files().create().execute.return_value = create_response or {
        "id": "new1",
        "name": "test.txt",
        "mimeType": "text/plain",
        "webViewLink": "https://drive.google.com/file/d/new1",
    }

    # files().update(fileId=..., body=..., media_body=..., fields=...).execute()
    service.files().update().execute.return_value = update_response or {
        "id": "file1",
        "name": "updated.txt",
        "mimeType": "text/plain",
    }

    # files().delete(fileId=...).execute()
    service.files().delete().execute.return_value = None

    return service


# ---------------------------------------------------------------------------
# Metadata tests
# ---------------------------------------------------------------------------


class TestGoogleDriveToolProperties:
    """Test tool metadata properties."""

    def test_name(self):
        tool = GoogleDriveTool()
        assert tool.name == "google_drive"

    def test_description_mentions_drive(self):
        tool = GoogleDriveTool()
        assert "Drive" in tool.description

    def test_schema_has_all_actions(self):
        tool = GoogleDriveTool()
        actions = tool.parameters_schema["properties"]["action"]["enum"]
        expected = [
            "list",
            "get",
            "download",
            "upload",
            "update",
            "delete",
            "create_folder",
            "search",
        ]
        assert actions == expected

    def test_requires_approval(self):
        tool = GoogleDriveTool()
        assert tool.requires_approval is True

    def test_approval_risk_level(self):
        tool = GoogleDriveTool()
        assert tool.approval_risk_level == ApprovalRiskLevel.MEDIUM

    def test_supports_parallelism(self):
        tool = GoogleDriveTool()
        assert tool.supports_parallelism is True

    def test_approval_preview(self):
        tool = GoogleDriveTool()
        preview = tool.get_approval_preview(action="upload", name="report.txt")
        assert "upload" in preview
        assert "report.txt" in preview


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


class TestGoogleDriveToolValidation:
    """Test parameter validation."""

    def test_valid_list(self):
        tool = GoogleDriveTool()
        ok, err = tool.validate_params(action="list")
        assert ok is True
        assert err is None

    def test_valid_search(self):
        tool = GoogleDriveTool()
        ok, err = tool.validate_params(action="search", query="name contains 'x'")
        assert ok is True

    def test_invalid_action(self):
        tool = GoogleDriveTool()
        ok, err = tool.validate_params(action="invalid")
        assert ok is False
        assert "action must be" in err

    def test_get_requires_file_id(self):
        tool = GoogleDriveTool()
        ok, err = tool.validate_params(action="get")
        assert ok is False
        assert "file_id" in err

    def test_download_requires_file_id(self):
        tool = GoogleDriveTool()
        ok, err = tool.validate_params(action="download")
        assert ok is False
        assert "file_id" in err

    def test_delete_requires_file_id(self):
        tool = GoogleDriveTool()
        ok, err = tool.validate_params(action="delete")
        assert ok is False
        assert "file_id" in err

    def test_update_requires_file_id(self):
        tool = GoogleDriveTool()
        ok, err = tool.validate_params(action="update")
        assert ok is False
        assert "file_id" in err

    def test_upload_requires_name(self):
        tool = GoogleDriveTool()
        ok, err = tool.validate_params(action="upload", content="data")
        assert ok is False
        assert "name" in err

    def test_upload_requires_content(self):
        tool = GoogleDriveTool()
        ok, err = tool.validate_params(action="upload", name="file.txt")
        assert ok is False
        assert "content" in err

    def test_create_folder_requires_name(self):
        tool = GoogleDriveTool()
        ok, err = tool.validate_params(action="create_folder")
        assert ok is False
        assert "name" in err


# ---------------------------------------------------------------------------
# Execution tests
# ---------------------------------------------------------------------------


class TestGoogleDriveToolList:
    """Test list action."""

    @pytest.mark.asyncio
    async def test_list_files(self):
        tool = GoogleDriveTool()
        items = [_fake_file_item("f1", "a.txt"), _fake_file_item("f2", "b.txt")]
        service = _build_mock_service(list_response=_fake_list_response(items))

        with patch(
            "taskforce.infrastructure.tools.native.google_drive_tool._build_service",
            return_value=service,
        ):
            result = await tool.execute(action="list")

        assert result["success"] is True
        assert result["count"] == 2
        assert result["files"][0]["name"] == "a.txt"

    @pytest.mark.asyncio
    async def test_list_empty(self):
        tool = GoogleDriveTool()
        service = _build_mock_service(list_response=_fake_list_response([]))

        with patch(
            "taskforce.infrastructure.tools.native.google_drive_tool._build_service",
            return_value=service,
        ):
            result = await tool.execute(action="list")

        assert result["success"] is True
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_list_with_folder_id(self):
        tool = GoogleDriveTool()
        service = _build_mock_service(list_response=_fake_list_response([_fake_file_item()]))

        with patch(
            "taskforce.infrastructure.tools.native.google_drive_tool._build_service",
            return_value=service,
        ):
            result = await tool.execute(action="list", folder_id="folder123")

        assert result["success"] is True
        assert result["folder_id"] == "folder123"


class TestGoogleDriveToolGet:
    """Test get action."""

    @pytest.mark.asyncio
    async def test_get_metadata(self):
        tool = GoogleDriveTool()
        meta = _fake_file_item("f1", "doc.txt")
        service = _build_mock_service(get_response=meta)

        with patch(
            "taskforce.infrastructure.tools.native.google_drive_tool._build_service",
            return_value=service,
        ):
            result = await tool.execute(action="get", file_id="f1")

        assert result["success"] is True
        assert result["file"]["name"] == "doc.txt"


class TestGoogleDriveToolDownload:
    """Test download action."""

    @pytest.mark.asyncio
    async def test_download_text_file(self):
        tool = GoogleDriveTool()
        meta = _fake_file_item("f1", "notes.txt", "text/plain")
        service = _build_mock_service(
            get_response=meta,
            get_media_response=b"Hello world",
        )

        with patch(
            "taskforce.infrastructure.tools.native.google_drive_tool._build_service",
            return_value=service,
        ):
            result = await tool.execute(action="download", file_id="f1")

        assert result["success"] is True
        assert result["content"] == "Hello world"
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_download_google_doc_export(self):
        tool = GoogleDriveTool()
        meta = _fake_file_item("f1", "My Doc", "application/vnd.google-apps.document")
        service = _build_mock_service(
            get_response=meta,
            export_response=b"Exported text content",
        )

        with patch(
            "taskforce.infrastructure.tools.native.google_drive_tool._build_service",
            return_value=service,
        ):
            result = await tool.execute(action="download", file_id="f1")

        assert result["success"] is True
        assert result["content"] == "Exported text content"

    @pytest.mark.asyncio
    async def test_download_binary_returns_metadata_only(self):
        tool = GoogleDriveTool()
        meta = _fake_file_item("f1", "photo.png", "image/png")
        service = _build_mock_service(get_response=meta)

        with patch(
            "taskforce.infrastructure.tools.native.google_drive_tool._build_service",
            return_value=service,
        ):
            result = await tool.execute(action="download", file_id="f1")

        assert result["success"] is True
        assert result["content"] is None
        assert "Binary" in result["message"]

    @pytest.mark.asyncio
    async def test_download_unsupported_google_type(self):
        tool = GoogleDriveTool()
        meta = _fake_file_item("f1", "My Form", "application/vnd.google-apps.form")
        service = _build_mock_service(get_response=meta)

        with patch(
            "taskforce.infrastructure.tools.native.google_drive_tool._build_service",
            return_value=service,
        ):
            result = await tool.execute(action="download", file_id="f1")

        assert result["success"] is True
        assert result["content"] is None
        assert "cannot be exported" in result["message"]

    @pytest.mark.asyncio
    async def test_download_truncation(self):
        tool = GoogleDriveTool()
        meta = _fake_file_item("f1", "big.txt", "text/plain")
        big_content = b"x" * 200_000
        service = _build_mock_service(
            get_response=meta,
            get_media_response=big_content,
        )

        with patch(
            "taskforce.infrastructure.tools.native.google_drive_tool._build_service",
            return_value=service,
        ):
            result = await tool.execute(action="download", file_id="f1")

        assert result["success"] is True
        assert result["truncated"] is True
        assert result["content"].endswith("[truncated]")


class TestGoogleDriveToolUpload:
    """Test upload action."""

    @pytest.mark.asyncio
    async def test_upload_text_file(self):
        tool = GoogleDriveTool()
        service = _build_mock_service()

        with patch(
            "taskforce.infrastructure.tools.native.google_drive_tool._build_service",
            return_value=service,
        ):
            result = await tool.execute(action="upload", name="test.txt", content="Hello")

        assert result["success"] is True
        assert "Uploaded" in result["message"]

    @pytest.mark.asyncio
    async def test_upload_with_custom_mime(self):
        tool = GoogleDriveTool()
        service = _build_mock_service()

        with patch(
            "taskforce.infrastructure.tools.native.google_drive_tool._build_service",
            return_value=service,
        ):
            result = await tool.execute(
                action="upload",
                name="data.csv",
                content="a,b\n1,2",
                mime_type="text/csv",
            )

        assert result["success"] is True


class TestGoogleDriveToolUpdate:
    """Test update action."""

    @pytest.mark.asyncio
    async def test_update_content(self):
        tool = GoogleDriveTool()
        service = _build_mock_service()

        with patch(
            "taskforce.infrastructure.tools.native.google_drive_tool._build_service",
            return_value=service,
        ):
            result = await tool.execute(action="update", file_id="f1", content="New content")

        assert result["success"] is True
        assert "updated" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_update_name(self):
        tool = GoogleDriveTool()
        service = _build_mock_service()

        with patch(
            "taskforce.infrastructure.tools.native.google_drive_tool._build_service",
            return_value=service,
        ):
            result = await tool.execute(action="update", file_id="f1", name="renamed.txt")

        assert result["success"] is True


class TestGoogleDriveToolDelete:
    """Test delete action."""

    @pytest.mark.asyncio
    async def test_delete(self):
        tool = GoogleDriveTool()
        service = _build_mock_service()

        with patch(
            "taskforce.infrastructure.tools.native.google_drive_tool._build_service",
            return_value=service,
        ):
            result = await tool.execute(action="delete", file_id="f1")

        assert result["success"] is True
        assert result["file_id"] == "f1"


class TestGoogleDriveToolCreateFolder:
    """Test create_folder action."""

    @pytest.mark.asyncio
    async def test_create_folder(self):
        tool = GoogleDriveTool()
        service = _build_mock_service(
            create_response={
                "id": "folder1",
                "name": "Reports",
                "mimeType": "application/vnd.google-apps.folder",
                "webViewLink": "https://drive.google.com/drive/folders/folder1",
            }
        )

        with patch(
            "taskforce.infrastructure.tools.native.google_drive_tool._build_service",
            return_value=service,
        ):
            result = await tool.execute(action="create_folder", name="Reports")

        assert result["success"] is True
        assert "Reports" in result["message"]

    @pytest.mark.asyncio
    async def test_create_folder_with_parent(self):
        tool = GoogleDriveTool()
        service = _build_mock_service()

        with patch(
            "taskforce.infrastructure.tools.native.google_drive_tool._build_service",
            return_value=service,
        ):
            result = await tool.execute(action="create_folder", name="Sub", folder_id="parent123")

        assert result["success"] is True


class TestGoogleDriveToolSearch:
    """Test search action."""

    @pytest.mark.asyncio
    async def test_search(self):
        tool = GoogleDriveTool()
        items = [_fake_file_item("f1", "report.pdf", "application/pdf")]
        service = _build_mock_service(list_response=_fake_list_response(items))

        with patch(
            "taskforce.infrastructure.tools.native.google_drive_tool._build_service",
            return_value=service,
        ):
            result = await tool.execute(action="search", query="name contains 'report'")

        assert result["success"] is True
        assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_search_empty(self):
        tool = GoogleDriveTool()
        service = _build_mock_service(list_response=_fake_list_response([]))

        with patch(
            "taskforce.infrastructure.tools.native.google_drive_tool._build_service",
            return_value=service,
        ):
            result = await tool.execute(action="search", query="name = 'nonexistent'")

        assert result["success"] is True
        assert result["count"] == 0


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class TestGoogleDriveToolErrors:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_missing_google_dependency(self, monkeypatch: pytest.MonkeyPatch):
        """Import error returns install instructions."""
        tool = GoogleDriveTool()

        # Remove google modules to trigger ImportError
        monkeypatch.delitem(sys.modules, "google.oauth2.credentials", raising=False)
        monkeypatch.delitem(sys.modules, "google.oauth2", raising=False)
        monkeypatch.delitem(sys.modules, "google", raising=False)
        monkeypatch.delitem(sys.modules, "googleapiclient.discovery", raising=False)
        monkeypatch.delitem(sys.modules, "googleapiclient", raising=False)

        # Force ImportError by patching builtins
        original_import = (
            __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__
        )

        def mock_import(name, *args, **kwargs):
            if "google" in name:
                raise ImportError("No module named 'google'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        result = await tool.execute(action="list")
        assert result["success"] is False
        assert "uv sync" in result["error"]

    @pytest.mark.asyncio
    async def test_build_service_failure(self):
        """Missing credentials raises helpful error."""
        tool = GoogleDriveTool()

        with patch(
            "taskforce.infrastructure.tools.native.google_drive_tool._build_service",
            side_effect=ValueError("No credentials found"),
        ):
            result = await tool.execute(action="list")

        assert result.get("success") is False or "error" in result

    @pytest.mark.asyncio
    async def test_api_error_on_list(self):
        """API error is caught and wrapped."""
        tool = GoogleDriveTool()
        service = MagicMock()
        service.files().list().execute.side_effect = Exception("API quota exceeded")

        with patch(
            "taskforce.infrastructure.tools.native.google_drive_tool._build_service",
            return_value=service,
        ):
            result = await tool.execute(action="list")

        assert result.get("success") is False or "error" in result
