"""Tests for the file upload/download API."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from taskforce.api.server import create_app
from taskforce.application import file_storage


@pytest.fixture
def storage_root(tmp_path: Path) -> Path:
    target = tmp_path / "uploads"
    target.mkdir()
    file_storage.reset_root_for_tests(target)
    yield target
    file_storage.reset_file_storage()


@pytest.fixture
def client(storage_root: Path) -> TestClient:
    return TestClient(create_app())


def test_upload_get_meta_download_delete(client: TestClient, storage_root: Path) -> None:
    payload = b"Hello attachments!"
    upload = client.post(
        "/api/v1/files",
        files={"file": ("hello.txt", payload, "text/plain")},
    )
    assert upload.status_code == 201, upload.text
    body = upload.json()
    file_id = body["file_id"]
    assert body["name"] == "hello.txt"
    assert body["size"] == len(payload)
    assert body["mime"] == "text/plain"
    assert len(body["sha256"]) == 64

    meta = client.get(f"/api/v1/files/{file_id}/meta")
    assert meta.status_code == 200
    assert meta.json()["file_id"] == file_id

    download = client.get(f"/api/v1/files/{file_id}")
    assert download.status_code == 200
    assert download.content == payload
    assert download.headers["content-type"].startswith("text/plain")
    assert "hello.txt" in download.headers["content-disposition"]

    delete = client.delete(f"/api/v1/files/{file_id}")
    assert delete.status_code == 204

    missing = client.get(f"/api/v1/files/{file_id}/meta")
    assert missing.status_code == 404


def test_upload_too_large_returns_413(
    client: TestClient, storage_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file_storage.reset_file_storage()
    monkeypatch.setenv("TASKFORCE_UPLOAD_MAX_MB", "1")
    file_storage._storage = file_storage.FileStorage(root=storage_root)  # type: ignore[attr-defined]

    big = b"x" * (2 * 1024 * 1024)
    response = client.post(
        "/api/v1/files",
        files={"file": ("big.bin", big, "application/octet-stream")},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "file_too_large"


def test_download_unknown_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/files/00000000000000000000000000000000")
    assert response.status_code == 404
