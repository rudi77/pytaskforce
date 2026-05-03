"""Unit tests for SchedulerService (cron parsing + job lifecycle)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
    @pytest.mark.parametrize(
        "expr,expected_seconds",
        [
            ("30s", 30),
            ("5m", 300),
            ("2h", 7200),
            ("1d", 86400),
            ("42", 42),  # bare int → seconds
        ],
    )
    def test_parses_suffixes(self, expr: str, expected_seconds: int) -> None:
        assert _parse_interval(expr).total_seconds() == expected_seconds

    def test_case_insensitive(self) -> None:
        assert _parse_interval("5M") == timedelta(minutes=5)


class TestNextCronOccurrence:
    def test_every_minute(self) -> None:
        base = datetime(2026, 4, 21, 12, 0, tzinfo=UTC)
        nxt = _next_cron_occurrence("* * * * *", base)
        assert nxt == datetime(2026, 4, 21, 12, 1, tzinfo=UTC)

    def test_specific_hour_and_minute(self) -> None:
        base = datetime(2026, 4, 21, 7, 59, tzinfo=UTC)
        nxt = _next_cron_occurrence("0 8 * * *", base)
        assert nxt == datetime(2026, 4, 21, 8, 0, tzinfo=UTC)

    def test_rolls_to_next_day(self) -> None:
        base = datetime(2026, 4, 21, 9, 0, tzinfo=UTC)
        nxt = _next_cron_occurrence("0 8 * * *", base)
        assert nxt == datetime(2026, 4, 22, 8, 0, tzinfo=UTC)

    def test_step_expression(self) -> None:
        base = datetime(2026, 4, 21, 12, 0, tzinfo=UTC)
        nxt = _next_cron_occurrence("*/15 * * * *", base)
        assert nxt == datetime(2026, 4, 21, 12, 15, tzinfo=UTC)

    def test_range_expression(self) -> None:
        # Hours 9-17 → next occurrence from 8:30 is 9:00.
        base = datetime(2026, 4, 21, 8, 30, tzinfo=UTC)
        nxt = _next_cron_occurrence("0 9-17 * * *", base)
        assert nxt == datetime(2026, 4, 21, 9, 0, tzinfo=UTC)

    def test_invalid_expression_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid cron expression"):
            _next_cron_occurrence("too few fields", datetime.now(UTC))


class InMemoryJobStore:
    """Minimal job-store fake for injection tests."""

    def __init__(self) -> None:
        self.jobs: dict[str, ScheduleJob] = {}

    async def save(self, job: ScheduleJob) -> None:
        self.jobs[job.job_id] = job

    async def load(self, job_id: str) -> ScheduleJob | None:
        return self.jobs.get(job_id)

    async def load_all(self) -> list[ScheduleJob]:
        return list(self.jobs.values())

    async def delete(self, job_id: str) -> bool:
        return self.jobs.pop(job_id, None) is not None


class TestSchedulerServiceLifecycle:
    async def test_uses_injected_job_store(self) -> None:
        store = InMemoryJobStore()
        svc = SchedulerService(job_store=store)
        job = ScheduleJob(name="briefing", schedule_type=ScheduleType.CRON, expression="0 8 * * *")

        await svc.add_job(job)

        assert await store.load(job.job_id) == job

    async def test_add_job_persists_and_lists(self, tmp_path: Path) -> None:
        svc = SchedulerService(work_dir=str(tmp_path))
        job = ScheduleJob(
            name="briefing",
            schedule_type=ScheduleType.CRON,
            expression="0 8 * * *",
            action=ScheduleAction(ScheduleActionType.EXECUTE_MISSION),
            tenant_id="acme",
            agent_id="accountant",
        )
        await svc.add_job(job)
        jobs = await svc.list_jobs()
        assert len(jobs) == 1 and jobs[0].name == "briefing"
        assert jobs[0].tenant_id == "acme"
        assert jobs[0].agent_id == "accountant"

    async def test_remove_job(self, tmp_path: Path) -> None:
        svc = SchedulerService(work_dir=str(tmp_path))
        job = ScheduleJob(name="x", schedule_type=ScheduleType.CRON, expression="* * * * *")
        await svc.add_job(job)
        assert await svc.remove_job(job.job_id) is True
        assert await svc.list_jobs() == []

    async def test_pause_and_resume(self, tmp_path: Path) -> None:
        svc = SchedulerService(work_dir=str(tmp_path))
        job = ScheduleJob(name="x", schedule_type=ScheduleType.CRON, expression="* * * * *")
        await svc.add_job(job)

        assert await svc.pause_job(job.job_id) is True
        assert (await svc.get_job(job.job_id)).enabled is False

        assert await svc.resume_job(job.job_id) is True
        assert (await svc.get_job(job.job_id)).enabled is True

    async def test_start_resumes_persisted_jobs(self, tmp_path: Path) -> None:
        svc1 = SchedulerService(work_dir=str(tmp_path))
        job = ScheduleJob(name="persisted", schedule_type=ScheduleType.CRON, expression="0 8 * * *")
        await svc1.add_job(job)

        svc2 = SchedulerService(work_dir=str(tmp_path))
        await svc2.start()
        try:
            restored = await svc2.list_jobs()
            assert len(restored) == 1 and restored[0].name == "persisted"
        finally:
            await svc2.stop()

    async def test_one_shot_fires_and_cleans_up(self, tmp_path: Path) -> None:
        fired: list[AgentEvent] = []

        async def on_event(event: AgentEvent) -> None:
            fired.append(event)

        svc = SchedulerService(work_dir=str(tmp_path), event_callback=on_event)
        fire_at = (datetime.now(UTC) + timedelta(milliseconds=50)).isoformat()
        job = ScheduleJob(
            name="one-shot",
            schedule_type=ScheduleType.ONE_SHOT,
            expression=fire_at,
            action=ScheduleAction(ScheduleActionType.EXECUTE_MISSION),
        )

        await svc.start()
        try:
            await svc.add_job(job)
            # wait for it to fire
            await asyncio.sleep(0.3)
            assert len(fired) == 1
            assert fired[0].event_type == AgentEventType.SCHEDULE_TRIGGERED
            assert fired[0].payload["job_id"] == job.job_id
            assert fired[0].payload["tenant_id"] == "default"
            assert fired[0].payload["agent_id"] == "default"
            # Cleaned up from memory and disk
            assert await svc.get_job(job.job_id) is None
        finally:
            await svc.stop()
