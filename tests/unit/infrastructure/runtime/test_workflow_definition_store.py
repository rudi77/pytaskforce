"""Tests for the YAML/JSON-tolerant workflow definition store (ADR-022 §7)."""

from __future__ import annotations

from pathlib import Path

import yaml

from taskforce.core.domain.workflow_definition import (
    WORKFLOW_TRIGGER_SCHEDULE,
    WorkflowDefinition,
    WorkflowStep,
)
from taskforce.infrastructure.runtime.workflow_definition_store import (
    FileWorkflowDefinitionStore,
)


def _sample_definition(workflow_id: str = "wf-1") -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id=workflow_id,
        name="Daily Report",
        description="Run the morning report.",
        trigger=WORKFLOW_TRIGGER_SCHEDULE,
        trigger_config={"cron": "0 8 * * *"},
        steps=[
            WorkflowStep(step_id="fetch", agent="reporter", task="fetch numbers"),
            WorkflowStep(
                step_id="summarise",
                agent="reporter",
                task="write the summary",
                depends_on=["fetch"],
            ),
        ],
    )


def test_save_writes_yaml_and_round_trips(tmp_path: Path) -> None:
    store = FileWorkflowDefinitionStore(work_dir=str(tmp_path))
    definition = _sample_definition()

    store.save(definition)

    yaml_file = tmp_path / "workflows" / "definitions" / "wf-1.yaml"
    assert yaml_file.exists()

    raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
    assert raw["trigger"] == "schedule"
    assert raw["trigger_config"] == {"cron": "0 8 * * *"}

    loaded = store.get("wf-1")
    assert loaded == definition


def test_legacy_json_still_loads(tmp_path: Path) -> None:
    """Pre-ADR-022 deployments wrote JSON without trigger_config — keep loading."""
    base = tmp_path / "workflows" / "definitions"
    base.mkdir(parents=True)
    (base / "legacy.json").write_text(
        '{"workflow_id": "legacy", "name": "Legacy", "trigger": "manual", "steps": []}',
        encoding="utf-8",
    )

    store = FileWorkflowDefinitionStore(work_dir=str(tmp_path))
    loaded = store.get("legacy")

    assert loaded is not None
    assert loaded.workflow_id == "legacy"
    assert loaded.trigger == "manual"
    assert loaded.trigger_config == {}


def test_save_replaces_legacy_json_with_yaml(tmp_path: Path) -> None:
    base = tmp_path / "workflows" / "definitions"
    base.mkdir(parents=True)
    legacy_path = base / "wf-1.json"
    legacy_path.write_text(
        '{"workflow_id": "wf-1", "name": "Old", "trigger": "manual", "steps": []}',
        encoding="utf-8",
    )

    store = FileWorkflowDefinitionStore(work_dir=str(tmp_path))
    store.save(_sample_definition())

    assert (base / "wf-1.yaml").exists()
    assert not legacy_path.exists()


def test_yaml_with_inline_trigger_dict(tmp_path: Path) -> None:
    """Hand-written YAML with the alternative trigger: {kind, config} shape."""
    base = tmp_path / "workflows" / "definitions"
    base.mkdir(parents=True)
    (base / "inline.yaml").write_text(
        """
workflow_id: inline
name: Inline Trigger
description: ""
trigger:
  kind: webhook
  config:
    path: /hooks/run
steps: []
metadata: {}
""",
        encoding="utf-8",
    )

    store = FileWorkflowDefinitionStore(work_dir=str(tmp_path))
    loaded = store.get("inline")

    assert loaded is not None
    assert loaded.trigger == "webhook"
    assert loaded.trigger_config == {"path": "/hooks/run"}


def test_list_prefers_yaml_over_json(tmp_path: Path) -> None:
    base = tmp_path / "workflows" / "definitions"
    base.mkdir(parents=True)
    # YAML and JSON for the same id with different content — YAML must win.
    (base / "dup.yaml").write_text(
        "workflow_id: dup\nname: From YAML\ntrigger: manual\nsteps: []\n",
        encoding="utf-8",
    )
    (base / "dup.json").write_text(
        '{"workflow_id": "dup", "name": "From JSON", "trigger": "manual", "steps": []}',
        encoding="utf-8",
    )
    (base / "only-json.json").write_text(
        '{"workflow_id": "only-json", "name": "Only JSON", "trigger": "manual", "steps": []}',
        encoding="utf-8",
    )

    store = FileWorkflowDefinitionStore(work_dir=str(tmp_path))
    definitions = {d.workflow_id: d.name for d in store.list()}

    assert definitions["dup"] == "From YAML"
    assert definitions["only-json"] == "Only JSON"


def test_delete_removes_both_formats(tmp_path: Path) -> None:
    base = tmp_path / "workflows" / "definitions"
    base.mkdir(parents=True)
    (base / "wf-1.yaml").write_text(
        "workflow_id: wf-1\nname: x\ntrigger: manual\nsteps: []\n",
        encoding="utf-8",
    )
    (base / "wf-1.json").write_text(
        '{"workflow_id": "wf-1", "name": "x", "trigger": "manual", "steps": []}',
        encoding="utf-8",
    )

    store = FileWorkflowDefinitionStore(work_dir=str(tmp_path))
    assert store.delete("wf-1") is True
    assert not (base / "wf-1.yaml").exists()
    assert not (base / "wf-1.json").exists()
