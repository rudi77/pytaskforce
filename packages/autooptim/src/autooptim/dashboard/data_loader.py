"""Data bridge between TSV experiment log and dashboard widgets."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from autooptim.experiment_log import ExperimentLog
from autooptim.models import ExperimentResult, ExperimentStatus, RunConfig


@dataclass
class DashboardData:
    """Aggregated view of all experiment data for dashboard rendering."""

    results: list[ExperimentResult] = field(default_factory=list)
    is_running: bool = False
    total_cost: float = 0.0
    kept_count: int = 0
    discarded_count: int = 0
    error_count: int = 0
    categories: dict[str, dict[str, int]] = field(default_factory=dict)
    latest: ExperimentResult | None = None
    score_names: list[str] = field(default_factory=list)
    max_iterations: int | None = None
    max_cost_usd: float | None = None
    run_name: str = "optimization"


class DashboardDataLoader:
    """Loads experiment data from TSV log for the dashboard.

    Reuses ExperimentLog.read_all() for all TSV parsing.
    Checks .autooptim_state.json for is_running status.
    """

    def __init__(self, log_path: Path, config: RunConfig | None = None) -> None:
        self._log = ExperimentLog(log_path)
        self._log_path = log_path
        self._config = config
        self._last_mtime: float = 0.0

    def has_changed(self) -> bool:
        """Check if the TSV file has been modified since last load."""
        try:
            mtime = self._log_path.stat().st_mtime
        except FileNotFoundError:
            return False
        if mtime != self._last_mtime:
            return True
        return False

    def load(self) -> DashboardData:
        """Load all experiment data and aggregate for dashboard display."""
        try:
            self._last_mtime = self._log_path.stat().st_mtime
        except FileNotFoundError:
            return DashboardData()

        try:
            results = self._log.read_all()
        except PermissionError:
            # File may be locked on Windows during write
            return DashboardData()

        data = DashboardData(results=results)

        # Running status: check state file existence
        state_file = self._log_path.parent.parent / ".autooptim_state.json"
        if not state_file.exists():
            # Also check project root
            state_file = Path(".autooptim_state.json")
        data.is_running = state_file.exists()

        # Aggregate counts
        for r in results:
            if r.status == ExperimentStatus.KEPT:
                data.kept_count += 1
            elif r.status == ExperimentStatus.DISCARDED:
                data.discarded_count += 1
            elif r.status == ExperimentStatus.ERROR:
                data.error_count += 1

            # Per-category stats
            cat = r.category
            if cat not in data.categories:
                data.categories[cat] = {"kept": 0, "discarded": 0, "error": 0, "total": 0}
            data.categories[cat]["total"] += 1
            if r.status == ExperimentStatus.KEPT:
                data.categories[cat]["kept"] += 1
            elif r.status == ExperimentStatus.DISCARDED:
                data.categories[cat]["discarded"] += 1
            elif r.status == ExperimentStatus.ERROR:
                data.categories[cat]["error"] += 1

        # Total cost
        data.total_cost = sum(r.eval_cost_usd for r in results)

        # Latest result (skip baseline)
        non_baseline = [r for r in results if r.status != ExperimentStatus.BASELINE]
        data.latest = non_baseline[-1] if non_baseline else (results[-1] if results else None)

        # Score names from first result with scores
        for r in results:
            if r.scores.values:
                data.score_names = list(r.scores.values.keys())
                break

        # Config-derived fields
        if self._config:
            data.max_iterations = self._config.max_iterations or None
            data.max_cost_usd = self._config.max_cost_usd
            data.run_name = self._config.name

        return data
