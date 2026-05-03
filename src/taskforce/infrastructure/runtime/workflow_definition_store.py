"""File-backed workflow definition store."""

from __future__ import annotations

import json
from pathlib import Path

from taskforce.core.domain.workflow_definition import WorkflowDefinition


class FileWorkflowDefinitionStore:
    """Persist workflow definitions as JSON files."""

    def __init__(self, work_dir: str = ".taskforce") -> None:
        self._base_dir = Path(work_dir) / "workflows" / "definitions"
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        """Save or overwrite a workflow definition."""
        self._path(definition.workflow_id).write_text(
            json.dumps(definition.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return definition

    def get(self, workflow_id: str) -> WorkflowDefinition | None:
        """Load a workflow definition by id."""
        path = self._path(workflow_id)
        if not path.exists():
            return None
        return WorkflowDefinition.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list(self) -> list[WorkflowDefinition]:
        """List all workflow definitions."""
        definitions: list[WorkflowDefinition] = []
        for path in sorted(self._base_dir.glob("*.json")):
            try:
                definitions.append(
                    WorkflowDefinition.from_dict(json.loads(path.read_text(encoding="utf-8")))
                )
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
        return definitions

    def delete(self, workflow_id: str) -> bool:
        """Delete a workflow definition by id."""
        path = self._path(workflow_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def _path(self, workflow_id: str) -> Path:
        return self._base_dir / f"{workflow_id}.json"
