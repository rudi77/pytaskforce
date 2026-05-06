"""FileStandingGoalStore — CRUD + atomic write + concurrent mark_evaluated."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from taskforce.core.domain.standing_goal import StandingGoal
from taskforce.infrastructure.persistence.file_standing_goal_store import (
    FileStandingGoalStore,
)


@pytest.fixture()
def store(tmp_path: Path) -> FileStandingGoalStore:
    return FileStandingGoalStore(work_dir=str(tmp_path))


def _make_goal(prefix: str = "g") -> StandingGoal:
    return StandingGoal(
        description=f"{prefix}-description",
        evaluation_prompt=f"{prefix}-prompt",
        frequency="0 9 * * 1",
    )


@pytest.mark.asyncio
async def test_add_get_list_round_trip(store: FileStandingGoalStore) -> None:
    goal = _make_goal()
    await store.add(goal)
    fetched = await store.get(goal.goal_id)
    assert fetched == goal
    assert [g.goal_id for g in await store.list()] == [goal.goal_id]


@pytest.mark.asyncio
async def test_add_duplicate_raises(store: FileStandingGoalStore) -> None:
    goal = _make_goal()
    await store.add(goal)
    with pytest.raises(ValueError, match="already exists"):
        await store.add(goal)


@pytest.mark.asyncio
async def test_update_replaces_existing(store: FileStandingGoalStore) -> None:
    goal = _make_goal()
    await store.add(goal)
    goal.description = "updated"
    await store.update(goal)
    fetched = await store.get(goal.goal_id)
    assert fetched is not None
    assert fetched.description == "updated"


@pytest.mark.asyncio
async def test_update_unknown_raises(store: FileStandingGoalStore) -> None:
    with pytest.raises(KeyError):
        await store.update(_make_goal())


@pytest.mark.asyncio
async def test_delete_returns_true_only_when_present(
    store: FileStandingGoalStore,
) -> None:
    goal = _make_goal()
    await store.add(goal)
    assert await store.delete(goal.goal_id) is True
    assert await store.delete(goal.goal_id) is False
    assert await store.list() == []


@pytest.mark.asyncio
async def test_mark_evaluated_persists_action(store: FileStandingGoalStore) -> None:
    goal = _make_goal()
    await store.add(goal)
    when = datetime(2026, 5, 6, 9, 0, tzinfo=UTC)
    await store.mark_evaluated(goal.goal_id, when, "sent summary")
    fetched = await store.get(goal.goal_id)
    assert fetched is not None
    assert fetched.last_evaluated_at == when
    assert fetched.last_action_taken == "sent summary"


@pytest.mark.asyncio
async def test_concurrent_mark_evaluated_does_not_lose_writes(
    store: FileStandingGoalStore,
) -> None:
    """Two concurrent updates must both land — guarded by the asyncio lock."""
    goal_a = _make_goal("a")
    goal_b = _make_goal("b")
    await store.add(goal_a)
    await store.add(goal_b)
    when = datetime(2026, 5, 6, 9, 0, tzinfo=UTC)

    await asyncio.gather(
        store.mark_evaluated(goal_a.goal_id, when, "a-action"),
        store.mark_evaluated(goal_b.goal_id, when, "b-action"),
    )

    fetched = {g.goal_id: g for g in await store.list()}
    assert fetched[goal_a.goal_id].last_action_taken == "a-action"
    assert fetched[goal_b.goal_id].last_action_taken == "b-action"


@pytest.mark.asyncio
async def test_atomic_write_leaves_no_temp_files(
    tmp_path: Path,
    store: FileStandingGoalStore,
) -> None:
    await store.add(_make_goal())
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".standing_goals.")]
    assert leftovers == []


@pytest.mark.asyncio
async def test_corrupt_file_returns_empty_list_not_crash(
    tmp_path: Path,
) -> None:
    """A corrupt JSON file should be logged and treated as empty."""
    path = tmp_path / "standing_goals.json"
    path.write_text("{not json", encoding="utf-8")
    store = FileStandingGoalStore(work_dir=str(tmp_path))
    assert await store.list() == []


@pytest.mark.asyncio
async def test_persisted_data_is_readable_json(
    tmp_path: Path,
    store: FileStandingGoalStore,
) -> None:
    goal = _make_goal()
    await store.add(goal)
    on_disk = json.loads(
        (tmp_path / "standing_goals.json").read_text(encoding="utf-8")
    )
    assert on_disk["schema_version"] == 1
    assert on_disk["goals"][0]["goal_id"] == goal.goal_id
