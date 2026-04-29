"""Tests for the profile create/update/delete endpoints (Phase 3)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from taskforce.api.server import create_app


@pytest.fixture
def user_profiles_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect user profile writes to a temporary directory."""
    target = tmp_path / "user_profiles"
    target.mkdir()
    monkeypatch.setenv("TASKFORCE_USER_PROFILES_DIR", str(target))
    # Reset state that leaks across tests via module globals.
    from taskforce.application import bootstrap_config_dirs as bcd
    from taskforce.application.profile_loader import clear_extra_config_dirs

    bcd._initialized = False  # type: ignore[attr-defined]
    clear_extra_config_dirs()
    yield target
    clear_extra_config_dirs()
    bcd._initialized = False  # type: ignore[attr-defined]


@pytest.fixture
def client(user_profiles_dir: Path) -> TestClient:
    return TestClient(create_app())


def _minimal_payload() -> dict:
    return {
        "name": "demo-agent",
        "config": {
            "description": "Demo agent for tests",
            "specialist": "demo",
            "agent": {"planning_strategy": "native_react", "max_steps": 10},
            "tools": ["python", "file_read"],
            "llm": {"default_model": "main"},
            "persistence": {"type": "file", "work_dir": ".taskforce_demo"},
        },
    }


def test_create_profile_writes_yaml(client: TestClient, user_profiles_dir: Path) -> None:
    response = client.post("/api/v1/profiles", json=_minimal_payload())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "demo-agent"
    assert body["is_writable"] is True
    assert body["specialist"] == "demo"

    target = user_profiles_dir / "demo-agent.yaml"
    assert target.is_file()
    text = target.read_text(encoding="utf-8")
    assert "specialist: demo" in text


def test_create_profile_conflict(client: TestClient) -> None:
    payload = _minimal_payload()
    first = client.post("/api/v1/profiles", json=payload)
    assert first.status_code == 201
    second = client.post("/api/v1/profiles", json=payload)
    assert second.status_code == 409
    assert second.json()["code"] == "profile_exists"


def test_update_preserves_comments(
    client: TestClient, user_profiles_dir: Path
) -> None:
    """Round-trip an existing file with comments and confirm they survive."""
    target = user_profiles_dir / "with-comments.yaml"
    target.write_text(
        "# top comment\n"
        "description: comment-test  # inline\n"
        "specialist: demo\n"
        "agent:\n"
        "  # planning section\n"
        "  planning_strategy: native_react\n"
        "  max_steps: 10\n"
        "tools:\n"
        "  - python\n",
        encoding="utf-8",
    )

    response = client.put(
        "/api/v1/profiles/with-comments",
        json={
            "config": {
                "description": "comment-test",
                "specialist": "demo",
                "agent": {"planning_strategy": "spar", "max_steps": 25},
                "tools": ["python", "file_read"],
            }
        },
    )
    assert response.status_code == 200, response.text

    text = target.read_text(encoding="utf-8")
    assert "# top comment" in text
    assert "# inline" in text
    assert "# planning section" in text
    assert "planning_strategy: spar" in text
    assert "file_read" in text


def test_update_unknown_returns_404(client: TestClient) -> None:
    response = client.put(
        "/api/v1/profiles/never-written",
        json={"config": {"description": "x"}},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "profile_not_found"


def test_update_framework_profile_is_forbidden(client: TestClient) -> None:
    response = client.put(
        "/api/v1/profiles/default",
        json={"config": {"description": "noop"}},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "profile_read_only"


def test_delete_user_profile(client: TestClient, user_profiles_dir: Path) -> None:
    create = client.post("/api/v1/profiles", json=_minimal_payload())
    assert create.status_code == 201

    delete = client.delete("/api/v1/profiles/demo-agent")
    assert delete.status_code == 204
    assert not (user_profiles_dir / "demo-agent.yaml").exists()


def test_delete_unknown_returns_404(client: TestClient) -> None:
    response = client.delete("/api/v1/profiles/never-existed")
    assert response.status_code == 404


def test_create_profile_invalid_payload(client: TestClient) -> None:
    response = client.post(
        "/api/v1/profiles",
        json={
            "name": "invalid-tools",
            "config": {"tools": [{"type": "WebSearchTool"}]},
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == "profile_invalid"
