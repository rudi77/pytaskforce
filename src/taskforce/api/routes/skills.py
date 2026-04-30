"""
Skills API Routes
=================

Read-only listing of skills discovered by :class:`SkillService`. Used by
the management UI to render an overview of available context, prompt
and agent skills.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from taskforce.api.errors import http_exception as _http_exception
from taskforce.application.profile_loader import _split_agent_md_frontmatter
from taskforce.application.skill_service import get_skill_service

router = APIRouter()


class SkillSummary(BaseModel):
    """One entry in the skill catalog."""

    name: str
    description: str
    skill_type: Literal["context", "prompt", "agent", "library", "integration"]
    slash_name: str | None = Field(
        None,
        description="Slash command name for prompt/agent skills (without leading `/`)",
    )
    file_path: str | None = None
    allowed_tools: list[str] = Field(default_factory=list)


class SkillListResponse(BaseModel):
    skills: list[SkillSummary]


def _to_summary(meta) -> SkillSummary:
    """Convert a SkillMetadataModel to the API summary."""
    skill_type = getattr(meta.skill_type, "value", str(meta.skill_type)).lower()
    return SkillSummary(
        name=meta.name,
        description=getattr(meta, "description", "") or "",
        skill_type=skill_type if skill_type in {"context", "prompt", "agent", "library", "integration"} else "context",
        slash_name=getattr(meta, "slash_name", None) or getattr(meta, "name", None),
        file_path=str(getattr(meta, "file_path", "") or "") or None,
        allowed_tools=list(getattr(meta, "allowed_tools", []) or []),
    )


class SkillDetail(SkillSummary):
    """Skill summary plus the SKILL.md body so the UI can preview it."""

    body: str = Field(default="", description="Markdown body of the skill file")


@lru_cache(maxsize=128)
def _read_skill_body(path_str: str, mtime_ns: int) -> str:
    """Read and de-frontmatter a SKILL.md, cached by ``(path, mtime_ns)``.

    The mtime is part of the key so edits to the file invalidate the cache
    automatically — it's a sentinel, not a stored value.
    """
    del mtime_ns  # used purely as cache key
    path = Path(path_str)
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    _, body = _split_agent_md_frontmatter(text)
    return body


def _skill_body(path_str: str | None) -> str:
    if not path_str:
        return ""
    path = Path(path_str)
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        return ""
    return _read_skill_body(str(path), mtime_ns)


@router.get(
    "/skills",
    response_model=SkillListResponse,
    summary="List all available skills",
)
def list_skills() -> SkillListResponse:
    """Return every skill discovered by the global SkillService."""
    service = get_skill_service()
    skills = [_to_summary(meta) for meta in service.get_all_metadata()]
    skills.sort(key=lambda s: s.name)
    return SkillListResponse(skills=skills)


@router.get(
    "/skills/{name:path}",
    response_model=SkillDetail,
    summary="Read a skill (frontmatter + body)",
)
def get_skill(name: str) -> SkillDetail:
    """Return the parsed skill metadata plus the SKILL.md body."""
    service = get_skill_service()
    metadata = None
    for meta in service.get_all_metadata():
        if getattr(meta, "name", None) == name:
            metadata = meta
            break
    if metadata is None:
        raise _http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="skill_not_found",
            message=f"Skill '{name}' not found.",
        )

    summary = _to_summary(metadata)
    body = _skill_body(getattr(metadata, "file_path", None))
    return SkillDetail(**summary.model_dump(), body=body)
