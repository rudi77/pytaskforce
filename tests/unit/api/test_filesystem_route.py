"""Tests for the filesystem browse REST API route."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from taskforce.api.exception_handlers import taskforce_http_exception_handler
from taskforce.api.routes.filesystem import router


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.add_exception_handler(HTTPException, taskforce_http_exception_handler)
    return TestClient(app)


def test_browse_lists_subdirectories(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    (tmp_path / "a_file.txt").write_text("ignored")

    resp = client.get(f"/api/v1/filesystem/browse?path={tmp_path}")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    names = [e["name"] for e in body["entries"]]
    assert names == ["alpha", "beta"]
    assert body["path"] == str(tmp_path.resolve())
    assert body["parent"] == str(tmp_path.resolve().parent)


def test_browse_filters_hidden_and_noise_by_default(
    client: TestClient, tmp_path: Path
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / ".hidden").mkdir()

    resp = client.get(f"/api/v1/filesystem/browse?path={tmp_path}")

    assert resp.status_code == 200
    names = [e["name"] for e in resp.json()["entries"]]
    assert names == ["src"]


def test_browse_include_hidden_shows_dotfiles(
    client: TestClient, tmp_path: Path
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / ".config").mkdir()

    resp = client.get(
        f"/api/v1/filesystem/browse?path={tmp_path}&include_hidden=true"
    )

    assert resp.status_code == 200
    names = [e["name"] for e in resp.json()["entries"]]
    assert ".config" in names
    assert "src" in names


def test_browse_strips_surrounding_quotes(
    client: TestClient, tmp_path: Path
) -> None:
    (tmp_path / "child").mkdir()
    quoted = f'"{tmp_path}"'

    resp = client.get("/api/v1/filesystem/browse", params={"path": quoted})

    assert resp.status_code == 200
    assert resp.json()["path"] == str(tmp_path.resolve())


def test_browse_missing_path_returns_404(client: TestClient, tmp_path: Path) -> None:
    missing = tmp_path / "nope" / "really_nope"

    resp = client.get(f"/api/v1/filesystem/browse?path={missing}")

    assert resp.status_code == 404
    assert resp.json()["code"] == "path_not_found"
    assert resp.json()["details"]["path"]


def test_browse_file_path_returns_400(client: TestClient, tmp_path: Path) -> None:
    file_path = tmp_path / "a.txt"
    file_path.write_text("hi")

    resp = client.get(f"/api/v1/filesystem/browse?path={file_path}")

    assert resp.status_code == 400
    assert resp.json()["code"] == "not_a_directory"


def test_browse_empty_path_defaults_to_home(client: TestClient) -> None:
    resp = client.get("/api/v1/filesystem/browse")

    assert resp.status_code == 200
    assert resp.json()["path"] == str(Path.home().resolve())


@pytest.mark.skipif(os.name != "nt", reason="Windows-only drive enumeration")
def test_browse_reports_drives_on_windows(client: TestClient) -> None:
    resp = client.get("/api/v1/filesystem/browse")

    assert resp.status_code == 200
    body = resp.json()
    assert body["is_windows"] is True
    assert body["drives"]  # at least the system drive


@pytest.mark.skipif(os.name == "nt", reason="POSIX-only")
def test_browse_no_drives_on_posix(client: TestClient) -> None:
    resp = client.get("/api/v1/filesystem/browse")

    assert resp.status_code == 200
    body = resp.json()
    assert body["is_windows"] is False
    assert body["drives"] == []
