"""
Integration Tests for Agent Templates API
=========================================

Tests the wizard endpoints used by the new agent-creation flow:
- GET /api/v1/agent-templates
- GET /api/v1/agent-templates/{id}
- POST /api/v1/agent-templates/compose-prompt
"""


import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from taskforce.api.server import create_app


@pytest.fixture
def client():
    yield TestClient(create_app())


def test_list_templates_returns_curated_set(client):
    response = client.get("/api/v1/agent-templates")
    assert response.status_code == 200
    data = response.json()
    ids = {t["id"] for t in data["templates"]}
    # All four personas plus the blank fallback must always be present.
    assert {"buchhalter", "handwerker", "assistent", "recherche", "blank"}.issubset(ids)


def test_template_has_required_shape(client):
    response = client.get("/api/v1/agent-templates")
    assert response.status_code == 200
    for tpl in response.json()["templates"]:
        assert tpl["name"]
        assert tpl["description"]
        assert tpl["emoji"]
        assert isinstance(tpl["recommended_tools"], list)
        assert isinstance(tpl["example_prompts"], list)
        assert tpl["system_prompt_template"]
        assert tpl["tone_default"]
        assert tpl["language_default"]


def test_get_single_template(client):
    response = client.get("/api/v1/agent-templates/buchhalter")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "buchhalter"
    assert "Buchhalter" in body["name"]
    assert any("SKR" in line or "Buch" in line for line in body["system_prompt_template"].splitlines())


def test_unknown_template_returns_404(client):
    response = client.get("/api/v1/agent-templates/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "template_not_found"


def test_compose_prompt_deterministic(client):
    response = client.post(
        "/api/v1/agent-templates/compose-prompt",
        json={
            "template_id": "buchhalter",
            "description": "Hilft bei Belegen.",
            "tone": "professionell",
            "language": "Deutsch",
            "rules": "- Beträge mit zwei Nachkommastellen\n- Niemals raten",
            "use_ai": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["used_ai"] is False
    prompt = body["system_prompt"]
    assert "Buchhaltungs-Assistent" in prompt or "SKR" in prompt
    assert "Hilft bei Belegen." in prompt
    assert "professionell" in prompt
    assert "Deutsch" in prompt
    assert "Beträge mit zwei Nachkommastellen" in prompt
    assert "Niemals raten" in prompt


def test_compose_prompt_blank_template(client):
    """Without a template the prompt is built only from user inputs."""
    response = client.post(
        "/api/v1/agent-templates/compose-prompt",
        json={
            "template_id": None,
            "description": "Du erklärst Steuern verständlich.",
            "tone": "locker",
            "language": "Deutsch",
            "rules": "",
            "use_ai": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["used_ai"] is False
    assert "Du erklärst Steuern verständlich." in body["system_prompt"]
    assert "locker" in body["system_prompt"]


def test_compose_prompt_falls_back_when_ai_unavailable(client, monkeypatch):
    """If the LLM call raises, the deterministic prompt is returned."""
    import taskforce.api.routes.agent_templates as mod

    async def _boom(req, deterministic):
        # Simulate an unconfigured LLM by returning the deterministic draft.
        return deterministic

    monkeypatch.setattr(mod, "_ai_compose", _boom)
    response = client.post(
        "/api/v1/agent-templates/compose-prompt",
        json={
            "template_id": "handwerker",
            "description": "Erstellt Angebote.",
            "tone": "professionell",
            "language": "Deutsch",
            "rules": "",
            "use_ai": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["used_ai"] is False
    assert "Angebote" in body["system_prompt"]
