"""File-backed state tracking for epic orchestration runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from taskforce.core.domain.epic import EpicTask, EpicTaskResult


def _utc_timestamp() -> str:
    """Return an ISO timestamp in UTC."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class EpicStatePaths:
    """File locations for a persisted epic run state."""

    base_dir: Path
    mission_path: Path
    current_state_path: Path
    memory_path: Path


def resolve_epic_state_paths(run_id: str, root_dir: Path | None = None) -> EpicStatePaths:
    """Resolve file locations for an epic run."""
    root = root_dir or Path(".taskforce") / "epic_runs"
    base_dir = root / run_id
    return EpicStatePaths(
        base_dir=base_dir,
        mission_path=base_dir / "MISSION.md",
        current_state_path=base_dir / "CURRENT_STATE.md",
        memory_path=base_dir / "MEMORY.md",
    )


class EpicStateStore:
    """Persist mission and progress state to Markdown files."""

    def __init__(self, paths: EpicStatePaths) -> None:
        self._paths = paths

    @property
    def paths(self) -> EpicStatePaths:
        """Return resolved file paths."""
        return self._paths

    def initialize(self, mission: str) -> None:
        """Create state files if they do not exist."""
        self._paths.base_dir.mkdir(parents=True, exist_ok=True)
        self._write_if_missing(
            self._paths.mission_path,
            f"# Mission (Desired State)\n\n{mission.strip()}\n",
        )
        self._write_if_missing(
            self._paths.current_state_path,
            "# Current State\n\n_No progress recorded yet._\n",
        )
        self._write_if_missing(
            self._paths.memory_path,
            "# Epic Memory Log\n\n",
        )

    def update_current_state(
        self,
        *,
        round_index: int,
        judge_summary: str,
        tasks: list[EpicTask],
        worker_results: list[EpicTaskResult],
    ) -> None:
        """Overwrite the current state snapshot."""
        content = "\n".join(
            [
                "# Current State",
                f"Last updated: {_utc_timestamp()}",
                f"Round: {round_index}",
                "",
                "## Latest Judge Summary",
                judge_summary.strip() or "_No summary provided._",
                "",
                "## Task Outcomes",
                _format_task_outcomes(worker_results) or "_No worker results._",
                "",
                "## Planned Tasks (Latest Round)",
                _format_task_list(tasks) or "_No tasks planned._",
                "",
            ]
        )
        self._paths.current_state_path.write_text(content, encoding="utf-8")

    def append_memory(
        self,
        *,
        round_index: int,
        judge_summary: str,
        tasks: list[EpicTask],
        worker_results: list[EpicTaskResult],
    ) -> None:
        """Append a round entry to the memory log."""
        entry = "\n".join(
            [
                f"## Round {round_index} ({_utc_timestamp()})",
                "",
                "### Judge Summary",
                judge_summary.strip() or "_No summary provided._",
                "",
                "### Tasks Planned",
                _format_task_list(tasks) or "_No tasks planned._",
                "",
                "### Worker Results",
                _format_task_outcomes(worker_results) or "_No worker results._",
                "",
            ]
        )
        with self._paths.memory_path.open("a", encoding="utf-8") as handle:
            handle.write(entry)

    def format_state_context(self) -> str:
        """Return a prompt snippet describing state file locations."""
        return "\n".join(
            [
                "State files for this epic run (read before planning):",
                f"- Desired state (mission): {self._paths.mission_path.as_posix()}",
                f"- Current state: {self._paths.current_state_path.as_posix()}",
                f"- Memory log: {self._paths.memory_path.as_posix()}",
            ]
        )

    @staticmethod
    def _write_if_missing(path: Path, content: str) -> None:
        """Write content if the file does not already exist."""
        if not path.exists():
            path.write_text(content, encoding="utf-8")


def _format_task_outcomes(worker_results: list[EpicTaskResult]) -> str:
    """Format worker results as a Markdown list."""
    return "\n".join(
        f"- {result.task_id}: {result.status} — {result.summary.strip()}"
        for result in worker_results
    )


def _format_task_list(tasks: list[EpicTask]) -> str:
    """Format tasks as a Markdown list."""
    return "\n".join(
        f"- {task.task_id}: {task.title} ({task.source})" for task in tasks
    )


def create_epic_state_store(run_id: str, root_dir: Path | None = None) -> EpicStateStore:
    """Create a state store for an epic run."""
    paths = resolve_epic_state_paths(run_id, root_dir=root_dir)
    return EpicStateStore(paths)
