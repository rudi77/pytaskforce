"""Google Drive tool for file operations.

Provides list, get, download, upload, update, delete, create_folder,
and search operations for Google Drive. Uses the same OAuth token as
the calendar and gmail tools (~/.taskforce/google_token.json).
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from taskforce.core.domain.errors import ToolError, tool_error_payload
from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.tools.base_tool import BaseTool

logger = structlog.get_logger(__name__)

# Maximum text content returned from downloads (characters).
_MAX_CONTENT_CHARS = 100_000

# Google Workspace MIME types and their text export targets.
_EXPORT_MIME_MAP: dict[str, str] = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}

# MIME prefixes that indicate binary content.
_BINARY_PREFIXES = ("image/", "video/", "audio/", "application/octet-stream")

# Standard fields returned for file listings.
_LIST_FIELDS = "files(id, name, mimeType, modifiedTime, size, parents)"


class GoogleDriveTool(BaseTool):
    """Tool for Google Drive file operations.

    Supports listing, reading, downloading, uploading, updating,
    deleting files and creating folders. Requires Google OAuth
    credentials with Drive scope.
    """

    tool_name = "google_drive"
    tool_description = (
        "Google Drive file operations. Actions: "
        "list (list files in a folder), "
        "get (file metadata), "
        "download (file content; exports Google Docs/Sheets/Slides to text), "
        "upload (create a new file), "
        "update (modify file content or name), "
        "delete (remove a file), "
        "create_folder (create a new folder), "
        "search (find files by Drive query syntax, e.g. \"name contains 'report'\")."
    )
    tool_parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "list",
                    "get",
                    "download",
                    "upload",
                    "update",
                    "delete",
                    "create_folder",
                    "search",
                ],
                "description": "Google Drive action to perform",
            },
            "file_id": {
                "type": "string",
                "description": ("File or folder ID (required for get, download, update, delete)"),
            },
            "folder_id": {
                "type": "string",
                "description": ("Parent folder ID for listing or uploading (default: 'root')"),
            },
            "query": {
                "type": "string",
                "description": (
                    "Search query using Drive query syntax (for search action). "
                    "Example: \"name contains 'report'\" or \"mimeType = 'application/pdf'\""
                ),
            },
            "name": {
                "type": "string",
                "description": "File or folder name (required for upload and create_folder)",
            },
            "content": {
                "type": "string",
                "description": "Text content for upload or update",
            },
            "mime_type": {
                "type": "string",
                "description": (
                    "MIME type for upload (default: 'text/plain'). "
                    "Use 'application/vnd.google-apps.document' to create a Google Doc."
                ),
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum files to return (default: 20, max: 100)",
            },
        },
        "required": ["action"],
    }
    tool_requires_approval = True
    tool_approval_risk_level = ApprovalRiskLevel.MEDIUM
    tool_supports_parallelism = True

    async def _execute(self, **kwargs: Any) -> dict[str, Any]:
        """Execute a Google Drive action."""
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError:
            return {
                "success": False,
                "error": (
                    "Google API not available. Install with: " "uv sync --extra personal-assistant"
                ),
            }

        action = kwargs.get("action")
        try:
            service = _build_service(build, Credentials)

            if action == "list":
                return await _list_files(service, kwargs)
            if action == "get":
                return await _get_file(service, kwargs)
            if action == "download":
                return await _download_file(service, kwargs)
            if action == "upload":
                return await _upload_file(service, kwargs)
            if action == "update":
                return await _update_file(service, kwargs)
            if action == "delete":
                return await _delete_file(service, kwargs)
            if action == "create_folder":
                return await _create_folder(service, kwargs)
            if action == "search":
                return await _search_files(service, kwargs)

            return {"success": False, "error": f"Unknown action: {action}"}
        except Exception as exc:
            return tool_error_payload(
                ToolError(f"google_drive failed: {exc}", tool_name="google_drive")
            )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters for the requested action."""
        action = kwargs.get("action")
        valid_actions = {
            "list",
            "get",
            "download",
            "upload",
            "update",
            "delete",
            "create_folder",
            "search",
        }
        if action not in valid_actions:
            return False, f"action must be one of {sorted(valid_actions)}"

        if action in ("get", "download", "delete") and not kwargs.get("file_id"):
            return False, f"file_id is required for {action} action"

        if action == "update" and not kwargs.get("file_id"):
            return False, "file_id is required for update action"

        if action == "upload":
            if not kwargs.get("name"):
                return False, "name is required for upload action"
            if not kwargs.get("content"):
                return False, "content is required for upload action"

        if action == "create_folder" and not kwargs.get("name"):
            return False, "name is required for create_folder action"

        return True, None

    def get_approval_preview(self, **kwargs: Any) -> str:
        """Return a human-readable preview for approval prompts."""
        action = kwargs.get("action", "")
        target = kwargs.get("name", kwargs.get("file_id", ""))
        return f"Tool: {self.name}\nOperation: {action}\nTarget: {target}"


# ---------------------------------------------------------------------------
# Service builder
# ---------------------------------------------------------------------------


def _build_service(build: Any, credentials_cls: Any) -> Any:
    """Build Google Drive API service using the shared OAuth token."""
    import json
    from pathlib import Path

    from google.auth.transport.requests import Request

    token_path = Path.home() / ".taskforce" / "google_token.json"
    if not token_path.exists():
        raise ValueError("No credentials found. Run 'python scripts/google_auth.py' first.")

    with open(token_path, encoding="utf-8") as f:
        creds_data = json.load(f)

    creds = credentials_cls.from_authorized_user_info(creds_data)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("drive", "v3", credentials=creds)


# ---------------------------------------------------------------------------
# Action implementations
# ---------------------------------------------------------------------------


async def _list_files(service: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """List files in a folder."""
    folder_id = kwargs.get("folder_id", "root")
    max_results = min(int(kwargs.get("max_results", 20)), 100)

    query = f"'{folder_id}' in parents and trashed = false"
    result = await asyncio.to_thread(
        lambda: service.files()
        .list(q=query, pageSize=max_results, fields=f"nextPageToken, {_LIST_FIELDS}")
        .execute()
    )

    files = _format_file_list(result.get("files", []))
    return {"success": True, "files": files, "count": len(files), "folder_id": folder_id}


async def _get_file(service: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Get file metadata."""
    file_id = kwargs["file_id"]
    fields = "id, name, mimeType, modifiedTime, size, parents, webViewLink, description"

    meta = await asyncio.to_thread(
        lambda: service.files().get(fileId=file_id, fields=fields).execute()
    )
    return {"success": True, "file": meta}


async def _download_file(service: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Download file content."""
    file_id = kwargs["file_id"]

    # First get metadata to determine MIME type.
    meta = await asyncio.to_thread(
        lambda: service.files().get(fileId=file_id, fields="id, name, mimeType, size").execute()
    )
    mime_type = meta.get("mimeType", "")
    name = meta.get("name", "")

    # Binary files — return metadata only.
    if any(mime_type.startswith(p) for p in _BINARY_PREFIXES):
        return {
            "success": True,
            "file_id": file_id,
            "name": name,
            "mime_type": mime_type,
            "content": None,
            "message": "Binary file — content cannot be displayed inline.",
        }

    # Google Workspace types — export to text.
    if mime_type in _EXPORT_MIME_MAP:
        export_mime = _EXPORT_MIME_MAP[mime_type]
        data = await asyncio.to_thread(
            lambda: service.files().export(fileId=file_id, mimeType=export_mime).execute()
        )
        content = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)
    elif mime_type.startswith("application/vnd.google-apps."):
        return {
            "success": True,
            "file_id": file_id,
            "name": name,
            "mime_type": mime_type,
            "content": None,
            "message": f"Google Workspace type '{mime_type}' cannot be exported to text.",
        }
    else:
        # Regular file — download content.
        data = await asyncio.to_thread(lambda: service.files().get_media(fileId=file_id).execute())
        content = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)

    truncated = len(content) > _MAX_CONTENT_CHARS
    if truncated:
        content = content[:_MAX_CONTENT_CHARS] + "\n[truncated]"

    return {
        "success": True,
        "file_id": file_id,
        "name": name,
        "mime_type": mime_type,
        "content": content,
        "truncated": truncated,
    }


async def _upload_file(service: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Upload a new file."""
    from googleapiclient.http import MediaInMemoryUpload

    name = kwargs["name"]
    content = kwargs["content"]
    mime_type = kwargs.get("mime_type", "text/plain")
    folder_id = kwargs.get("folder_id", "root")

    metadata: dict[str, Any] = {"name": name, "parents": [folder_id]}
    media = MediaInMemoryUpload(content.encode("utf-8"), mimetype=mime_type, resumable=False)

    created = await asyncio.to_thread(
        lambda: service.files()
        .create(body=metadata, media_body=media, fields="id, name, mimeType, webViewLink")
        .execute()
    )
    return {"success": True, "file": created, "message": f"Uploaded '{name}' successfully."}


async def _update_file(service: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Update an existing file's content or name."""
    from googleapiclient.http import MediaInMemoryUpload

    file_id = kwargs["file_id"]
    content = kwargs.get("content")
    new_name = kwargs.get("name")

    metadata: dict[str, Any] = {}
    if new_name:
        metadata["name"] = new_name

    media = None
    if content is not None:
        mime_type = kwargs.get("mime_type", "text/plain")
        media = MediaInMemoryUpload(content.encode("utf-8"), mimetype=mime_type, resumable=False)

    updated = await asyncio.to_thread(
        lambda: service.files()
        .update(fileId=file_id, body=metadata, media_body=media, fields="id, name, mimeType")
        .execute()
    )
    return {"success": True, "file": updated, "message": "File updated successfully."}


async def _delete_file(service: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Delete a file."""
    file_id = kwargs["file_id"]
    await asyncio.to_thread(lambda: service.files().delete(fileId=file_id).execute())
    return {"success": True, "file_id": file_id, "message": "File deleted successfully."}


async def _create_folder(service: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Create a new folder."""
    name = kwargs["name"]
    parent_id = kwargs.get("folder_id", "root")

    metadata: dict[str, Any] = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = await asyncio.to_thread(
        lambda: service.files()
        .create(body=metadata, fields="id, name, mimeType, webViewLink")
        .execute()
    )
    return {"success": True, "folder": folder, "message": f"Folder '{name}' created."}


async def _search_files(service: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Search files using Drive query syntax."""
    query = kwargs.get("query", "")
    max_results = min(int(kwargs.get("max_results", 20)), 100)

    # Append trashed filter if not already present.
    if "trashed" not in query.lower():
        query = f"({query}) and trashed = false" if query else "trashed = false"

    result = await asyncio.to_thread(
        lambda: service.files()
        .list(q=query, pageSize=max_results, fields=f"nextPageToken, {_LIST_FIELDS}")
        .execute()
    )

    files = _format_file_list(result.get("files", []))
    return {"success": True, "files": files, "count": len(files), "query": kwargs.get("query", "")}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_file_list(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize file metadata for consistent output."""
    return [
        {
            "id": f.get("id"),
            "name": f.get("name"),
            "mime_type": f.get("mimeType"),
            "modified_time": f.get("modifiedTime"),
            "size": f.get("size"),
        }
        for f in files
    ]
