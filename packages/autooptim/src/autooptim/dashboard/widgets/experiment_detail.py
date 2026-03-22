"""Experiment detail widget showing the latest experiment info."""

from __future__ import annotations

from textual.widgets import Static

from autooptim.dashboard.data_loader import DashboardData
from autooptim.models import ExperimentStatus


class ExperimentDetail(Static):
    """Shows detailed info about the latest experiment."""

    DEFAULT_CSS = """
    ExperimentDetail {
        height: auto;
        min-height: 6;
        border: solid $primary;
        padding: 0 1;
    }
    """

    def update_data(self, data: DashboardData) -> None:
        """Refresh with latest experiment details."""
        if data.latest is None:
            self.update("[dim]No experiments yet[/]")
            return

        r = data.latest
        delta = r.composite_score - r.baseline_composite
        sign = "+" if delta >= 0 else ""

        # Status coloring
        status_colors = {
            ExperimentStatus.KEPT: "green",
            ExperimentStatus.DISCARDED: "red",
            ExperimentStatus.ERROR: "yellow",
            ExperimentStatus.BASELINE: "blue",
        }
        color = status_colors.get(r.status, "white")
        status_text = f"[{color}]{r.status.value.upper()}[/]"

        files = ", ".join(r.files_modified) if r.files_modified else "none"
        duration = f"{r.duration_seconds:.1f}s" if r.duration_seconds else "-"

        lines = [
            f"[bold]Latest: #{r.experiment_id}[/] [{r.category}] {status_text} ({sign}{delta:.4f})",
            f'"{r.description}"',
            f"[dim]Hypothesis:[/] {r.hypothesis}",
            f"[dim]Files:[/] {files}",
            f"[dim]Duration:[/] {duration}  [dim]Cost:[/] ${r.eval_cost_usd:.4f}",
        ]
        self.update("\n".join(lines))
