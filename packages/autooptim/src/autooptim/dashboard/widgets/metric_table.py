"""Metric table widget showing current scores vs baseline."""

from __future__ import annotations

from textual.widgets import DataTable

from autooptim.dashboard.data_loader import DashboardData
from autooptim.models import ExperimentStatus


class MetricTable(DataTable):
    """DataTable showing per-score current vs baseline values."""

    DEFAULT_CSS = """
    MetricTable {
        height: auto;
        max-height: 12;
        border: solid $primary;
    }
    """

    def on_mount(self) -> None:
        self.add_columns("Metric", "Current", "Baseline", "Delta")
        self.cursor_type = "none"

    def update_data(self, data: DashboardData) -> None:
        """Refresh metrics from the latest kept experiment."""
        self.clear()

        if not data.results:
            return

        # Find baseline
        baseline = None
        for r in data.results:
            if r.status == ExperimentStatus.BASELINE:
                baseline = r
                break

        # Find latest kept experiment
        latest_kept = None
        for r in reversed(data.results):
            if r.status == ExperimentStatus.KEPT:
                latest_kept = r
                break

        current = latest_kept or baseline
        if current is None:
            return

        for name in data.score_names:
            cur_val = current.scores.get(name)
            base_val = baseline.scores.get(name) if baseline else 0.0
            delta = cur_val - base_val

            if delta > 0:
                delta_str = f"[green]+{delta:.4f}[/]"
            elif delta < 0:
                delta_str = f"[red]{delta:.4f}[/]"
            else:
                delta_str = f"{delta:.4f}"

            self.add_row(name, f"{cur_val:.4f}", f"{base_val:.4f}", delta_str)

        # Composite row
        cur_comp = current.composite_score
        base_comp = baseline.baseline_composite if baseline else 0.0
        delta_comp = cur_comp - base_comp
        if delta_comp > 0:
            d_str = f"[green]+{delta_comp:.4f}[/]"
        elif delta_comp < 0:
            d_str = f"[red]{delta_comp:.4f}[/]"
        else:
            d_str = f"{delta_comp:.4f}"
        self.add_row("[bold]composite[/]", f"{cur_comp:.4f}", f"{base_comp:.4f}", d_str)
