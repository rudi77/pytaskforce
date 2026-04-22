"""Wiki (long-term memory) management API routes.

Replaces the old record-based memory endpoint.  Exposes read-only
listing and lookup of wiki pages backed by ``FileWikiStore``.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/memory")


class WikiPageSummary(BaseModel):
    """One-line summary of a wiki page."""

    name: str
    title: str
    kind: str
    tags: list[str]
    updated_at: str


class WikiPageDetail(WikiPageSummary):
    """Full wiki page payload."""

    body: str
    created_at: str


@router.get("/list", response_model=list[WikiPageSummary])
async def list_pages(profile: str = "dev", limit: int = 50) -> list[WikiPageSummary]:
    """List wiki pages for a given profile."""
    from taskforce.application.infrastructure_builder import InfrastructureBuilder
    from taskforce.application.profile_loader import ProfileLoader

    config = ProfileLoader().load(profile)
    work_dir = config.get("persistence", {}).get("work_dir", ".taskforce")
    store = InfrastructureBuilder().build_wiki_store(work_dir)
    pages = await store.list_pages()
    return [
        WikiPageSummary(
            name=p.name,
            title=p.title,
            kind=p.kind,
            tags=list(p.tags),
            updated_at=p.updated_at.isoformat(),
        )
        for p in pages[:limit]
    ]


@router.get("/page/{name:path}", response_model=WikiPageDetail)
async def get_page(name: str, profile: str = "dev") -> WikiPageDetail:
    """Return one wiki page by its relative path."""
    from taskforce.application.infrastructure_builder import InfrastructureBuilder
    from taskforce.application.profile_loader import ProfileLoader

    config = ProfileLoader().load(profile)
    work_dir = config.get("persistence", {}).get("work_dir", ".taskforce")
    store = InfrastructureBuilder().build_wiki_store(work_dir)
    page = await store.get_page(name)
    if page is None:
        raise HTTPException(status_code=404, detail=f"page not found: {name}")
    return WikiPageDetail(
        name=page.name,
        title=page.title,
        kind=page.kind,
        tags=list(page.tags),
        updated_at=page.updated_at.isoformat(),
        body=page.body,
        created_at=page.created_at.isoformat(),
    )
