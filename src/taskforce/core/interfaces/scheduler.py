"""Scheduler Protocol for time-based job management.

Defines the contract for scheduling cron jobs, interval tasks,
and one-shot reminders within the butler daemon.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from taskforce.core.domain.schedule import ScheduleJob


class SchedulerProtocol(Protocol):
    """Protocol for job scheduling.

    Manages time-based triggers (cron expressions, intervals, one-shot)
    and persists jobs across restarts.
    """

    async def start(self) -> None:
        """Start the scheduler, resuming any persisted jobs."""
        ...

    async def stop(self) -> None:
        """Gracefully shut down the scheduler."""
        ...

    async def add_job(self, job: ScheduleJob) -> str:
        """Add a new scheduled job.

        Args:
            job: The job definition to schedule.

        Returns:
            The job_id of the created job.
        """
        ...

    async def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job.

        Args:
            job_id: ID of the job to remove.

        Returns:
            True if the job was found and removed.
        """
        ...

    async def get_job(self, job_id: str) -> ScheduleJob | None:
        """Retrieve a job by ID.

        Args:
            job_id: ID of the job to retrieve.

        Returns:
            The job if found, None otherwise.
        """
        ...

    async def list_jobs(self) -> list[ScheduleJob]:
        """List all registered jobs.

        Returns:
            List of all scheduled jobs.
        """
        ...

    async def pause_job(self, job_id: str) -> bool:
        """Pause a running job.

        Args:
            job_id: ID of the job to pause.

        Returns:
            True if the job was found and paused.
        """
        ...

    async def resume_job(self, job_id: str) -> bool:
        """Resume a paused job.

        Args:
            job_id: ID of the job to resume.

        Returns:
            True if the job was found and resumed.
        """
        ...
