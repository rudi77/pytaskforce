import json
from pathlib import Path

from taskforce.application.epic_state_store import create_epic_state_store
from taskforce.core.domain.epic import EpicTask, EpicTaskResult


def _sample_tasks() -> list[EpicTask]:
    return [EpicTask(task_id="task-1", title="Collect logs", description="Get logs")]


def _sample_results() -> list[EpicTaskResult]:
    return [
        EpicTaskResult(
            task_id="task-1",
            worker_session_id="worker-1",
            status="completed",
            summary="Logs collected.",
        )
    ]


def test_epic_state_store_writes_state_files(tmp_path: Path) -> None:
    store = create_epic_state_store("run-123", root_dir=tmp_path)
    store.initialize("Deliver payment export flow")

    assert store.paths.mission_path.exists()
    assert store.paths.current_state_path.exists()
    assert store.paths.memory_path.exists()
    assert "Deliver payment export flow" in store.paths.mission_path.read_text()


def test_epic_state_store_updates_current_state_and_memory(tmp_path: Path) -> None:
    store = create_epic_state_store("run-456", root_dir=tmp_path)
    store.initialize("Audit billing export")
    tasks = _sample_tasks()
    results = _sample_results()

    store.update_current_state(
        round_index=1,
        judge_summary="Progress made.",
        tasks=tasks,
        worker_results=results,
    )
    store.append_memory(
        round_index=1,
        judge_summary="Progress made.",
        tasks=tasks,
        worker_results=results,
    )

    current_state = store.paths.current_state_path.read_text()
    memory_log = store.paths.memory_path.read_text()

    assert "Progress made." in current_state
    assert "Collect logs" in current_state
    assert "Round 1" in memory_log
    assert "Logs collected." in memory_log


def test_atomic_write_is_not_partial_on_current_state(tmp_path: Path) -> None:
    """Verify update_current_state overwrites fully (no leftover content)."""
    store = create_epic_state_store("run-atomic", root_dir=tmp_path)
    store.initialize("Atomic test")
    tasks = _sample_tasks()
    results = _sample_results()

    store.update_current_state(
        round_index=1, judge_summary="Round 1 done.", tasks=tasks, worker_results=results
    )
    store.update_current_state(
        round_index=2, judge_summary="Round 2 done.", tasks=tasks, worker_results=results
    )

    content = store.paths.current_state_path.read_text()
    assert "Round: 2" in content
    assert "Round: 1" not in content


def test_atomic_append_preserves_previous_entries(tmp_path: Path) -> None:
    """Verify append_memory keeps all previous round entries."""
    store = create_epic_state_store("run-append", root_dir=tmp_path)
    store.initialize("Append test")
    tasks = _sample_tasks()
    results = _sample_results()

    store.append_memory(
        round_index=1, judge_summary="R1.", tasks=tasks, worker_results=results
    )
    store.append_memory(
        round_index=2, judge_summary="R2.", tasks=tasks, worker_results=results
    )

    content = store.paths.memory_path.read_text()
    assert "## Round 1" in content
    assert "## Round 2" in content
    assert "R1." in content
    assert "R2." in content


def test_save_and_load_checkpoint(tmp_path: Path) -> None:
    """Verify checkpoint round-trip serialization."""
    store = create_epic_state_store("run-ckpt", root_dir=tmp_path)
    store.initialize("Checkpoint test")
    tasks = _sample_tasks()
    results = _sample_results()
    summaries = [{"round": 1, "summary": "ok", "continue": True}]

    store.save_checkpoint(
        last_completed_round=1,
        tasks=tasks,
        worker_results=results,
        round_summaries=summaries,
        status="completed",
    )

    checkpoint = store.load_checkpoint()
    assert checkpoint is not None
    assert checkpoint["last_completed_round"] == 1
    assert checkpoint["status"] == "completed"
    assert len(checkpoint["tasks"]) == 1
    assert checkpoint["tasks"][0]["title"] == "Collect logs"
    assert len(checkpoint["worker_results"]) == 1
    assert checkpoint["round_summaries"] == summaries


def test_load_checkpoint_returns_none_when_missing(tmp_path: Path) -> None:
    """load_checkpoint returns None when no checkpoint file exists."""
    store = create_epic_state_store("run-no-ckpt", root_dir=tmp_path)
    store.initialize("No checkpoint")

    assert store.load_checkpoint() is None


def test_load_checkpoint_returns_none_on_corrupt_file(tmp_path: Path) -> None:
    """load_checkpoint returns None when the checkpoint file is corrupt."""
    store = create_epic_state_store("run-corrupt", root_dir=tmp_path)
    store.initialize("Corrupt test")
    store.paths.checkpoint_path.write_text("not valid json {{{", encoding="utf-8")

    assert store.load_checkpoint() is None


def test_checkpoint_path_exists_in_paths(tmp_path: Path) -> None:
    """Verify checkpoint_path is part of EpicStatePaths."""
    store = create_epic_state_store("run-paths", root_dir=tmp_path)
    assert store.paths.checkpoint_path.name == "CHECKPOINT.json"
