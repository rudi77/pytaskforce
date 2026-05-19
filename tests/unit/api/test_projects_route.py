"""Tests for the projects REST API routes."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taskforce.api.dependencies import get_project_store
from taskforce.api.routes.projects import router
from taskforce.infrastructure.persistence.file_project_store import FileProjectStore


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    from fastapi import HTTPException

    from taskforce.api.exception_handlers import taskforce_http_exception_handler

    store = FileProjectStore(work_dir=str(tmp_path / "store"))

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.add_exception_handler(HTTPException, taskforce_http_exception_handler)
    app.dependency_overrides[get_project_store] = lambda: store
    return TestClient(app)


class TestCreateProject:
    def test_scratch_mode_creates_dir_and_anchors(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        target = tmp_path / "fresh-project"

        resp = client.post(
            "/api/v1/projects",
            json={"name": "Fresh", "path": str(target), "mode": "scratch"},
        )

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "Fresh"
        assert body["path"] == str(target.resolve())
        assert body["project_id"]

        claude_md = target / "CLAUDE.md"
        assert claude_md.exists()
        claude_text = claude_md.read_text(encoding="utf-8")
        assert "## CoWork baseline rules" in claude_text
        assert "prefer relative paths from this directory" in claude_text
        assert "external path or source" in claude_text
        assert "Never delete, move, or overwrite user files" in claude_text
        assert (target / "skills").is_dir()

    def test_existing_mode_requires_existing_directory(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        missing = tmp_path / "nope"
        resp = client.post(
            "/api/v1/projects",
            json={"name": "X", "path": str(missing), "mode": "existing"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "path_not_found"

    def test_existing_mode_adds_missing_anchors(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        target = tmp_path / "imported"
        target.mkdir()
        (target / "kontext").mkdir()
        (target / "kontext" / "data.csv").write_text("a,b\n")

        resp = client.post(
            "/api/v1/projects",
            json={"name": "Imported", "path": str(target), "mode": "existing"},
        )

        assert resp.status_code == 201
        assert (target / "CLAUDE.md").exists()
        assert (target / "skills").is_dir()
        assert (target / "kontext" / "data.csv").exists(), (
            "import must not touch user files"
        )

    def test_existing_mode_does_not_overwrite_claude_md(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        target = tmp_path / "with-existing-claude"
        target.mkdir()
        (target / "CLAUDE.md").write_text("# Hands off")

        resp = client.post(
            "/api/v1/projects",
            json={"name": "X", "path": str(target), "mode": "existing"},
        )
        assert resp.status_code == 201
        assert (
            (target / "CLAUDE.md").read_text(encoding="utf-8") == "# Hands off"
        )

    def test_duplicate_path_returns_409(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        client.post(
            "/api/v1/projects",
            json={"name": "First", "path": str(target), "mode": "scratch"},
        )
        resp = client.post(
            "/api/v1/projects",
            json={"name": "Second", "path": str(target), "mode": "scratch"},
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "project_create_failed"


class TestListAndGetProject:
    def test_list_returns_created(self, client: TestClient, tmp_path: Path) -> None:
        client.post(
            "/api/v1/projects",
            json={"name": "A", "path": str(tmp_path / "a")},
        )
        client.post(
            "/api/v1/projects",
            json={"name": "B", "path": str(tmp_path / "b")},
        )
        resp = client.get("/api/v1/projects")
        assert resp.status_code == 200
        body = resp.json()
        assert {p["name"] for p in body} == {"A", "B"}

    def test_get_unknown_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/v1/projects/missing")
        assert resp.status_code == 404
        assert resp.json()["code"] == "project_not_found"


class TestDeleteProject:
    def test_delete_then_get_returns_404(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        created = client.post(
            "/api/v1/projects",
            json={"name": "P", "path": str(target)},
        ).json()
        pid = created["project_id"]

        delete_resp = client.delete(f"/api/v1/projects/{pid}")
        assert delete_resp.status_code == 204

        get_resp = client.get(f"/api/v1/projects/{pid}")
        assert get_resp.status_code == 404

        # Directory must still exist on disk.
        assert target.exists()

    def test_delete_unknown_returns_404(self, client: TestClient) -> None:
        resp = client.delete("/api/v1/projects/does-not-exist")
        assert resp.status_code == 404
