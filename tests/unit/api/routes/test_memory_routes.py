"""REST read surface for wiki long-term memory (GET /api/v1/memory/*).

The routes are read-only and build the wiki store via
``InfrastructureBuilder.build_wiki_store`` rooted at ``TASKFORCE_WORK_DIR``.
These tests mount the router on a bare ``FastAPI()`` app so no auth
middleware is involved — ``require_permission`` is a no-op without it.

Spec: docs/spec/wiki-memory.md.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taskforce.api.routes import memory
from taskforce.core.domain.wiki_page import WikiPage
from taskforce.infrastructure.memory.file_wiki_store import FileWikiStore


async def _seed(tmp_path: Path) -> None:
    store = FileWikiStore(tmp_path / "memory" / "wiki")
    await store.write_page(
        WikiPage(
            name="entities/mueller",
            title="Steuerberater Mueller",
            body="## Kontakt\n- Tel: 0664-1234567\n",
            tags=["kontakt", "steuer"],
        )
    )


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("TASKFORCE_WORK_DIR", str(tmp_path))
    asyncio.run(_seed(tmp_path))
    application = FastAPI()
    application.include_router(memory.router, prefix="/api/v1")
    return application


@pytest.mark.spec("wiki-memory.rest_memory_list_returns_page_summaries")
def test_memory_list_returns_page_summaries(app: FastAPI) -> None:
    response = TestClient(app).get("/api/v1/memory/list")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    summary = body[0]
    assert summary["name"] == "entities/mueller"
    assert summary["title"] == "Steuerberater Mueller"
    assert summary["kind"] == "entities"
    assert summary["tags"] == ["kontakt", "steuer"]
    # Summary is a one-liner — it must NOT carry the page body.
    assert "body" not in summary


def test_memory_page_returns_full_page(app: FastAPI) -> None:
    response = TestClient(app).get("/api/v1/memory/page/entities/mueller")

    assert response.status_code == 200
    page = response.json()
    assert page["name"] == "entities/mueller"
    assert "0664-1234567" in page["body"]
    assert page["created_at"]


@pytest.mark.spec("wiki-memory.rest_memory_page_missing_returns_404")
def test_memory_page_missing_returns_404(app: FastAPI) -> None:
    response = TestClient(app).get("/api/v1/memory/page/entities/does-not-exist")

    assert response.status_code == 404
