"""
File API Routes
===============

Generic file upload / download for the management UI. Phase 4 wires
chat attachments through this surface.

Endpoints:

* ``POST   /api/v1/files``               — multipart upload
* ``GET    /api/v1/files/{file_id}``     — streaming download
* ``GET    /api/v1/files/{file_id}/meta`` — metadata
* ``DELETE /api/v1/files/{file_id}``     — delete
"""

from __future__ import annotations

from typing import Iterable

from fastapi import APIRouter, File, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from taskforce.api.errors import http_exception as _http_exception
from taskforce.api.schemas.file_schemas import FileMetadataResponse
from taskforce.application.file_storage import (
    FileNotFound,
    FileStorageError,
    FileTooLarge,
    get_file_storage,
)

router = APIRouter()


def _to_response(meta) -> FileMetadataResponse:
    return FileMetadataResponse(
        file_id=meta.file_id,
        name=meta.name,
        mime=meta.mime,
        size=meta.size,
        sha256=meta.sha256,
        created_at=meta.created_at,
    )


@router.post(
    "/files",
    response_model=FileMetadataResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a file",
)
async def upload_file(file: UploadFile = File(...)) -> FileMetadataResponse:
    storage = get_file_storage()
    try:
        meta = storage.save(
            name=file.filename or "file.bin",
            stream=file.file,
            declared_mime=file.content_type,
        )
    except FileTooLarge as exc:
        raise _http_exception(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            code="file_too_large",
            message=str(exc),
            details={"limit_bytes": storage.max_bytes},
        ) from exc
    except FileStorageError as exc:
        raise _http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="upload_failed",
            message=str(exc),
        ) from exc
    finally:
        await file.close()
    return _to_response(meta)


@router.get(
    "/files/{file_id}/meta",
    response_model=FileMetadataResponse,
    summary="Get file metadata",
)
def get_file_meta(file_id: str) -> FileMetadataResponse:
    try:
        meta = get_file_storage().get_metadata(file_id)
    except FileNotFound as exc:
        raise _http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="file_not_found",
            message=str(exc),
        ) from exc
    return _to_response(meta)


@router.get(
    "/files/{file_id}",
    summary="Download a file",
    responses={
        200: {
            "description": "Binary file content (streamed).",
            "content": {"application/octet-stream": {}},
        }
    },
)
def download_file(file_id: str) -> StreamingResponse:
    try:
        handle, meta = get_file_storage().open_stream(file_id)
    except FileNotFound as exc:
        raise _http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="file_not_found",
            message=str(exc),
        ) from exc

    def _iterator() -> Iterable[bytes]:
        try:
            while True:
                chunk = handle.read(1 << 16)
                if not chunk:
                    break
                yield chunk
        finally:
            handle.close()

    headers = {
        "Content-Length": str(meta.size),
        "Content-Disposition": f'attachment; filename="{_safe_filename(meta.name)}"',
        "X-Taskforce-File-Sha256": meta.sha256,
    }
    return StreamingResponse(_iterator(), media_type=meta.mime, headers=headers)


@router.delete(
    "/files/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a file",
)
def delete_file(file_id: str) -> Response:
    try:
        get_file_storage().delete(file_id)
    except FileNotFound as exc:
        raise _http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="file_not_found",
            message=str(exc),
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _safe_filename(name: str) -> str:
    """Strip CR/LF and quotes so Content-Disposition stays well-formed."""
    return name.replace("\r", "").replace("\n", "").replace('"', "")
