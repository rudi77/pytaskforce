"""
Eval Runner
===========

Lightweight in-process benchmark service used by the management UI's
"compare profiles" page.

Each run consists of an ordered list of missions executed against a
selection of profiles. Results contain final status, latency, and the
token/cost figures recorded by ``TokenLedger`` for the session, so the
UI can render a comparison matrix.

This is intentionally not the same thing as the inspect-ai based eval
suite — it lives in-process so users can iterate quickly during
profile-tuning without touching ``inspect_ai``.
"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class EvalCellResult:
    profile: str
    mission: str
    status: str  # pending | running | completed | failed | cancelled
    started_at: datetime | None = None
    finished_at: datetime | None = None
    latency_ms: int | None = None
    final_message: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None
    session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "mission": self.mission,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "latency_ms": self.latency_ms,
            "final_message": self.final_message,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_usd": self.cost_usd,
            "error": self.error,
            "session_id": self.session_id,
        }


@dataclass
class EvalRun:
    run_id: str
    missions: list[str]
    profiles: list[str]
    created_at: datetime
    cells: list[EvalCellResult] = field(default_factory=list)
    finished: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "missions": self.missions,
            "profiles": self.profiles,
            "created_at": self.created_at.isoformat(),
            "finished": self.finished,
            "cells": [c.to_dict() for c in self.cells],
        }


class EvalRunStore:
    """LRU-bounded in-memory store of recent eval runs."""

    def __init__(self, max_runs: int = 20) -> None:
        self._runs: OrderedDict[str, EvalRun] = OrderedDict()
        self._lock = threading.Lock()
        self._max_runs = max_runs

    def create(self, missions: list[str], profiles: list[str]) -> EvalRun:
        run_id = uuid.uuid4().hex[:16]
        cells = [
            EvalCellResult(profile=p, mission=m, status="pending")
            for m in missions
            for p in profiles
        ]
        run = EvalRun(
            run_id=run_id,
            missions=list(missions),
            profiles=list(profiles),
            created_at=datetime.now(UTC),
            cells=cells,
        )
        with self._lock:
            self._runs[run_id] = run
            self._runs.move_to_end(run_id)
            while len(self._runs) > self._max_runs:
                self._runs.popitem(last=False)
        return run

    def get(self, run_id: str) -> EvalRun | None:
        with self._lock:
            return self._runs.get(run_id)

    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "run_id": r.run_id,
                    "missions": r.missions,
                    "profiles": r.profiles,
                    "created_at": r.created_at.isoformat(),
                    "finished": r.finished,
                    "cell_count": len(r.cells),
                    "completed_cells": sum(
                        1 for c in r.cells if c.status in {"completed", "failed", "cancelled"}
                    ),
                }
                for r in reversed(self._runs.values())
            ]


_store: EvalRunStore | None = None


def get_eval_run_store() -> EvalRunStore:
    global _store
    if _store is None:
        _store = EvalRunStore()
    return _store


def reset_eval_run_store() -> None:
    global _store
    _store = None


async def run_eval(
    run: EvalRun,
    *,
    executor: Any,
    parallelism: int = 2,
) -> None:
    """Execute every (mission, profile) cell and update the run in place."""
    semaphore = asyncio.Semaphore(max(1, parallelism))

    async def _execute(cell: EvalCellResult) -> None:
        async with semaphore:
            cell.status = "running"
            cell.started_at = datetime.now(UTC)
            start = time.perf_counter()
            try:
                result = await executor.execute_mission(
                    mission=cell.mission,
                    profile=cell.profile,
                )
                cell.session_id = getattr(result, "session_id", None)
                cell.final_message = (
                    getattr(result, "final_message", "") or ""
                )[:500]
                status = getattr(result, "status_value", None) or getattr(
                    result, "status", "completed"
                )
                cell.status = "completed" if status in {"completed", "complete"} else str(status)
            except Exception as exc:  # noqa: BLE001
                cell.status = "failed"
                cell.error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "eval_cell_failed",
                    run_id=run.run_id,
                    profile=cell.profile,
                    error=cell.error,
                )
            finally:
                cell.finished_at = datetime.now(UTC)
                cell.latency_ms = int((time.perf_counter() - start) * 1000)
                _harvest_token_usage(cell)

    await asyncio.gather(*(_execute(c) for c in run.cells))
    run.finished = True


def _harvest_token_usage(cell: EvalCellResult) -> None:
    """Best-effort: pull token + cost figures from the TokenLedger."""
    if not cell.session_id:
        return
    try:
        from taskforce.application.token_ledger import get_token_ledger

        ledger = get_token_ledger()
        # ``per_session`` is not part of the public API yet — fall back to
        # iterating recent calls if unavailable.
        if hasattr(ledger, "per_session"):
            agg = ledger.per_session(cell.session_id)
        else:  # pragma: no cover — defensive
            agg = None
        if agg:
            cell.prompt_tokens = int(agg.get("prompt_tokens", 0) or 0)
            cell.completion_tokens = int(agg.get("completion_tokens", 0) or 0)
            cell.cost_usd = float(agg.get("cost_usd", 0.0) or 0.0)
    except Exception:  # noqa: BLE001 — non-fatal
        logger.debug("eval_token_harvest_failed", session_id=cell.session_id)
