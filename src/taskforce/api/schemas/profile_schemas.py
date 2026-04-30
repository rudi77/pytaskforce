"""
Profile API Schemas
===================

Pydantic models for the profile-discovery endpoints used by the
management UI. Read-only in Phase 2 — write/update endpoints land in
Phase 3.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ProfileSummary(BaseModel):
    """Lightweight metadata for a single profile (used in list views)."""

    name: str = Field(..., description="Profile identifier (filename minus extension)")
    path: str = Field(..., description="Absolute path to the source file")
    format: Literal["agent_md", "yaml"] = Field(
        ..., description="Source file format"
    )
    description: str = Field("", description="Best-effort description for previews")
    specialist: str | None = Field(
        None, description="Value of the top-level ``specialist`` field"
    )
    name_label: str | None = Field(
        None, description="Human-friendly label declared in the file"
    )
    is_custom: bool = Field(
        False, description="True if the profile lives under a ``custom/`` directory"
    )


class ProfileListResponse(BaseModel):
    """Wrapper around the list of profile summaries."""

    profiles: list[ProfileSummary]


class ProfileDetail(BaseModel):
    """Full configuration plus raw text for a single profile."""

    name: str
    path: str
    format: Literal["agent_md", "yaml"]
    description: str = ""
    specialist: str | None = None
    is_writable: bool = Field(
        False,
        description="True if the API can update or delete this file",
    )
    config: dict[str, Any] = Field(
        ..., description="Parsed and merged configuration dict"
    )
    yaml_text: str = Field(
        ..., description="Original on-disk text (frontmatter + body for .agent.md)"
    )


class ProfileDefinitionPayload(BaseModel):
    """Body for create/update operations.

    Accepts either a structured ``config`` dict (preferred — gets
    serialised by the backend with comment-preserving YAML) or an
    explicit ``yaml_text`` string for power-users.
    """

    config: dict[str, Any] = Field(
        ..., description="Structured configuration that the backend will write as YAML"
    )


class ProfileCreatePayload(ProfileDefinitionPayload):
    """Create body — adds the profile name."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern="^[a-zA-Z0-9._-]+$",
        description="Profile identifier (filename minus extension)",
    )


class ProfileClonePayload(BaseModel):
    """Body for ``POST /profiles/{source}/clone``."""

    target_name: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern="^[a-zA-Z0-9._-]+$",
        description="Name of the new user-owned profile",
    )
