"""Memory management API routes.

Provides REST endpoints for listing and managing long-term memories.
Consolidation and experience tracking have been moved to agent packages.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/memory")


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------


class MemoryItem(BaseModel):
    """Summary of a stored memory."""

    memory_id: str
    kind: str
    content: str


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------


@router.get("/list", response_model=list[MemoryItem])
async def list_memories(
    profile: str = "dev",
    limit: int = 20,
) -> list[MemoryItem]:
    """List stored long-term memories."""
    from taskforce.application.infrastructure_builder import InfrastructureBuilder
    from taskforce.application.profile_loader import ProfileLoader

    loader = ProfileLoader()
    config = loader.load(profile)
    memory_dir = config.get("persistence", {}).get("work_dir", ".taskforce")

    store = InfrastructureBuilder().build_memory_store(memory_dir)
    memories = await store.list()

    return [
        MemoryItem(
            memory_id=str(getattr(m, "memory_id", ""))[:40],
            kind=str(getattr(m, "kind", "unknown")),
            content=str(getattr(m, "content", ""))[:200],
        )
        for m in memories[:limit]
    ]
