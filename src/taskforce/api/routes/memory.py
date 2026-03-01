"""Memory management API routes.

Provides REST endpoints for triggering consolidation, listing experiences,
and viewing consolidation history.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/memory")


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------


class ConsolidateRequest(BaseModel):
    """Request body for triggering consolidation."""

    profile: str = Field("dev", description="Profile to load config from")
    strategy: str = Field("batch", description="Consolidation strategy")
    max_sessions: int = Field(20, description="Max sessions to process")
    session_ids: list[str] | None = Field(None, description="Specific sessions")


class ConsolidateResponse(BaseModel):
    """Response body from a consolidation run."""

    consolidation_id: str
    strategy: str
    sessions_processed: int
    memories_created: int
    memories_updated: int
    memories_retired: int
    contradictions_resolved: int
    quality_score: float
    total_tokens: int


class ExperienceSummary(BaseModel):
    """Summary of a session experience."""

    session_id: str
    profile: str
    mission: str
    total_steps: int
    tool_calls: int
    processed: bool


class ConsolidationHistoryItem(BaseModel):
    """Summary of a past consolidation run."""

    consolidation_id: str
    strategy: str
    sessions_processed: int
    memories_created: int
    quality_score: float


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------


@router.post("/consolidate", response_model=ConsolidateResponse)
async def trigger_consolidation(body: ConsolidateRequest) -> ConsolidateResponse:
    """Trigger memory consolidation of captured experiences."""
    from taskforce.application.consolidation_service import (
        build_consolidation_components,
    )
    from taskforce.application.infrastructure_builder import InfrastructureBuilder
    from taskforce.application.profile_loader import ProfileLoader

    loader = ProfileLoader()
    config = loader.load(body.profile)

    ib = InfrastructureBuilder()
    llm_provider = ib.build_llm_provider(config)

    tracker, service = build_consolidation_components(config, llm_provider)
    if service is None:
        raise HTTPException(
            status_code=400,
            detail="Consolidation is not enabled in this profile",
        )

    result = await service.trigger_consolidation(
        session_ids=body.session_ids,
        strategy=body.strategy,
        max_sessions=body.max_sessions,
    )

    return ConsolidateResponse(
        consolidation_id=result.consolidation_id,
        strategy=result.strategy,
        sessions_processed=result.sessions_processed,
        memories_created=result.memories_created,
        memories_updated=result.memories_updated,
        memories_retired=result.memories_retired,
        contradictions_resolved=result.contradictions_resolved,
        quality_score=result.quality_score,
        total_tokens=result.total_tokens,
    )


@router.get("/experiences", response_model=list[ExperienceSummary])
async def list_experiences(
    profile: str = "dev",
    limit: int = 20,
    unprocessed: bool = False,
) -> list[ExperienceSummary]:
    """List captured session experiences."""
    from taskforce.application.infrastructure_builder import InfrastructureBuilder
    from taskforce.application.profile_loader import ProfileLoader

    loader = ProfileLoader()
    config = loader.load(profile)
    work_dir = config.get("consolidation", {}).get("work_dir", ".taskforce/experiences")

    store = InfrastructureBuilder().build_experience_store(work_dir)
    experiences = await store.list_experiences(limit=limit, unprocessed_only=unprocessed)

    return [
        ExperienceSummary(
            session_id=exp.session_id,
            profile=exp.profile,
            mission=exp.mission[:200],
            total_steps=exp.total_steps,
            tool_calls=len(exp.tool_calls),
            processed=bool(exp.processed_by),
        )
        for exp in experiences
    ]


@router.get("/consolidations", response_model=list[ConsolidationHistoryItem])
async def list_consolidations(
    profile: str = "dev",
    limit: int = 10,
) -> list[ConsolidationHistoryItem]:
    """List past consolidation runs."""
    from taskforce.application.infrastructure_builder import InfrastructureBuilder
    from taskforce.application.profile_loader import ProfileLoader

    loader = ProfileLoader()
    config = loader.load(profile)
    work_dir = config.get("consolidation", {}).get("work_dir", ".taskforce/experiences")

    store = InfrastructureBuilder().build_experience_store(work_dir)
    results = await store.list_consolidations(limit=limit)

    return [
        ConsolidationHistoryItem(
            consolidation_id=r.consolidation_id,
            strategy=r.strategy,
            sessions_processed=r.sessions_processed,
            memories_created=r.memories_created,
            quality_score=r.quality_score,
        )
        for r in results
    ]
