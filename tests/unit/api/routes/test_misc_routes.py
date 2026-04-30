"""Unit tests for the lightweight Phase-2 listing routes."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from taskforce.api.server import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_planning_strategies_returns_four_entries(client: TestClient) -> None:
    response = client.get("/api/v1/planning-strategies")
    assert response.status_code == 200
    body = response.json()
    ids = {s["id"] for s in body["strategies"]}
    assert ids == {"native_react", "plan_and_execute", "plan_and_react", "spar"}


def test_llm_models_returns_default_and_aliases(client: TestClient) -> None:
    response = client.get("/api/v1/llm/models")
    assert response.status_code == 200
    body = response.json()
    assert "default_model" in body
    assert "models" in body
    if body["models"]:
        first = body["models"][0]
        assert {"alias", "model_id", "provider"} <= first.keys()


def test_skills_endpoint_returns_list(client: TestClient) -> None:
    response = client.get("/api/v1/skills")
    assert response.status_code == 200
    body = response.json()
    assert "skills" in body
    assert isinstance(body["skills"], list)


def test_skill_detail_strips_frontmatter_and_caches(
    client: TestClient, tmp_path, monkeypatch
) -> None:
    """``GET /skills/{name}`` returns body without frontmatter; cached by mtime."""
    from types import SimpleNamespace
    from taskforce.api.routes import skills as skills_route

    skill_path = tmp_path / "demo" / "SKILL.md"
    skill_path.parent.mkdir()
    skill_path.write_text(
        "---\n"
        "name: demo\n"
        "description: A demo skill\n"
        "skill_type: context\n"
        "---\n"
        "\n"
        "## Heading\n\nBody with --- inside the prose stays intact.\n",
        encoding="utf-8",
    )

    fake_meta = SimpleNamespace(
        name="demo",
        description="A demo skill",
        skill_type="context",
        slash_name="demo",
        file_path=str(skill_path),
        allowed_tools=[],
    )

    class _Service:
        def get_all_metadata(self):
            return [fake_meta]

    monkeypatch.setattr(skills_route, "get_skill_service", lambda: _Service())
    skills_route._read_skill_body.cache_clear()

    response = client.get("/api/v1/skills/demo")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "demo"
    # Frontmatter dropped; the body's literal ``---`` survives.
    assert "name: demo" not in body["body"]
    assert "Body with --- inside the prose stays intact." in body["body"]


def test_skill_detail_supports_hierarchical_name(
    client: TestClient, tmp_path, monkeypatch
) -> None:
    """Skill names with ``:`` separators round-trip through URL encoding."""
    from types import SimpleNamespace
    from taskforce.api.routes import skills as skills_route

    skill_path = tmp_path / "agents-reviewer" / "SKILL.md"
    skill_path.parent.mkdir()
    skill_path.write_text(
        "---\nname: agents:reviewer\nskill_type: agent\n---\nReview body.\n",
        encoding="utf-8",
    )

    fake_meta = SimpleNamespace(
        name="agents:reviewer",
        description="",
        skill_type="agent",
        slash_name="agents:reviewer",
        file_path=str(skill_path),
        allowed_tools=[],
    )

    class _Service:
        def get_all_metadata(self):
            return [fake_meta]

    monkeypatch.setattr(skills_route, "get_skill_service", lambda: _Service())
    skills_route._read_skill_body.cache_clear()

    response = client.get("/api/v1/skills/agents%3Areviewer")
    assert response.status_code == 200
    assert response.json()["name"] == "agents:reviewer"
    assert "Review body" in response.json()["body"]


def test_skill_detail_returns_404_for_unknown_name(
    client: TestClient, monkeypatch
) -> None:
    from taskforce.api.routes import skills as skills_route

    class _Service:
        def get_all_metadata(self):
            return []

    monkeypatch.setattr(skills_route, "get_skill_service", lambda: _Service())

    response = client.get("/api/v1/skills/never-existed")
    assert response.status_code == 404
    assert response.json()["code"] == "skill_not_found"
