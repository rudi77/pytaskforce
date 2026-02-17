"""File-backed state tracking for epic orchestration runs."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from taskforce.core.domain.epic import EpicTask, EpicTaskResult
from taskforce.core.utils.time import utc_now

_logger = structlog.get_logger(__name__)


def _utc_timestamp() -> str:
    """Return an ISO timestamp in UTC."""
    return utc_now().isoformat()


def _atomic_write(path: Path, content: str) -> None:
    """Write content atomically via write-to-temp + rename.

    Ensures readers never see a partially written file. On POSIX systems
    ``os.replace`` is atomic when source and destination are on the same
    filesystem (guaranteed here because the temp file lives in the same
    directory).
    """
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, str(path))
    except BaseException:
        # Clean up the temp file on any failure.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _atomic_append(path: Path, entry: str) -> None:
    """Append *entry* to *path* atomically by rewriting the entire file.

    This avoids partial appends on crash: readers always see either the
    old content or the old content plus the complete new entry.
    """
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    _atomic_write(path, existing + entry)


@dataclass(frozen=True)
class EpicStatePaths:
    """File locations for a persisted epic run state."""

    base_dir: Path
    mission_path: Path
    current_state_path: Path
    memory_path: Path
    checkpoint_path: Path


def resolve_epic_state_paths(run_id: str, root_dir: Path | None = None) -> EpicStatePaths:
    """Resolve file locations for an epic run."""
    root = root_dir or Path(".taskforce") / "epic_runs"
    base_dir = root / run_id
    return EpicStatePaths(
        base_dir=base_dir,
        mission_path=base_dir / "MISSION.md",
        current_state_path=base_dir / "CURRENT_STATE.md",
        memory_path=base_dir / "MEMORY.md",
        checkpoint_path=base_dir / "CHECKPOINT.json",
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
        """Overwrite the current state snapshot atomically."""
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
        _atomic_write(self._paths.current_state_path, content)

    def append_memory(
        self,
        *,
        round_index: int,
        judge_summary: str,
        tasks: list[EpicTask],
        worker_results: list[EpicTaskResult],
    ) -> None:
        """Append a round entry to the memory log atomically."""
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
        _atomic_append(self._paths.memory_path, entry)

    def save_checkpoint(
        self,
        *,
        last_completed_round: int,
        tasks: list[EpicTask],
        worker_results: list[EpicTaskResult],
        round_summaries: list[dict[str, Any]],
        status: str,
    ) -> None:
        """Persist a checkpoint so the run can resume after a crash.

        The checkpoint captures all accumulated state after a round completes.
        It is written atomically — readers see either the previous checkpoint
        or the new one, never a partial write.
        """
        payload = {
            "last_completed_round": last_completed_round,
            "status": status,
            "tasks": [t.to_dict() for t in tasks],
            "worker_results": [r.to_dict() for r in worker_results],
            "round_summaries": round_summaries,
            "saved_at": _utc_timestamp(),
        }
        _atomic_write(self._paths.checkpoint_path, json.dumps(payload, indent=2))

    def load_checkpoint(self) -> dict[str, Any] | None:
        """Load a previously saved checkpoint, or *None* if none exists.

        Returns a dict with keys ``last_completed_round``, ``status``,
        ``tasks``, ``worker_results``, and ``round_summaries``.
        """
        if not self._paths.checkpoint_path.exists():
            return None
        try:
            raw = self._paths.checkpoint_path.read_text(encoding="utf-8")
            return json.loads(raw)  # type: ignore[no-any-return]
        except (json.JSONDecodeError, OSError) as exc:
            _logger.warning(
                "epic.checkpoint_load_failed",
                error=str(exc),
                path=str(self._paths.checkpoint_path),
            )
            return None

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
