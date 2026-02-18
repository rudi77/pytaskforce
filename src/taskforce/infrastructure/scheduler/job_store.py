"""File-based job store for persisting scheduled jobs across restarts."""

from __future__ import annotations

import json
from pathlib import Path

import aiofiles
import structlog

from taskforce.core.domain.schedule import ScheduleJob

logger = structlog.get_logger(__name__)


class FileJobStore:
    """Persist scheduled jobs as JSON files.

    Storage layout::

        {work_dir}/scheduler/jobs/
        ├── {job_id}.json
        └── {job_id}.json
    """

    def __init__(self, work_dir: str = ".taskforce") -> None:
        self._dir = Path(work_dir) / "scheduler" / "jobs"

    async def _ensure_dir(self) -> None:
        """Create the storage directory if it doesn't exist."""
        self._dir.mkdir(parents=True, exist_ok=True)

    async def save(self, job: ScheduleJob) -> None:
        """Persist a job to disk."""
        await self._ensure_dir()
        path = self._dir / f"{job.job_id}.json"
        data = json.dumps(job.to_dict(), indent=2, default=str)
        tmp = path.with_suffix(".json.tmp")
        async with aiofiles.open(tmp, "w") as f:
            await f.write(data)
        tmp.rename(path)
        logger.debug("job_store.saved", job_id=job.job_id, name=job.name)

    async def load(self, job_id: str) -> ScheduleJob | None:
        """Load a single job from disk."""
        path = self._dir / f"{job_id}.json"
        if not path.exists():
            return None
        async with aiofiles.open(path) as f:
            raw = await f.read()
        return ScheduleJob.from_dict(json.loads(raw))

    async def load_all(self) -> list[ScheduleJob]:
        """Load all persisted jobs."""
        await self._ensure_dir()
        jobs: list[ScheduleJob] = []
        for path in sorted(self._dir.glob("*.json")):
            try:
                async with aiofiles.open(path) as f:
                    raw = await f.read()
                jobs.append(ScheduleJob.from_dict(json.loads(raw)))
            except Exception as exc:
                logger.warning("job_store.load_failed", path=str(path), error=str(exc))
        return jobs

    async def delete(self, job_id: str) -> bool:
        """Delete a persisted job."""
        path = self._dir / f"{job_id}.json"
        if path.exists():
            path.unlink()
            logger.debug("job_store.deleted", job_id=job_id)
            return True
        return False
