"""File-backed ``StandingGoalStoreProtocol`` implementation.

Stores every goal as a single JSON document under
``<work_dir>/standing_goals.json``. Writes are atomic (tempfile +
``os.replace``) and serialized through an ``asyncio.Lock`` so two
``mark_evaluated`` calls cannot race even when the evaluator runs in
parallel with a CLI ``add``.

Pattern matches the existing ``FileAgentState`` and ``FileJobStore`` —
no SQLite for an inherently small dataset (a butler typically has
fewer than a dozen standing goals).
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from taskforce.core.domain.standing_goal import StandingGoal

logger = structlog.get_logger(__name__)


class FileStandingGoalStore:
    """JSON-file backed standing-goal store."""

    def __init__(self, work_dir: str | os.PathLike[str]) -> None:
        self._path = Path(work_dir) / "standing_goals.json"
        self._lock = asyncio.Lock()

    @property
    def path(self) -> Path:
        return self._path

    async def list(self) -> list[StandingGoal]:
        async with self._lock:
            return self._read()

    async def get(self, goal_id: str) -> StandingGoal | None:
        for goal in await self.list():
            if goal.goal_id == goal_id:
                return goal
        return None

    async def add(self, goal: StandingGoal) -> StandingGoal:
        async with self._lock:
            goals = self._read()
            if any(g.goal_id == goal.goal_id for g in goals):
                raise ValueError(
                    f"Standing goal {goal.goal_id!r} already exists. "
                    "Use update() to modify an existing goal."
                )
            goals.append(goal)
            self._write(goals)
            logger.info(
                "standing_goal_store.added",
                goal_id=goal.goal_id,
                description=goal.description[:60],
            )
        return goal

    async def update(self, goal: StandingGoal) -> StandingGoal:
        async with self._lock:
            goals = self._read()
            for idx, existing in enumerate(goals):
                if existing.goal_id == goal.goal_id:
                    goals[idx] = goal
                    self._write(goals)
                    logger.info("standing_goal_store.updated", goal_id=goal.goal_id)
                    return goal
            raise KeyError(f"No standing goal with id {goal.goal_id!r}")

    async def delete(self, goal_id: str) -> bool:
        async with self._lock:
            goals = self._read()
            kept = [g for g in goals if g.goal_id != goal_id]
            if len(kept) == len(goals):
                return False
            self._write(kept)
            logger.info("standing_goal_store.deleted", goal_id=goal_id)
            return True

    async def mark_evaluated(
        self,
        goal_id: str,
        evaluated_at: datetime,
        action_taken: str,
    ) -> None:
        async with self._lock:
            goals = self._read()
            for idx, existing in enumerate(goals):
                if existing.goal_id != goal_id:
                    continue
                existing.last_evaluated_at = evaluated_at
                existing.last_action_taken = action_taken
                goals[idx] = existing
                self._write(goals)
                return
            logger.warning(
                "standing_goal_store.mark_evaluated_unknown_id",
                goal_id=goal_id,
            )

    # --- internal -----------------------------------------------------------

    def _read(self) -> list[StandingGoal]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.error(
                "standing_goal_store.corrupt_file",
                path=str(self._path),
                error=str(exc),
            )
            return []
        return [StandingGoal.from_dict(item) for item in data.get("goals", [])]

    def _write(self, goals: list[StandingGoal]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "schema_version": 1,
            "goals": [g.to_dict() for g in goals],
        }
        # Atomic write: tempfile in the same dir, then rename.
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(self._path.parent),
            prefix=".standing_goals.",
            suffix=".json.tmp",
            delete=False,
        ) as tmp:
            json.dump(payload, tmp, indent=2, sort_keys=True)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, self._path)
