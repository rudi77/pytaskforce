"""Tests for the workspace browse route (Cowork-parity @mention picker)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taskforce.api.routes.workspace import router


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a small fake project tree and point the route at it.

    Layout:

        <root>/
        ├── README.md
        ├── src/
        │   ├── foo.py
        │   └── bar.py
        ├── tests/
        │   └── test_foo.py
        ├── .git/HEAD               # must be hidden by default
        ├── node_modules/pkg.js     # must be hidden by default
        └── .env                    # hidden until include_hidden=true
    """
    (tmp_path / "README.md").write_text("hi")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text("# foo\n")
    (tmp_path / "src" / "bar.py").write_text("# bar\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_foo.py").write_text("def test(): ...\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.js").write_text("x")
    (tmp_path / ".env").write_text("SECRET=1")

    monkeypatch.setenv("TASKFORCE_WORKSPACE_ROOT", str(tmp_path))
    # Make sure no inherited excludes from a parent shell mess up tests.
    monkeypatch.delenv("TASKFORCE_WORKSPACE_EXCLUDE", raising=False)
    return tmp_path


@pytest.fixture
def client(workspace: Path) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


class TestWorkspaceBrowseRoot:
    def test_lists_root_directory_top_level_only(self, client, workspace):
        resp = client.get("/api/v1/workspace/browse")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["root"] == str(workspace.resolve())
        assert body["path"] == ""

        names = {e["name"] for e in body["entries"]}
        # Visible: regular files and dirs.
        assert {"README.md", "src", "tests"} <= names
        # Hidden by default: VCS / build dirs / dotfiles.
        assert ".git" not in names
        assert "node_modules" not in names
        assert ".env" not in names

    def test_dirs_appear_before_files(self, client):
        resp = client.get("/api/v1/workspace/browse")
        entries = resp.json()["entries"]
        types_in_order = [e["type"] for e in entries]
        # No "file" should come before any "dir" — i.e. once we see a
        # file, everything after must also be a file.
        first_file_idx = next(
            (i for i, t in enumerate(types_in_order) if t == "file"), None
        )
        if first_file_idx is not None:
            assert all(t == "file" for t in types_in_order[first_file_idx:])

    def test_file_entries_include_size(self, client):
        resp = client.get("/api/v1/workspace/browse")
        readme = next(e for e in resp.json()["entries"] if e["name"] == "README.md")
        assert readme["type"] == "file"
        assert readme["size"] == 2  # "hi"

    def test_dir_entries_have_null_size(self, client):
        resp = client.get("/api/v1/workspace/browse")
        src = next(e for e in resp.json()["entries"] if e["name"] == "src")
        assert src["type"] == "dir"
        assert src["size"] is None


class TestWorkspaceBrowseSubdirs:
    def test_drilling_into_subdir(self, client):
        resp = client.get("/api/v1/workspace/browse", params={"path": "src"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["path"] == "src"
        names = {e["name"] for e in body["entries"]}
        assert names == {"foo.py", "bar.py"}
        # Paths are relative to ROOT, not to the listed dir, so the picker
        # can insert them directly as ``@src/foo.py``.
        paths = {e["path"] for e in body["entries"]}
        assert paths == {"src/foo.py", "src/bar.py"}

    def test_returns_404_for_unknown_dir(self, client):
        resp = client.get("/api/v1/workspace/browse", params={"path": "no-such-dir"})
        assert resp.status_code == 404

    def test_returns_400_when_path_is_a_file(self, client):
        resp = client.get("/api/v1/workspace/browse", params={"path": "README.md"})
        assert resp.status_code == 400


class TestWorkspaceBrowseSecurity:
    def test_rejects_parent_traversal(self, client):
        resp = client.get("/api/v1/workspace/browse", params={"path": "../"})
        assert resp.status_code == 400
        # ErrorResponse is flat: {code, message, details}.
        assert resp.json()["detail"]["code"] == "invalid_path"

    def test_rejects_absolute_outside_path(self, client):
        # Leading slash strips and resolves relative to root — but the
        # absolute path "/etc" would resolve outside; we test the literal
        # absolute form too.
        resp = client.get("/api/v1/workspace/browse", params={"path": "/etc"})
        # Either treated as relative "etc" (404 inside workspace) or
        # rejected as traversal — both are acceptable; what we MUST never
        # do is return /etc's contents.
        assert resp.status_code in (400, 404)
        body = resp.json()
        if resp.status_code == 200:  # pragma: no cover — defensive
            pytest.fail(f"leaked /etc listing: {body}")


class TestWorkspaceBrowseFiltering:
    def test_query_filter_matches_substring_case_insensitively(self, client):
        resp = client.get("/api/v1/workspace/browse", params={"q": "READ"})
        names = [e["name"] for e in resp.json()["entries"]]
        assert names == ["README.md"]

    def test_query_can_narrow_a_subdir_listing(self, client):
        resp = client.get(
            "/api/v1/workspace/browse", params={"path": "src", "q": "foo"}
        )
        names = {e["name"] for e in resp.json()["entries"]}
        assert names == {"foo.py"}

    def test_include_hidden_surfaces_dotfiles(self, client):
        resp = client.get(
            "/api/v1/workspace/browse", params={"include_hidden": "true"}
        )
        names = {e["name"] for e in resp.json()["entries"]}
        assert ".env" in names
        # .git is in the hardcoded denylist — include_hidden does NOT
        # override that (VCS internals are useless for prompt referencing).
        assert ".git" not in names

    def test_truncation_flag_set_when_over_limit(self, client, workspace):
        # Stuff a directory full of files and hit it with a tight limit.
        big = workspace / "big"
        big.mkdir()
        for i in range(20):
            (big / f"f{i:02d}.txt").write_text("x")
        resp = client.get(
            "/api/v1/workspace/browse",
            params={"path": "big", "limit": 5},
        )
        body = resp.json()
        assert body["truncated"] is True
        assert len(body["entries"]) == 5


class TestWorkspaceExclude:
    def test_extra_excludes_via_env(
        self, client, workspace, monkeypatch: pytest.MonkeyPatch
    ):
        (workspace / "secrets").mkdir()
        (workspace / "secrets" / "key.pem").write_text("x")
        monkeypatch.setenv("TASKFORCE_WORKSPACE_EXCLUDE", "secrets")

        resp = client.get("/api/v1/workspace/browse")
        names = {e["name"] for e in resp.json()["entries"]}
        assert "secrets" not in names

    def test_default_excludes_still_apply_with_extra_env(
        self, client, workspace, monkeypatch: pytest.MonkeyPatch
    ):
        """Extra env-var excludes must ADD to the defaults, not replace
        them — otherwise a misconfiguration could re-expose .git."""
        monkeypatch.setenv("TASKFORCE_WORKSPACE_EXCLUDE", "only-this")
        resp = client.get("/api/v1/workspace/browse")
        names = {e["name"] for e in resp.json()["entries"]}
        assert ".git" not in names
        assert "node_modules" not in names


def test_falls_back_to_cwd_when_env_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Without ``TASKFORCE_WORKSPACE_ROOT`` we use ``cwd`` — the docs
    promise this so single-tenant installs work without configuration."""
    (tmp_path / "marker.txt").write_text("ok")
    monkeypatch.delenv("TASKFORCE_WORKSPACE_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)
    resp = client.get("/api/v1/workspace/browse")
    assert resp.status_code == 200
    body = resp.json()
    assert body["root"] == str(tmp_path.resolve())
    assert any(e["name"] == "marker.txt" for e in body["entries"])
