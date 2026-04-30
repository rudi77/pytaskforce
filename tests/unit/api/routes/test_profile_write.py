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


def test_update_preserves_unknown_top_level_keys(
    client: TestClient, user_profiles_dir: Path
) -> None:
    """A partial form patch must not nuke butler-specific top-level keys.

    Regression test for the data-loss bug found in code review: the editor
    only knows about a handful of fields, so anything else (event_sources,
    schedule_jobs, trigger_rules, learning, …) was silently deleted.
    """
    target = user_profiles_dir / "butler-shaped.yaml"
    target.write_text(
        "description: butler-shaped\n"
        "specialist: butler\n"
        "agent:\n"
        "  planning_strategy: native_react\n"
        "  max_steps: 30\n"
        "tools:\n"
        "  - python\n"
        "event_sources:\n"
        "  - type: calendar\n"
        "    poll_interval_seconds: 60\n"
        "schedule_jobs:\n"
        "  - id: morning_brief\n"
        "    cron: '0 8 * * *'\n"
        "trigger_rules:\n"
        "  - name: calendar_reminder\n"
        "    source: calendar\n"
        "learning:\n"
        "  enabled: true\n",
        encoding="utf-8",
    )

    response = client.put(
        "/api/v1/profiles/butler-shaped",
        json={
            "config": {
                "description": "butler-shaped",
                "specialist": "butler",
                "agent": {"planning_strategy": "spar", "max_steps": 25},
                "tools": ["python", "file_read"],
            }
        },
    )
    assert response.status_code == 200, response.text

    text = target.read_text(encoding="utf-8")
    assert "event_sources" in text
    assert "schedule_jobs" in text
    assert "trigger_rules" in text
    assert "learning" in text
    assert "planning_strategy: spar" in text
    assert "file_read" in text


def test_clone_framework_profile_to_user_dir(
    client: TestClient, user_profiles_dir: Path
) -> None:
    """A read-only profile clones into the user dir as a fresh, editable copy."""
    response = client.post(
        "/api/v1/profiles/default/clone",
        json={"target_name": "default-copy"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "default-copy"
    assert body["is_writable"] is True
    assert (user_profiles_dir / "default-copy.yaml").is_file()


def test_clone_unknown_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/v1/profiles/never-existed/clone",
        json={"target_name": "anything"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "profile_not_found"


def test_clone_conflict_when_target_exists(
    client: TestClient, user_profiles_dir: Path
) -> None:
    create = client.post("/api/v1/profiles", json=_minimal_payload())
    assert create.status_code == 201
    response = client.post(
        "/api/v1/profiles/default/clone",
        json={"target_name": "demo-agent"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "profile_exists"


def test_clone_rejects_reserved_target_names(client: TestClient) -> None:
    for name in ("default", "butler", "coding_agent", "rag_agent"):
        response = client.post(
            "/api/v1/profiles/default/clone",
            json={"target_name": name},
        )
        assert response.status_code == 400, name
        assert response.json()["code"] == "profile_name_reserved"


def test_clone_agent_md_source_writes_yaml_in_user_dir(
    client: TestClient, user_profiles_dir: Path, tmp_path: Path
) -> None:
    """Cloning a ``.agent.md`` source must produce an editable YAML."""
    # Create a fake agent-package config dir with a .agent.md profile.
    pkg_dir = tmp_path / "extra_pkg" / "configs"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "fake_butler.agent.md").write_text(
        "---\n"
        "specialist: butler\n"
        "tools:\n"
        "  - python\n"
        "---\n"
        "\n"
        "You are fake-butler.\n",
        encoding="utf-8",
    )
    from taskforce.application.profile_loader import register_config_dir

    register_config_dir(pkg_dir)

    response = client.post(
        "/api/v1/profiles/fake_butler/clone",
        json={"target_name": "fake_butler-copy"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "fake_butler-copy"
    assert body["is_writable"] is True

    target = user_profiles_dir / "fake_butler-copy.yaml"
    assert target.is_file()
    text = target.read_text(encoding="utf-8")
    assert "specialist: butler" in text


def test_update_explicit_null_deletes_key(
    client: TestClient, user_profiles_dir: Path
) -> None:
    """Sending a JSON ``null`` value still removes the key — explicit opt-in."""
    target = user_profiles_dir / "explicit-delete.yaml"
    target.write_text(
        "description: dropme\n"
        "specialist: demo\n"
        "tools: [python]\n"
        "extra_field: keepme\n",
        encoding="utf-8",
    )

    response = client.put(
        "/api/v1/profiles/explicit-delete",
        json={"config": {"extra_field": None, "description": "kept"}},
    )
    assert response.status_code == 200, response.text

    text = target.read_text(encoding="utf-8")
    assert "extra_field" not in text
    assert "description: kept" in text
