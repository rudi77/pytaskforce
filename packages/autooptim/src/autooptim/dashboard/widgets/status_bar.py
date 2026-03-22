"""Status bar widget showing run name, iteration count, and status."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static

from autooptim.dashboard.data_loader import DashboardData


class StatusBar(Static):
    """Top status bar with run info, iteration count, and budget."""

    DEFAULT_CSS = """
    StatusBar {
        dock: top;
        height: 3;
        background: $primary-background;
        color: $text;
        padding: 0 2;
        content-align: center middle;
    }
    """

    def update_data(self, data: DashboardData) -> None:
        """Refresh the status bar content."""
        # Iteration count (exclude baseline)
        experiment_count = len([r for r in data.results if r.status.value != "baseline"])
        if data.max_iterations:
            iter_text = f"Iteration {experiment_count}/{data.max_iterations}"
        else:
            iter_text = f"Iteration {experiment_count}"

        # Budget
        if data.max_cost_usd:
            pct = (data.total_cost / data.max_cost_usd) * 100 if data.max_cost_usd > 0 else 0
            budget_text = f"Budget: ${data.total_cost:.2f} / ${data.max_cost_usd:.2f} ({pct:.1f}%)"
        else:
            budget_text = f"Cost: ${data.total_cost:.2f}"

        # Status indicator
        status = "[bold green]RUNNING[/]" if data.is_running else "[bold blue]COMPLETED[/]"

        self.update(
            f"[bold]{data.run_name}[/]  |  {iter_text}  |  {budget_text}  |  {status}"
        )
