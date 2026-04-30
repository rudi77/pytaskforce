"""Route-level tests for the eval-runner API."""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from taskforce.api.dependencies import get_executor
from taskforce.api.server import create_app
from taskforce.application.eval_runner import (
    get_eval_run_store,
    reset_eval_run_store,
)


class _Result:
    def __init__(self, session_id: str = "sess") -> None:
        self.session_id = session_id
        self.status = "completed"
        self.status_value = "completed"
        self.final_message = "ok"


@pytest.fixture
def fake_executor() -> Any:
    executor = AsyncMock()
    executor.execute_mission = AsyncMock(return_value=_Result())
    return executor


@pytest.fixture
def client(fake_executor) -> TestClient:
    reset_eval_run_store()
    app = create_app()
    app.dependency_overrides[get_executor] = lambda: fake_executor
    yield TestClient(app)
    reset_eval_run_store()


def test_create_run_strips_and_dedups_inputs(client: TestClient) -> None:
    response = client.post(
        "/api/v1/evals/runs",
        json={
            "missions": ["  hello", "hello", "", "  ", "ok"],
            "profiles": ["a", " a", "b"],
            "parallelism": 1,
            "cell_timeout_s": 5,
        },
    )
    assert response.status_code == 202, response.text
    body = response.json()
    # 2 missions × 2 profiles = 4 cells.
    assert body["cell_count"] == 4

    # Wait briefly for the background task to materialise the run.
    deadline = time.time() + 2.0
    detail = None
    while time.time() < deadline:
        detail = client.get(f"/api/v1/evals/runs/{body['run_id']}")
        if detail.status_code == 200 and detail.json().get("finished"):
            break
        time.sleep(0.05)
    assert detail is not None and detail.status_code == 200
    payload = detail.json()
    assert payload["missions"] == ["hello", "ok"]
    assert payload["profiles"] == ["a", "b"]


def test_create_run_rejects_all_empty_missions(client: TestClient) -> None:
    response = client.post(
        "/api/v1/evals/runs",
        json={"missions": ["", " "], "profiles": ["a"]},
    )
    assert response.status_code == 422


def test_get_unknown_run_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/evals/runs/never-existed")
    assert response.status_code == 404
    assert response.json()["code"] == "eval_run_not_found"


def test_run_drives_executor_calls(
    client: TestClient, fake_executor
) -> None:
    response = client.post(
        "/api/v1/evals/runs",
        json={
            "missions": ["mission-1"],
            "profiles": ["p1", "p2"],
            "parallelism": 2,
            "cell_timeout_s": 5,
        },
    )
    assert response.status_code == 202
    run_id = response.json()["run_id"]

    deadline = time.time() + 2.0
    while time.time() < deadline:
        detail = client.get(f"/api/v1/evals/runs/{run_id}")
        if detail.status_code == 200 and detail.json().get("finished"):
            break
        time.sleep(0.05)

    assert fake_executor.execute_mission.await_count == 2
    body = detail.json()
    assert all(cell["status"] == "completed" for cell in body["cells"])
