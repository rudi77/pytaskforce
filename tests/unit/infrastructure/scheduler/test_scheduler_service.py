"""Tests for SchedulerService."""

import asyncio
from datetime import UTC
from unittest.mock import AsyncMock

import pytest

from taskforce.core.domain.agent_event import AgentEvent, AgentEventType
from taskforce.core.domain.schedule import (
    ScheduleAction,
    ScheduleActionType,
    ScheduleJob,
    ScheduleType,
)
from taskforce.infrastructure.scheduler.scheduler_service import (
    SchedulerService,
    _next_cron_occurrence,
    _parse_interval,
)


class TestParseInterval:
    """Tests for interval expression parsing."""

    def test_seconds(self) -> None:
        td = _parse_interval("30s")
        assert td.total_seconds() == 30

    def test_minutes(self) -> None:
        td = _parse_interval("15m")
        assert td.total_seconds() == 900

    def test_hours(self) -> None:
        td = _parse_interval("2h")
        assert td.total_seconds() == 7200

    def test_days(self) -> None:
        td = _parse_interval("1d")
        assert td.total_seconds() == 86400

    def test_bare_number(self) -> None:
        td = _parse_interval("60")
        assert td.total_seconds() == 60


class TestNextCronOccurrence:
    """Tests for cron expression evaluation."""

    def test_every_minute(self) -> None:
        from datetime import datetime

        after = datetime(2026, 2, 18, 10, 30, 0, tzinfo=UTC)
        result = _next_cron_occurrence("* * * * *", after)
        assert result.minute == 31
        assert result.hour == 10

    def test_specific_hour(self) -> None:
        from datetime import datetime

        after = datetime(2026, 2, 18, 7, 0, 0, tzinfo=UTC)
        result = _next_cron_occurrence("0 8 * * *", after)
        assert result.hour == 8
        assert result.minute == 0

    def test_invalid_expression(self) -> None:
        from datetime import datetime

        after = datetime(2026, 2, 18, 10, 0, 0, tzinfo=UTC)
        with pytest.raises(ValueError, match="expected 5 fields"):
            _next_cron_occurrence("invalid", after)


class TestSchedulerService:
    """Tests for the SchedulerService."""

    @pytest.fixture
    def scheduler(self, tmp_path) -> SchedulerService:
        return SchedulerService(work_dir=str(tmp_path))

    @pytest.fixture
    def callback(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def scheduler_with_callback(self, tmp_path, callback) -> SchedulerService:
        return SchedulerService(work_dir=str(tmp_path), event_callback=callback)

    async def test_start_stop(self, scheduler: SchedulerService) -> None:
        assert not scheduler.is_running
        await scheduler.start()
        assert scheduler.is_running
        await scheduler.stop()
        assert not scheduler.is_running

    async def test_add_job(self, scheduler: SchedulerService) -> None:
        await scheduler.start()
        job = ScheduleJob(
            name="test_job",
            schedule_type=ScheduleType.INTERVAL,
            expression="1h",
            action=ScheduleAction(
                action_type=ScheduleActionType.SEND_NOTIFICATION,
                params={"message": "test"},
            ),
        )
        job_id = await scheduler.add_job(job)
        assert job_id == job.job_id

        jobs = await scheduler.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].name == "test_job"
        await scheduler.stop()

    async def test_remove_job(self, scheduler: SchedulerService) -> None:
        await scheduler.start()
        job = ScheduleJob(name="to_remove", schedule_type=ScheduleType.INTERVAL, expression="1h")
        await scheduler.add_job(job)

        removed = await scheduler.remove_job(job.job_id)
        assert removed is True

        removed_again = await scheduler.remove_job(job.job_id)
        assert removed_again is False

        jobs = await scheduler.list_jobs()
        assert len(jobs) == 0
        await scheduler.stop()

    async def test_pause_resume_job(self, scheduler: SchedulerService) -> None:
        await scheduler.start()
        job = ScheduleJob(name="pausable", schedule_type=ScheduleType.INTERVAL, expression="1h")
        await scheduler.add_job(job)

        paused = await scheduler.pause_job(job.job_id)
        assert paused is True

        retrieved = await scheduler.get_job(job.job_id)
        assert retrieved is not None
        assert retrieved.enabled is False

        resumed = await scheduler.resume_job(job.job_id)
        assert resumed is True

        retrieved = await scheduler.get_job(job.job_id)
        assert retrieved is not None
        assert retrieved.enabled is True
        await scheduler.stop()

    async def test_get_nonexistent_job(self, scheduler: SchedulerService) -> None:
        result = await scheduler.get_job("nonexistent")
        assert result is None

    async def test_job_persistence(self, tmp_path) -> None:
        """Test that jobs survive restart."""
        s1 = SchedulerService(work_dir=str(tmp_path))
        await s1.start()
        job = ScheduleJob(
            name="persistent",
            schedule_type=ScheduleType.INTERVAL,
            expression="1h",
        )
        await s1.add_job(job)
        await s1.stop()

        # Create a new scheduler instance pointing to same dir
        s2 = SchedulerService(work_dir=str(tmp_path))
        await s2.start()
        jobs = await s2.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].name == "persistent"
        await s2.stop()

    @pytest.mark.slow
    async def test_interval_job_fires(self, scheduler_with_callback, callback) -> None:
        """Test that a short-interval job actually fires.

        Uses polling instead of a fixed sleep to avoid flakiness on slow CI runners.
        """
        await scheduler_with_callback.start()
        job = ScheduleJob(
            name="fast_interval",
            schedule_type=ScheduleType.INTERVAL,
            expression="1s",  # Fire every second
            action=ScheduleAction(
                action_type=ScheduleActionType.SEND_NOTIFICATION,
                params={"message": "ping"},
            ),
        )
        await scheduler_with_callback.add_job(job)

        # Poll until the callback fires, with a generous timeout
        for _ in range(50):  # 50 * 0.1s = 5s max
            if callback.call_count >= 1:
                break
            await asyncio.sleep(0.1)

        await scheduler_with_callback.stop()

        assert callback.call_count >= 1
        fired_event: AgentEvent = callback.call_args[0][0]
        assert fired_event.source == "scheduler"
        assert fired_event.event_type == AgentEventType.SCHEDULE_TRIGGERED
        assert fired_event.payload["job_name"] == "fast_interval"
