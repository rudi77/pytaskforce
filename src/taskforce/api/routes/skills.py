"""
Skills API Routes
=================

Read-only listing of skills discovered by :class:`SkillService`. Used by
the management UI to render an overview of available context, prompt
and agent skills.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

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
