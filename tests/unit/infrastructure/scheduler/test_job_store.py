"""Tests for FileJobStore."""

import pytest

from taskforce.core.domain.schedule import (
    ScheduleAction,
    ScheduleActionType,
    ScheduleJob,
    ScheduleType,
)
from taskforce.infrastructure.scheduler.job_store import FileJobStore


class TestFileJobStore:
    """Tests for file-based job persistence."""

    @pytest.fixture
    def store(self, tmp_path) -> FileJobStore:
        return FileJobStore(work_dir=str(tmp_path))

    async def test_save_and_load(self, store: FileJobStore) -> None:
        job = ScheduleJob(
            name="test_persist",
            schedule_type=ScheduleType.CRON,
            expression="0 8 * * *",
            action=ScheduleAction(
                action_type=ScheduleActionType.EXECUTE_MISSION,
                params={"mission": "Daily briefing"},
            ),
        )
        await store.save(job)
        loaded = await store.load(job.job_id)
        assert loaded is not None
        assert loaded.name == "test_persist"
        assert loaded.schedule_type == ScheduleType.CRON
        assert loaded.expression == "0 8 * * *"
        assert loaded.action.params["mission"] == "Daily briefing"

    async def test_load_nonexistent(self, store: FileJobStore) -> None:
        loaded = await store.load("nonexistent")
        assert loaded is None

    async def test_load_all(self, store: FileJobStore) -> None:
        for i in range(3):
            job = ScheduleJob(name=f"job_{i}", expression="* * * * *")
            await store.save(job)

        all_jobs = await store.load_all()
        assert len(all_jobs) == 3

    async def test_delete(self, store: FileJobStore) -> None:
        job = ScheduleJob(name="to_delete")
        await store.save(job)

        deleted = await store.delete(job.job_id)
        assert deleted is True

        deleted_again = await store.delete(job.job_id)
        assert deleted_again is False

        loaded = await store.load(job.job_id)
        assert loaded is None

    async def test_overwrite_on_save(self, store: FileJobStore) -> None:
        job = ScheduleJob(name="original")
        await store.save(job)
        job.name = "updated"
        await store.save(job)

        loaded = await store.load(job.job_id)
        assert loaded is not None
        assert loaded.name == "updated"
