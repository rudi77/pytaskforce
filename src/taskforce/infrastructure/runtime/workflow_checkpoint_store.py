"""File-based storage for resumable workflow checkpoints."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from taskforce.core.domain.workflow_checkpoint import WorkflowCheckpoint


class FileWorkflowCheckpointStore:
    """Persist workflow checkpoints to JSON files."""

    def __init__(self, work_dir: str = ".taskforce"):
        self._base_dir = Path(work_dir) / "workflows" / "checkpoints"
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, checkpoint: WorkflowCheckpoint) -> None:
        """Save or update checkpoint."""
        payload = checkpoint.to_dict()
        payload["updated_at"] = datetime.now(UTC).isoformat()
        self._path(checkpoint.run_id).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def get(self, run_id: str) -> WorkflowCheckpoint | None:
        """Load checkpoint by run ID."""
        path = self._path(run_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return WorkflowCheckpoint.from_dict(data)

    def list_waiting(self) -> list[WorkflowCheckpoint]:
        """List checkpoints currently waiting for external input."""
        waiting: list[WorkflowCheckpoint] = []
        for file in sorted(self._base_dir.glob("*.json")):
            data = json.loads(file.read_text(encoding="utf-8"))
            checkpoint = WorkflowCheckpoint.from_dict(data)
            if checkpoint.status == "waiting_external":
                waiting.append(checkpoint)
        return waiting

    def _path(self, run_id: str) -> Path:
        return self._base_dir / f"{run_id}.json"


def validate_required_inputs(
    required_inputs: dict[str, object],
    payload: dict[str, object],
) -> tuple[bool, str | None]:
    """Validate resume payload against minimal required input schema.

    Expected shape:
    {
      "required": ["field_a", "field_b"]
    }
    """
    required = required_inputs.get("required", [])
    if not isinstance(required, list):
        return False, "required_inputs.required must be a list"

    missing = [key for key in required if key not in payload]
    if missing:
        return False, f"Missing required resume fields: {', '.join(str(k) for k in missing)}"

    return True, None
