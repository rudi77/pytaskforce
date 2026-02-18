"""Asyncio-based scheduler service for managing timed jobs.

Uses asyncio tasks for scheduling instead of APScheduler to avoid
an external dependency. Jobs are persisted via FileJobStore and
survive restarts.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import structlog

from taskforce.core.domain.agent_event import AgentEvent, AgentEventType
from taskforce.core.domain.schedule import ScheduleJob, ScheduleType
from taskforce.core.utils.time import utc_now
from taskforce.infrastructure.scheduler.job_store import FileJobStore

logger = structlog.get_logger(__name__)


def _parse_interval(expression: str) -> timedelta:
    """Parse an interval expression like '15m', '1h', '30s' into timedelta."""
    expr = expression.strip().lower()
    if expr.endswith("s"):
        return timedelta(seconds=int(expr[:-1]))
    if expr.endswith("m"):
        return timedelta(minutes=int(expr[:-1]))
    if expr.endswith("h"):
        return timedelta(hours=int(expr[:-1]))
    if expr.endswith("d"):
        return timedelta(days=int(expr[:-1]))
    return timedelta(seconds=int(expr))


def _next_cron_occurrence(expression: str, after: datetime) -> datetime:
    """Calculate the next occurrence for a simple cron expression.

    Supports standard 5-field cron: minute hour day_of_month month day_of_week.
    Uses a simple forward-scanning approach (not production-grade for all
    edge cases, but sufficient for typical butler use cases).
    """
    parts = expression.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression (expected 5 fields): {expression}")

    minute_spec, hour_spec, dom_spec, month_spec, dow_spec = parts

    def _matches(value: int, spec: str, min_val: int, max_val: int) -> bool:
        if spec == "*":
            return True
        for part in spec.split(","):
            if "/" in part:
                base, step = part.split("/", 1)
                base_val = min_val if base == "*" else int(base)
                if (value - base_val) >= 0 and (value - base_val) % int(step) == 0:
                    return True
            elif "-" in part:
                lo, hi = part.split("-", 1)
                if int(lo) <= value <= int(hi):
                    return True
            elif int(part) == value:
                return True
        return False

    candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(525960):  # scan up to ~1 year
        if (
            _matches(candidate.minute, minute_spec, 0, 59)
            and _matches(candidate.hour, hour_spec, 0, 23)
            and _matches(candidate.day, dom_spec, 1, 31)
            and _matches(candidate.month, month_spec, 1, 12)
            and _matches(candidate.weekday(), dow_spec, 0, 6)
        ):
            return candidate
        candidate += timedelta(minutes=1)

    raise ValueError(f"No matching time found within 1 year for cron: {expression}")


class SchedulerService:
    """Asyncio-based scheduler that manages timed jobs.

    Persists jobs to a FileJobStore and publishes AgentEvents on the
    message bus when jobs fire.
    """

    def __init__(
        self,
        work_dir: str = ".taskforce",
        event_callback: Callable[[AgentEvent], Awaitable[None]] | None = None,
    ) -> None:
        self._store = FileJobStore(work_dir)
        self._event_callback = event_callback
        self._jobs: dict[str, ScheduleJob] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._running = False

    @property
    def is_running(self) -> bool:
        """Whether the scheduler is active."""
        return self._running

    async def start(self) -> None:
        """Start the scheduler, resuming persisted jobs."""
        if self._running:
            return
        self._running = True
        persisted = await self._store.load_all()
        for job in persisted:
            self._jobs[job.job_id] = job
            if job.enabled:
                self._schedule_task(job)
        logger.info("scheduler.started", job_count=len(persisted))

    async def stop(self) -> None:
        """Gracefully stop all scheduled tasks."""
        self._running = False
        for task in self._tasks.values():
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()
        logger.info("scheduler.stopped")

    async def add_job(self, job: ScheduleJob) -> str:
        """Add and persist a new scheduled job."""
        self._jobs[job.job_id] = job
        await self._store.save(job)
        if job.enabled and self._running:
            self._schedule_task(job)
        logger.info("scheduler.job_added", job_id=job.job_id, name=job.name)
        return job.job_id

    async def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job."""
        if job_id not in self._jobs:
            return False
        task = self._tasks.pop(job_id, None)
        if task:
            task.cancel()
        del self._jobs[job_id]
        await self._store.delete(job_id)
        logger.info("scheduler.job_removed", job_id=job_id)
        return True

    async def get_job(self, job_id: str) -> ScheduleJob | None:
        """Retrieve a job by ID."""
        return self._jobs.get(job_id)

    async def list_jobs(self) -> list[ScheduleJob]:
        """List all registered jobs."""
        return list(self._jobs.values())

    async def pause_job(self, job_id: str) -> bool:
        """Pause a running job."""
        job = self._jobs.get(job_id)
        if not job:
            return False
        job.enabled = False
        await self._store.save(job)
        task = self._tasks.pop(job_id, None)
        if task:
            task.cancel()
        return True

    async def resume_job(self, job_id: str) -> bool:
        """Resume a paused job."""
        job = self._jobs.get(job_id)
        if not job:
            return False
        job.enabled = True
        await self._store.save(job)
        if self._running:
            self._schedule_task(job)
        return True

    def _schedule_task(self, job: ScheduleJob) -> None:
        """Create an asyncio task for a job."""
        existing = self._tasks.pop(job.job_id, None)
        if existing:
            existing.cancel()
        self._tasks[job.job_id] = asyncio.create_task(
            self._run_job_loop(job), name=f"scheduler-{job.job_id}"
        )

    async def _run_job_loop(self, job: ScheduleJob) -> None:
        """Run the scheduling loop for a single job."""
        try:
            if job.schedule_type == ScheduleType.ONE_SHOT:
                await self._run_one_shot(job)
            elif job.schedule_type == ScheduleType.INTERVAL:
                await self._run_interval(job)
            elif job.schedule_type == ScheduleType.CRON:
                await self._run_cron(job)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("scheduler.job_error", job_id=job.job_id, error=str(exc))

    async def _run_one_shot(self, job: ScheduleJob) -> None:
        """Execute a one-shot job at the specified time."""
        target = datetime.fromisoformat(job.expression)
        if target.tzinfo is None:
            target = target.replace(tzinfo=UTC)
        delay = (target - utc_now()).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)
        await self._fire_job(job)
        job.enabled = False
        await self._store.save(job)

    async def _run_interval(self, job: ScheduleJob) -> None:
        """Execute an interval job repeatedly."""
        interval = _parse_interval(job.expression)
        while self._running and job.enabled:
            await asyncio.sleep(interval.total_seconds())
            if self._running and job.enabled:
                await self._fire_job(job)

    async def _run_cron(self, job: ScheduleJob) -> None:
        """Execute a cron job at matching times."""
        while self._running and job.enabled:
            now = utc_now()
            next_time = _next_cron_occurrence(job.expression, now)
            delay = (next_time - now).total_seconds()
            if delay > 0:
                await asyncio.sleep(delay)
            if self._running and job.enabled:
                await self._fire_job(job)

    async def _fire_job(self, job: ScheduleJob) -> None:
        """Fire a job by publishing an AgentEvent."""
        job.last_run = utc_now()
        await self._store.save(job)

        event = AgentEvent(
            source="scheduler",
            event_type=AgentEventType.SCHEDULE_TRIGGERED,
            payload={
                "job_id": job.job_id,
                "job_name": job.name,
                "action": job.action.to_dict(),
            },
            metadata={"schedule_type": job.schedule_type.value},
        )

        logger.info(
            "scheduler.job_fired",
            job_id=job.job_id,
            name=job.name,
            action_type=job.action.action_type.value,
        )

        if self._event_callback:
            await self._event_callback(event)
