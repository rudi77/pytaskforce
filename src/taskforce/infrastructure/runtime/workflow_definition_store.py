"""File-backed workflow definition store.

Workflow definitions persist as one file per ``workflow_id`` under
``${work_dir}/workflows/definitions/``. Both YAML (``.yaml``) and
JSON (``.json``) are accepted; new definitions are written as YAML
because that's the human-edit format the ADR-022 §7 first-class
workflow story optimises for. Older deployments with ``.json``
definitions on disk continue to load.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from taskforce.core.domain.workflow_definition import WorkflowDefinition


class FileWorkflowDefinitionStore:
    """Persist workflow definitions as YAML (preferred) or JSON files."""

    def __init__(self, work_dir: str = ".taskforce") -> None:
        self._base_dir = Path(work_dir) / "workflows" / "definitions"
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        """Save or overwrite a workflow definition (writes YAML).

        If a legacy ``.json`` file with the same id exists it is
        deleted so the YAML version becomes authoritative on the next
        load.
        """
        target = self._yaml_path(definition.workflow_id)
        target.write_text(
            yaml.safe_dump(definition.to_dict(), sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        legacy_json = self._json_path(definition.workflow_id)
        if legacy_json.exists():
            try:
                legacy_json.unlink()
            except OSError:
                pass
        return definition

    def get(self, workflow_id: str) -> WorkflowDefinition | None:
        """Load a workflow definition by id.

        YAML takes precedence over JSON when both exist (post-migration
        only writes YAML, but a hand-edited JSON could linger).
        """
        yaml_path = self._yaml_path(workflow_id)
        if yaml_path.exists():
            return _load_definition(yaml_path)
        json_path = self._json_path(workflow_id)
        if json_path.exists():
            return _load_definition(json_path)
        return None

    def list(self) -> list[WorkflowDefinition]:
        """List all workflow definitions in the store."""
        seen: set[str] = set()
        definitions: list[WorkflowDefinition] = []
        # Prefer YAML; fall back to JSON for ids only present as JSON.
        for pattern in ("*.yaml", "*.yml", "*.json"):
            for path in sorted(self._base_dir.glob(pattern)):
                if path.stem in seen:
                    continue
                definition = _load_definition(path)
                if definition is None:
                    continue
                seen.add(path.stem)
                definitions.append(definition)
        return definitions

    def delete(self, workflow_id: str) -> bool:
        """Delete a workflow definition (removes both YAML and JSON copies)."""
        removed = False
        for path in (self._yaml_path(workflow_id), self._json_path(workflow_id)):
            if path.exists():
                try:
                    path.unlink()
                    removed = True
                except OSError:
                    continue
        return removed

    def _yaml_path(self, workflow_id: str) -> Path:
        return self._base_dir / f"{workflow_id}.yaml"

    def _json_path(self, workflow_id: str) -> Path:
        return self._base_dir / f"{workflow_id}.json"


def _load_definition(path: Path) -> WorkflowDefinition | None:
    """Load a definition from disk. Returns ``None`` on any parse error."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    try:
        if path.suffix.lower() in (".yaml", ".yml"):
            data: Any = yaml.safe_load(text)
        else:
            data = json.loads(text)
    except (yaml.YAMLError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    try:
        return WorkflowDefinition.from_dict(data)
    except (KeyError, TypeError, ValueError):
        return None
