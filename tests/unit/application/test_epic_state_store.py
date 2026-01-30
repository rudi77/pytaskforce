from pathlib import Path

from taskforce.application.epic_state_store import create_epic_state_store
from taskforce.core.domain.epic import EpicTask, EpicTaskResult


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
    tasks = [EpicTask(task_id="task-1", title="Collect logs", description="Get logs")]
    results = [
        EpicTaskResult(
            task_id="task-1",
            worker_session_id="worker-1",
            status="completed",
            summary="Logs collected.",
        )
    ]

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
