"""Unit tests for FileJobStore."""

from __future__ import annotations

from pathlib import Path

from taskforce.core.domain.schedule import (
    ScheduleAction,
    ScheduleActionType,
    ScheduleJob,
    ScheduleType,
)
from taskforce.infrastructure.scheduler.file_job_store import FileJobStore


def _make_job(name: str = "daily_briefing") -> ScheduleJob:
    return ScheduleJob(
        name=name,
        schedule_type=ScheduleType.CRON,
        expression="0 8 * * *",
        action=ScheduleAction(
            action_type=ScheduleActionType.EXECUTE_MISSION,
            params={"mission": "Summarize overnight events"},
        ),
    )


class TestFileJobStore:
    async def test_save_and_load_single_job(self, tmp_path: Path) -> None:
        store = FileJobStore(str(tmp_path))
        job = _make_job()
        await store.save(job)

        loaded = await store.load(job.job_id)
        assert loaded is not None
        assert loaded.job_id == job.job_id
        assert loaded.name == job.name
        assert loaded.schedule_type == ScheduleType.CRON

    async def test_load_missing_returns_none(self, tmp_path: Path) -> None:
        store = FileJobStore(str(tmp_path))
        assert await store.load("does-not-exist") is None

    async def test_load_all(self, tmp_path: Path) -> None:
        store = FileJobStore(str(tmp_path))
        await store.save(_make_job("a"))
        await store.save(_make_job("b"))

        jobs = await store.load_all()
        assert {j.name for j in jobs} == {"a", "b"}

    async def test_load_all_empty(self, tmp_path: Path) -> None:
        store = FileJobStore(str(tmp_path))
        assert await store.load_all() == []

    async def test_delete_existing(self, tmp_path: Path) -> None:
        store = FileJobStore(str(tmp_path))
        job = _make_job()
        await store.save(job)

        assert await store.delete(job.job_id) is True
        assert await store.load(job.job_id) is None

    async def test_delete_missing(self, tmp_path: Path) -> None:
        store = FileJobStore(str(tmp_path))
        assert await store.delete("ghost") is False

    async def test_save_is_atomic(self, tmp_path: Path) -> None:
        """Save writes to .tmp then renames — no stale .tmp files remain."""
        store = FileJobStore(str(tmp_path))
        await store.save(_make_job())
        tmp_files = list((tmp_path / "scheduler" / "jobs").glob("*.tmp"))
        assert tmp_files == []

    async def test_load_all_quarantines_corrupt_files(self, tmp_path: Path) -> None:
        """A corrupt job file is renamed aside, healthy jobs still load."""
        store = FileJobStore(str(tmp_path))
        await store.save(_make_job("healthy"))

        jobs_dir = tmp_path / "scheduler" / "jobs"
        corrupt_path = jobs_dir / "broken.json"
        corrupt_path.write_text("{not json", encoding="utf-8")

        loaded = await store.load_all()
        assert {j.name for j in loaded} == {"healthy"}
        # The corrupt file is gone (renamed), and a *.corrupt-* sibling
        # exists in its place — no silent data loss.
        assert not corrupt_path.exists()
        quarantined = list(jobs_dir.glob("broken.json.corrupt-*"))
        assert len(quarantined) == 1
