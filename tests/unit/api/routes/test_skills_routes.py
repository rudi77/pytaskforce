"""Framework REST contract for the skills catalog (GET /api/v1/skills*).

These mount the skills router on a bare ``FastAPI()`` app — no
``create_app()`` — so the enterprise auth middleware is not involved.
The skills read routes carry no permission gate, so a bare app is the
faithful framework contract and the tests are deterministic locally
and in CI.

Spec: docs/spec/skills.md.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taskforce.api.routes import skills as skills_route


def _meta(name: str, skill_type: str = "context") -> SimpleNamespace:
    """Build a minimal skill-metadata stand-in for the route's ``_to_summary``."""
    return SimpleNamespace(
        name=name,
        description=f"{name} description",
        skill_type=skill_type,
        slash_name=name,
        file_path=None,
        allowed_tools=[],
    )


@pytest.fixture
def app() -> FastAPI:
    application = FastAPI()
    application.include_router(skills_route.router, prefix="/api/v1")
    return application


@pytest.mark.spec("skills.rest_list_returns_sorted")
def test_skills_list_returns_sorted(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /skills returns the catalog sorted alphabetically by name, even
    when the underlying service yields metadata in another order."""
    unsorted = [_meta("zebra-skill"), _meta("alpha-skill"), _meta("mid-skill")]

    class _Service:
        def get_all_metadata(self):
            return unsorted

    monkeypatch.setattr(skills_route, "get_skill_service", lambda: _Service())

    response = TestClient(app).get("/api/v1/skills")

    assert response.status_code == 200
    names = [s["name"] for s in response.json()["skills"]]
    assert names == ["alpha-skill", "mid-skill", "zebra-skill"]


@pytest.mark.spec("skills.rest_get_unknown_returns_404")
def test_skills_get_unknown_returns_404(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /skills/{name} returns 404 when no skill with that name exists."""

    class _Service:
        def get_all_metadata(self):
            return [_meta("known-skill")]

    monkeypatch.setattr(skills_route, "get_skill_service", lambda: _Service())

    response = TestClient(app).get("/api/v1/skills/does-not-exist")

    assert response.status_code == 404
