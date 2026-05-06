"""REST CRUD + evaluate-now route for standing goals."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taskforce.api.dependencies import (
    set_goal_evaluator,
    set_standing_goal_store,
)
from taskforce.api.routes import standing_goals
from taskforce.infrastructure.persistence.file_standing_goal_store import (
    FileStandingGoalStore,
)


@pytest.fixture()
def app(tmp_path) -> FastAPI:
    set_standing_goal_store(FileStandingGoalStore(work_dir=str(tmp_path)))
    app = FastAPI()
    app.include_router(standing_goals.router, prefix="/api/v1")
    yield app
    set_standing_goal_store(None)
    set_goal_evaluator(None)


def test_create_list_get_round_trip(app: FastAPI) -> None:
    client = TestClient(app)

    create = client.post(
        "/api/v1/standing-goals",
        json={
            "description": "Weekly summary",
            "evaluation_prompt": "Should we send a weekly summary now?",
            "frequency": "0 9 * * 1",
            "priority": 3,
        },
    )
    assert create.status_code == 201
    goal_id = create.json()["goal_id"]

    listed = client.get("/api/v1/standing-goals")
    assert listed.status_code == 200
    assert any(g["goal_id"] == goal_id for g in listed.json())

    one = client.get(f"/api/v1/standing-goals/{goal_id}")
    assert one.status_code == 200
    assert one.json()["priority"] == 3


def test_get_unknown_returns_404(app: FastAPI) -> None:
    response = TestClient(app).get("/api/v1/standing-goals/does-not-exist")
    assert response.status_code == 404


def test_patch_partial_update(app: FastAPI) -> None:
    client = TestClient(app)
    create = client.post(
        "/api/v1/standing-goals",
        json={
            "description": "x",
            "evaluation_prompt": "y",
            "frequency": "* * * * *",
        },
    )
    goal_id = create.json()["goal_id"]

    response = client.patch(
        f"/api/v1/standing-goals/{goal_id}",
        json={"enabled": False, "priority": 1},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["priority"] == 1
    assert body["description"] == "x"  # untouched


def test_delete_returns_204_then_404(app: FastAPI) -> None:
    client = TestClient(app)
    create = client.post(
        "/api/v1/standing-goals",
        json={
            "description": "x",
            "evaluation_prompt": "y",
            "frequency": "* * * * *",
        },
    )
    goal_id = create.json()["goal_id"]
    assert client.delete(f"/api/v1/standing-goals/{goal_id}").status_code == 204
    assert client.delete(f"/api/v1/standing-goals/{goal_id}").status_code == 404


def test_evaluate_now_503_without_evaluator(app: FastAPI) -> None:
    client = TestClient(app)
    create = client.post(
        "/api/v1/standing-goals",
        json={
            "description": "x",
            "evaluation_prompt": "y",
            "frequency": "* * * * *",
        },
    )
    goal_id = create.json()["goal_id"]
    response = client.post(f"/api/v1/standing-goals/{goal_id}/evaluate-now")
    assert response.status_code == 503


def test_evaluate_now_with_evaluator(app: FastAPI) -> None:
    client = TestClient(app)
    create = client.post(
        "/api/v1/standing-goals",
        json={
            "description": "x",
            "evaluation_prompt": "y",
            "frequency": "* * * * *",
        },
    )
    goal_id = create.json()["goal_id"]

    class _StubEvaluator:
        async def evaluate_goal(self, gid: str) -> dict[str, Any] | None:
            if gid != goal_id:
                return None
            return {"goal_id": gid, "acted": True, "rationale": "stub"}

    set_goal_evaluator(_StubEvaluator())
    response = client.post(f"/api/v1/standing-goals/{goal_id}/evaluate-now")
    assert response.status_code == 202
    assert response.json()["acted"] is True
