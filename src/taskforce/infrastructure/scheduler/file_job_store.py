"""File-based job store for persisting scheduled jobs across restarts."""

from __future__ import annotations

import json
import time
from pathlib import Path

import aiofiles
import structlog

from taskforce.core.domain.schedule import ScheduleJob
from taskforce.core.utils.atomic_io import atomic_write_text

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
        await atomic_write_text(path, data)
        logger.debug("job_store.saved", job_id=job.job_id, name=job.name)

    async def load(self, job_id: str) -> ScheduleJob | None:
        """Load a single job from disk."""
        path = self._dir / f"{job_id}.json"
        if not path.exists():
            return None
        async with aiofiles.open(path, encoding="utf-8") as f:
            raw = await f.read()
        return ScheduleJob.from_dict(json.loads(raw))

    async def load_all(self) -> list[ScheduleJob]:
        """Load all persisted jobs.

        Corrupt or unparseable files are quarantined by renaming them
        to ``{name}.corrupt-{epoch}`` instead of being silently
        dropped. Daemon startup continues so the rest of the schedule
        survives a single bad file, but the operator gets a loud
        ``ERROR`` log line *and* the file stays on disk for forensics.
        """
        await self._ensure_dir()
        jobs: list[ScheduleJob] = []
        for path in sorted(self._dir.glob("*.json")):
            try:
                async with aiofiles.open(path, encoding="utf-8") as f:
                    raw = await f.read()
                jobs.append(ScheduleJob.from_dict(json.loads(raw)))
            except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
                self._quarantine(path, exc)
        return jobs

    def _quarantine(self, path: Path, exc: BaseException) -> None:
        """Move *path* aside so a corrupt file is not silently lost."""
        quarantine_path = path.with_name(f"{path.name}.corrupt-{int(time.time())}")
        try:
            path.rename(quarantine_path)
        except OSError as rename_exc:
            logger.error(
                "job_store.quarantine_failed",
                path=str(path),
                error=str(exc),
                rename_error=str(rename_exc),
            )
            return
        logger.error(
            "job_store.load_failed",
            path=str(path),
            quarantined_to=str(quarantine_path),
            error=str(exc),
            error_type=type(exc).__name__,
        )

    async def delete(self, job_id: str) -> bool:
        """Delete a persisted job."""
        path = self._dir / f"{job_id}.json"
        if path.exists():
            path.unlink()
            logger.debug("job_store.deleted", job_id=job_id)
            return True
        return False
