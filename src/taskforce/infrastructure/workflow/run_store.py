"""File-based persistence for workflow run state.

Stores workflow run records as JSON files under
``{work_dir}/workflow_runs/{run_id}.json``, using atomic writes
(write-to-temp + rename) to avoid partial writes.
"""

from __future__ import annotations

import json
from pathlib import Path

import aiofiles
import structlog

from taskforce.core.domain.workflow import WorkflowRunRecord, WorkflowStatus
from taskforce.core.interfaces.workflow import WorkflowRunStoreProtocol

logger = structlog.get_logger(__name__)


class FileWorkflowRunStore(WorkflowRunStoreProtocol):
    """File-based workflow run store."""

    def __init__(self, work_dir: str | Path = ".taskforce") -> None:
        self._base_dir = Path(work_dir) / "workflow_runs"
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, run_id: str) -> Path:
        return self._base_dir / f"{run_id}.json"

    async def save(self, record: WorkflowRunRecord) -> None:
        """Save or update a workflow run record."""
        path = self._path_for(record.run_id)
        payload = json.dumps(record.to_dict(), ensure_ascii=False, indent=2)
        tmp_path = path.with_suffix(".tmp")
        async with aiofiles.open(tmp_path, "w", encoding="utf-8") as f:
            await f.write(payload)
        tmp_path.replace(path)
        logger.debug(
            "workflow_run.saved",
            run_id=record.run_id,
            status=record.status.value,
        )

    async def load(self, run_id: str) -> WorkflowRunRecord | None:
        """Load a workflow run record by run ID."""
        path = self._path_for(run_id)
        if not path.exists():
            return None
        async with aiofiles.open(path, encoding="utf-8") as f:
            data = json.loads(await f.read())
        return WorkflowRunRecord.from_dict(data)

    async def load_by_session(self, session_id: str) -> WorkflowRunRecord | None:
        """Load the active (WAITING_FOR_INPUT) workflow run for a session."""
        waiting = await self.list_waiting()
        for record in waiting:
            if record.session_id == session_id:
                return record
        return None

    async def delete(self, run_id: str) -> None:
        """Delete a workflow run record."""
        path = self._path_for(run_id)
        if path.exists():
            path.unlink()
            logger.debug("workflow_run.deleted", run_id=run_id)

    async def list_waiting(self) -> list[WorkflowRunRecord]:
        """List all workflow runs currently waiting for input."""
        records: list[WorkflowRunRecord] = []
        for path in self._base_dir.glob("*.json"):
            try:
                async with aiofiles.open(path, encoding="utf-8") as f:
                    data = json.loads(await f.read())
                record = WorkflowRunRecord.from_dict(data)
                if record.status == WorkflowStatus.WAITING_FOR_INPUT:
                    records.append(record)
            except (json.JSONDecodeError, KeyError, ValueError):
                logger.warning("workflow_run.invalid_file", path=str(path))
        return records
