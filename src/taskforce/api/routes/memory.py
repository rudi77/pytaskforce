"""Wiki (long-term memory) management API routes.

Read-only listing and lookup of wiki pages backed by the framework's
``WikiStoreProtocol``. The store is built via
:meth:`InfrastructureBuilder.build_wiki_store` so the plugin override
(``set_wiki_store_override`` — used by ``taskforce-enterprise`` for
per-(tenant, user) scoping) takes effect.

Previously these routes called ``ProfileLoader().load("dev")`` which
hard-coded a profile name that only exists in framework-only builds —
in any Butler / Enterprise deployment the load raised
``FileNotFoundError`` and the route returned 500. The profile-driven
``work_dir`` lookup was unnecessary indirection anyway: the override
ignores ``work_dir`` and reads tenant/user from ContextVars; the
default impl uses ``<work_dir>/memory/wiki``.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from taskforce.api.dependencies import require_permission

router = APIRouter(prefix="/memory")


def _build_store():
    """Build the wiki store rooted at the configured work_dir.

    Goes through ``InfrastructureBuilder`` so any installed override
    (per-tenant/per-user, postgres-backed, etc.) is consulted before
    falling back to the default ``FileWikiStore`` at
    ``<work_dir>/memory/wiki``.
    """
    from taskforce.application.infrastructure_builder import InfrastructureBuilder

    work_dir = os.getenv("TASKFORCE_WORK_DIR", ".taskforce")
    return InfrastructureBuilder().build_wiki_store(work_dir=work_dir)


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
async def list_pages(
    limit: int = 50,
    _permission: None = Depends(require_permission("memory:read")),
) -> list[WikiPageSummary]:
    """List wiki pages for the calling user.

    Permission gate: ``memory:read``. Without an auth middleware the
    gate is a no-op (framework-only mode).
    """
    store = _build_store()
    pages = await store.list_pages()
    return [
        WikiPageSummary(
            name=p.name,
            title=p.title,
            kind=p.kind,
            tags=list(p.tags),
            updated_at=p.updated_at.isoformat(),
        )
        for p in pages[: max(1, limit)]
    ]


@router.get("/page/{name:path}", response_model=WikiPageDetail)
async def get_page(
    name: str,
    _permission: None = Depends(require_permission("memory:read")),
) -> WikiPageDetail:
    """Return one wiki page by its relative path."""
    store = _build_store()
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
