"""Pydantic schemas for the file upload / download endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FileMetadataResponse(BaseModel):
    file_id: str = Field(..., description="32-character hex identifier")
    name: str
    mime: str
    size: int = Field(..., description="Bytes")
    sha256: str
    created_at: str
