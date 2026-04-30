"""
Eval / benchmark API
====================

Lightweight comparison runs across profiles. Used by the management UI
to answer "how do my profile variants compare on this mission set?".
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, status
from pydantic import BaseModel, Field, field_validator

from taskforce.api.dependencies import get_executor
from taskforce.api.errors import http_exception as _http_exception
from taskforce.application.eval_runner import (
    DEFAULT_CELL_TIMEOUT_S,
    EvalRun,
    get_eval_run_store,
    run_eval,
)

router = APIRouter()


def _strip_dedup(values: list[str]) -> list[str]:
    """Trim whitespace, drop empties, dedup while preserving order."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        cleaned = (raw or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out


class EvalRunRequest(BaseModel):
    missions: list[str] = Field(..., min_length=1, max_length=20)
    profiles: list[str] = Field(..., min_length=1, max_length=10)
    parallelism: int = Field(default=2, ge=1, le=8)
    cell_timeout_s: float = Field(
        default=DEFAULT_CELL_TIMEOUT_S, ge=5.0, le=600.0,
        description="Per-cell wall-clock cap in seconds.",
    )

    @field_validator("missions", "profiles")
    @classmethod
    def _strip_and_dedup(cls, value: list[str]) -> list[str]:
        cleaned = _strip_dedup(value)
        if not cleaned:
            raise ValueError("must contain at least one non-empty entry")
        return cleaned


class EvalRunCreated(BaseModel):
    run_id: str
    cell_count: int


@router.post(
    "/evals/runs",
    response_model=EvalRunCreated,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Kick off a comparison run",
)
async def create_eval_run(
    payload: EvalRunRequest,
    background: BackgroundTasks,
    executor=Depends(get_executor),
) -> EvalRunCreated:
    if not payload.missions or not payload.profiles:
        raise _http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_eval_request",
            message="missions and profiles must each have at least one entry",
        )
    store = get_eval_run_store()
    run = store.create(payload.missions, payload.profiles)

    async def _runner() -> None:
        try:
            await run_eval(
                run,
                executor=executor,
                parallelism=payload.parallelism,
                cell_timeout_s=payload.cell_timeout_s,
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — logged inside run_eval
            pass

    background.add_task(_runner)
    return EvalRunCreated(run_id=run.run_id, cell_count=len(run.cells))


@router.get(
    "/evals/runs",
    summary="List recent eval runs",
)
def list_eval_runs() -> dict[str, Any]:
    return {"runs": get_eval_run_store().list_runs()}


@router.get(
    "/evals/runs/{run_id}",
    summary="Return the matrix of results for a single run",
)
def get_eval_run(run_id: str) -> dict[str, Any]:
    run = get_eval_run_store().get(run_id)
    if run is None:
        raise _http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="eval_run_not_found",
            message=f"No eval run with id '{run_id}'.",
        )
    return run.to_dict()
