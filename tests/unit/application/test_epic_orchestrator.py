from pathlib import Path

from taskforce.application.epic_orchestrator import (
    EpicOrchestrator,
    _parse_json_object,
    _parse_task_payload,
)
from taskforce.application.epic_state_store import create_epic_state_store
from taskforce.core.domain.epic import EpicTask, EpicTaskResult


def test_parse_tasks_from_json() -> None:
    orchestrator = EpicOrchestrator()
    output = (
        """
```json
[
  {
    "title": "Task A",
    "description": "Do A",
    "acceptance_criteria": ["done"]
  }
]
```
"""
    )
    tasks = orchestrator._parse_tasks(output, "planner")

    assert len(tasks) == 1
    assert tasks[0].title == "Task A"
    assert tasks[0].acceptance_criteria == ["done"]


def test_deduplicate_tasks() -> None:
    orchestrator = EpicOrchestrator()
    tasks = orchestrator._parse_tasks("- Task A\n- Task A", "planner")

    deduped = orchestrator._deduplicate_tasks(tasks)

    assert len(deduped) == 1


def test_parse_judge_decision() -> None:
    orchestrator = EpicOrchestrator()
    output = (
        "```json\n"
        "{ \"summary\": \"round ok\", \"continue\": true }\n"
        "```"
    )

    decision = orchestrator._parse_judge_decision(output)

    assert decision["summary"] == "round ok"
    assert decision["continue"] is True


# --- JSON parse logging tests ---


def test_parse_task_payload_returns_empty_on_invalid_json() -> None:
    """Invalid JSON should return an empty list (and log a warning)."""
    result = _parse_task_payload("not json at all")
    assert result == []


def test_parse_task_payload_returns_empty_on_non_list_json() -> None:
    """A JSON object (not array) should return an empty list."""
    result = _parse_task_payload('{"key": "value"}')
    assert result == []


def test_parse_json_object_returns_empty_on_invalid_json() -> None:
    """Invalid JSON should return an empty dict (and log a warning)."""
    result = _parse_json_object("{broken")
    assert result == {}


def test_parse_json_object_returns_empty_on_non_dict() -> None:
    """A JSON array should return an empty dict."""
    result = _parse_json_object("[1, 2, 3]")
    assert result == {}


# --- Checkpoint restore test ---


def test_restore_checkpoint_returns_defaults_when_no_checkpoint() -> None:
    """With no checkpoint file, _restore_checkpoint returns empty lists and round 1."""
    orchestrator = EpicOrchestrator()
    # Use a real state store with tmp_path would need pytest fixture;
    # instead test via a state store that has no checkpoint file
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        store = create_epic_state_store("run-test", root_dir=Path(tmpdir))
        store.initialize("test")
        tasks, results, summaries, start = orchestrator._restore_checkpoint(store)
        assert tasks == []
        assert results == []
        assert summaries == []
        assert start == 1


def test_restore_checkpoint_recovers_saved_state() -> None:
    """_restore_checkpoint should recover tasks/results from a checkpoint."""
    orchestrator = EpicOrchestrator()
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        store = create_epic_state_store("run-restore", root_dir=Path(tmpdir))
        store.initialize("restore test")
        tasks = [EpicTask(task_id="t1", title="T1", description="D1")]
        results = [
            EpicTaskResult(
                task_id="t1", worker_session_id="w1", status="completed", summary="done"
            )
        ]
        summaries = [{"round": 1, "summary": "ok", "continue": True}]
        store.save_checkpoint(
            last_completed_round=2,
            tasks=tasks,
            worker_results=results,
            round_summaries=summaries,
            status="completed",
        )

        r_tasks, r_results, r_summaries, start = orchestrator._restore_checkpoint(store)
        assert len(r_tasks) == 1
        assert r_tasks[0].title == "T1"
        assert len(r_results) == 1
        assert r_results[0].task_id == "t1"
        assert r_summaries == summaries
        assert start == 3  # resumes after round 2
