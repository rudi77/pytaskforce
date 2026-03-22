"""Cost tracker widget showing budget usage."""

from __future__ import annotations

from textual.widgets import Static

from autooptim.dashboard.data_loader import DashboardData


class CostTracker(Static):
    """Compact cost summary with budget percentage and per-experiment average."""

    DEFAULT_CSS = """
    CostTracker {
        height: auto;
        border: solid $primary;
        padding: 0 1;
    }
    """

    def update_data(self, data: DashboardData) -> None:
        """Refresh cost tracking info."""
        experiment_count = len(data.results)
        avg_cost = data.total_cost / experiment_count if experiment_count > 0 else 0.0

        parts = [f"[bold]Total Cost:[/] ${data.total_cost:.2f}"]

        if data.max_cost_usd:
            pct = (data.total_cost / data.max_cost_usd) * 100
            parts.append(f"Budget: ${data.max_cost_usd:.2f} ({pct:.1f}% used)")

        parts.append(f"Avg/experiment: ${avg_cost:.4f}")
        self.update("  |  ".join(parts))
