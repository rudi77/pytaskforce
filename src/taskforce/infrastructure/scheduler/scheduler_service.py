"""Asyncio-based scheduler service for managing timed jobs.

Uses asyncio tasks for scheduling instead of APScheduler to avoid
an external dependency. Jobs are persisted via FileJobStore and
survive restarts.

Edge-case handling (issue #158):

- **Timezone:** Each ``ScheduleJob`` stores an explicit IANA ``timezone``.
  Cron expressions and naive ISO datetimes are evaluated in that zone via
  :mod:`zoneinfo`. The scheduler falls back to a configurable
  ``default_timezone`` (defaulting to ``"UTC"``) when a job omits it.
- **Coalesce policy:** Jobs missed during downtime honour the
  :class:`taskforce.core.domain.schedule.CoalescePolicy` field. ``SKIP``
  ignores missed firings; ``RUN_ONCE`` fires a single catch-up at
  startup.
- **One-shot idempotency:** ``last_fired_at`` is persisted **before** the
  action runs. On startup, one-shots whose ``last_fired_at`` is set are
  skipped and removed from disk so they cannot fire again.
- **DST transitions:** Local cron candidates that fall in a non-existent
  wall-clock window (DST forward jump) are skipped; the next valid local
  match is used. Ambiguous local times (DST backward jump) resolve to a
  unique UTC instant via ``fold=0``, so each cron slot fires exactly once.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog

from taskforce.core.domain.agent_event import AgentEvent, AgentEventType
from taskforce.core.domain.schedule import CoalescePolicy, ScheduleJob, ScheduleType
from taskforce.core.utils.time import utc_now
from taskforce.infrastructure.scheduler.file_job_store import FileJobStore

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


def _resolve_zone(name: str | None) -> ZoneInfo:
    """Resolve an IANA timezone name, falling back to UTC on failure."""
    if not name:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("scheduler.unknown_timezone", timezone=name, fallback="UTC")
        return ZoneInfo("UTC")


def _is_nonexistent_local(naive: datetime, zone: ZoneInfo) -> bool:
    """Detect whether a naive local datetime falls in a DST forward gap.

    A non-existent wall-clock time round-trips through UTC to a *different*
    naive local datetime than the one we started with.
    """
    aware = naive.replace(tzinfo=zone)
    roundtrip = aware.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
    return roundtrip != naive


def _next_cron_occurrence(
    expression: str,
    after: datetime,
    timezone: str | None = None,
) -> datetime:
    """Calculate the next occurrence for a simple cron expression.

    Supports standard 5-field cron: minute hour day_of_month month day_of_week.
    Cron fields are evaluated in ``timezone`` (defaults to UTC). The returned
    datetime is timezone-aware in UTC so callers can keep doing UTC arithmetic.

    DST handling:

    - **Forward jump** (e.g. local 02:30 does not exist on the spring DST
      day): the candidate is skipped and the next valid local match is used.
    - **Backward jump** (e.g. local 02:30 happens twice on the autumn DST
      day): the first occurrence is used (``fold=0``), so the slot fires
      exactly once.
    """
    parts = expression.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression (expected 5 fields): {expression}")

    minute_spec, hour_spec, dom_spec, month_spec, dow_spec = parts
    zone = _resolve_zone(timezone)

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

    # Convert ``after`` to local naive time so we iterate the cron grid in the
    # job's wall clock (so "0 8 * * *" stays at 08:00 local across DST).
    if after.tzinfo is None:
        after_utc = after.replace(tzinfo=UTC)
    else:
        after_utc = after.astimezone(UTC)
    local_after = after_utc.astimezone(zone).replace(tzinfo=None)
    candidate = local_after.replace(second=0, microsecond=0) + timedelta(minutes=1)

    for _ in range(525960):  # scan up to ~1 year
        if (
            _matches(candidate.minute, minute_spec, 0, 59)
            and _matches(candidate.hour, hour_spec, 0, 23)
            and _matches(candidate.day, dom_spec, 1, 31)
            and _matches(candidate.month, month_spec, 1, 12)
            and _matches(candidate.weekday(), dow_spec, 0, 6)
        ):
            if not _is_nonexistent_local(candidate, zone):
                aware_local = candidate.replace(tzinfo=zone, fold=0)
                return aware_local.astimezone(UTC)
            # Skipped wall-clock (DST gap) — keep scanning.
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
        job_store: Any | None = None,
        default_timezone: str = "UTC",
    ) -> None:
        self._store = job_store or FileJobStore(work_dir)
        self._event_callback = event_callback
        self._jobs: dict[str, ScheduleJob] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._running = False
        self._default_timezone = default_timezone or "UTC"

    @property
    def is_running(self) -> bool:
        """Whether the scheduler is active."""
        return self._running

    def _job_timezone(self, job: ScheduleJob) -> str:
        """Return the IANA timezone name to use for a job, with fallback."""
        return job.timezone or self._default_timezone or "UTC"

    async def start(self) -> None:
        """Start the scheduler, resuming persisted jobs.

        One-shot jobs whose ``last_fired_at`` is already set are removed
        from disk and skipped (see issue #158: scheduler restart must not
        re-fire already-executed one-shots).
        """
        if self._running:
            return
        self._running = True
        persisted = await self._store.load_all()
        scheduled = 0
        for job in persisted:
            if job.schedule_type == ScheduleType.ONE_SHOT and job.last_fired_at is not None:
                # Already fired before a crash/restart — drop it permanently.
                logger.info(
                    "scheduler.one_shot_skip_already_fired",
                    job_id=job.job_id,
                    name=job.name,
                    last_fired_at=job.last_fired_at.isoformat(),
                )
                await self._store.delete(job.job_id)
                continue
            self._jobs[job.job_id] = job
            if job.enabled:
                self._schedule_task(job)
                scheduled += 1
        logger.info("scheduler.started", job_count=scheduled)

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
        if not job.timezone:
            job.timezone = self._default_timezone or "UTC"
        self._jobs[job.job_id] = job
        await self._store.save(job)
        if job.enabled and self._running:
            self._schedule_task(job)
        logger.info(
            "scheduler.job_added",
            job_id=job.job_id,
            name=job.name,
            timezone=job.timezone,
            coalesce=job.coalesce.value,
        )
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

    def _parse_one_shot_target(self, job: ScheduleJob) -> datetime:
        """Parse a one-shot expression into a UTC datetime.

        Naive ISO datetimes are interpreted in the job's timezone.
        """
        target = datetime.fromisoformat(job.expression)
        if target.tzinfo is None:
            zone = _resolve_zone(self._job_timezone(job))
            target = target.replace(tzinfo=zone)
        return target.astimezone(UTC)

    async def _run_one_shot(self, job: ScheduleJob) -> None:
        """Execute a one-shot job at the specified time.

        ``last_fired_at`` is persisted **before** the action runs so a crash
        between persistence and action does not cause a duplicate firing on
        restart (issue #158).
        """
        # If a previous run already marked this one-shot as fired (e.g. the
        # store handed us a stale copy), refuse to fire again.
        if job.last_fired_at is not None:
            logger.info(
                "scheduler.one_shot_already_fired",
                job_id=job.job_id,
                name=job.name,
            )
            self._jobs.pop(job.job_id, None)
            self._tasks.pop(job.job_id, None)
            await self._store.delete(job.job_id)
            return

        target = self._parse_one_shot_target(job)
        delay = (target - utc_now()).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)
        await self._fire_job(job)
        # Clean up: remove completed one-shot job from memory and disk.
        self._jobs.pop(job.job_id, None)
        self._tasks.pop(job.job_id, None)
        await self._store.delete(job.job_id)
        logger.info("scheduler.one_shot_completed", job_id=job.job_id, name=job.name)

    async def _maybe_catch_up(self, job: ScheduleJob, now: datetime, expected: datetime) -> bool:
        """Apply the coalesce policy when ``expected`` is already in the past.

        Returns True when a catch-up event was fired (so the caller knows the
        job has been advanced past ``expected``).
        """
        if expected > now:
            return False
        if job.coalesce == CoalescePolicy.RUN_ONCE:
            logger.info(
                "scheduler.catch_up_run_once",
                job_id=job.job_id,
                name=job.name,
                missed_at=expected.isoformat(),
            )
            await self._fire_job(job)
            return True
        # SKIP: drop missed runs silently.
        logger.info(
            "scheduler.catch_up_skipped",
            job_id=job.job_id,
            name=job.name,
            missed_at=expected.isoformat(),
        )
        return True

    async def _run_interval(self, job: ScheduleJob) -> None:
        """Execute an interval job repeatedly.

        On startup we honour ``coalesce``: if more than one interval has
        elapsed since ``last_run`` we either fire one catch-up or skip
        directly to the next slot.
        """
        interval = _parse_interval(job.expression)
        anchor = job.last_run
        if anchor is not None and self._running and job.enabled:
            now = utc_now()
            expected = anchor + interval
            if expected <= now:
                fired = await self._maybe_catch_up(job, now, expected)
                if fired and not (self._running and job.enabled):
                    return
        while self._running and job.enabled:
            await asyncio.sleep(interval.total_seconds())
            if self._running and job.enabled:
                await self._fire_job(job)

    async def _run_cron(self, job: ScheduleJob) -> None:
        """Execute a cron job at matching times.

        On startup we honour ``coalesce``: if the previous expected
        occurrence is in the past (because the scheduler was down) we
        either fire one catch-up or skip directly to the next slot.
        """
        tz = self._job_timezone(job)
        if job.last_run is not None and self._running and job.enabled:
            now = utc_now()
            expected = _next_cron_occurrence(job.expression, job.last_run, tz)
            if expected <= now:
                await self._maybe_catch_up(job, now, expected)
        while self._running and job.enabled:
            now = utc_now()
            next_time = _next_cron_occurrence(job.expression, now, tz)
            delay = (next_time - now).total_seconds()
            if delay > 0:
                await asyncio.sleep(delay)
            if self._running and job.enabled:
                await self._fire_job(job)

    async def _fire_job(self, job: ScheduleJob) -> None:
        """Fire a job by publishing an AgentEvent.

        ``last_fired_at`` and ``last_run`` are persisted *before* the
        callback runs so a crash mid-fire does not cause duplicate firings.
        """
        fired_at = utc_now()
        job.last_fired_at = fired_at
        job.last_run = fired_at
        await self._store.save(job)

        event = AgentEvent(
            source="scheduler",
            event_type=AgentEventType.SCHEDULE_TRIGGERED,
            payload={
                "job_id": job.job_id,
                "job_name": job.name,
                "action": job.action.to_dict(),
                "tenant_id": job.tenant_id,
                "agent_id": job.agent_id,
            },
            metadata={
                "schedule_type": job.schedule_type.value,
                "tenant_id": job.tenant_id,
                "agent_id": job.agent_id,
                "timezone": self._job_timezone(job),
            },
        )

        logger.info(
            "scheduler.job_fired",
            job_id=job.job_id,
            name=job.name,
            action_type=job.action.action_type.value,
        )

        if self._event_callback:
            await self._event_callback(event)
