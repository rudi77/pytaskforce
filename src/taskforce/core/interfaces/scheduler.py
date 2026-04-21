"""Protocol for time-based job scheduling."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from taskforce.core.domain.schedule import ScheduleJob


class SchedulerProtocol(Protocol):
    """Protocol for time-based job scheduling (cron, interval, one-shot)."""

    async def start(self) -> None:
        """Start the scheduler, resuming any persisted jobs."""
        ...

    async def stop(self) -> None:
        """Gracefully shut down the scheduler."""
        ...

    async def add_job(self, job: ScheduleJob) -> str:
        """Add a new scheduled job. Returns the job_id."""
        ...

    async def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job. Returns True if found and removed."""
        ...

    async def get_job(self, job_id: str) -> ScheduleJob | None:
        """Retrieve a job by ID."""
        ...

    async def list_jobs(self) -> list[ScheduleJob]:
        """List all registered jobs."""
        ...

    async def pause_job(self, job_id: str) -> bool:
        """Pause a running job. Returns True if found and paused."""
        ...

    async def resume_job(self, job_id: str) -> bool:
        """Resume a paused job. Returns True if found and resumed."""
        ...
