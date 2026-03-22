"""Main Textual application for the AutoOptim live dashboard."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static

from autooptim.dashboard.data_loader import DashboardData, DashboardDataLoader
from autooptim.dashboard.widgets.category_stats import CategoryStats
from autooptim.dashboard.widgets.cost_tracker import CostTracker
from autooptim.dashboard.widgets.experiment_detail import ExperimentDetail
from autooptim.dashboard.widgets.metric_table import MetricTable
from autooptim.dashboard.widgets.score_chart import ScoreChart
from autooptim.dashboard.widgets.status_bar import StatusBar
from autooptim.models import RunConfig


class AutoOptimDashboard(App):
    """Live TUI dashboard for monitoring AutoOptim optimization runs."""

    TITLE = "AutoOptim Dashboard"

    CSS = """
    Screen {
        layout: vertical;
    }

    #main-content {
        height: 1fr;
    }

    #top-row {
        height: 1fr;
        min-height: 12;
    }

    #chart-container {
        width: 2fr;
    }

    #side-panel {
        width: 1fr;
        min-width: 30;
    }

    #bottom-row {
        height: auto;
        max-height: 10;
    }

    #tables-row {
        height: auto;
        max-height: 14;
    }

    #metric-container {
        width: 1fr;
    }

    #category-container {
        width: 1fr;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("m", "toggle_metrics", "Toggle metrics"),
    ]

    def __init__(self, log_path: Path, config: RunConfig | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._loader = DashboardDataLoader(log_path, config)
        self._log_path = log_path

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatusBar(id="status-bar")
        with Vertical(id="main-content"):
            with Horizontal(id="top-row"):
                yield ScoreChart(id="chart-container")
                with Vertical(id="side-panel"):
                    yield ExperimentDetail(id="experiment-detail")
                    yield CostTracker(id="cost-tracker")
            with Horizontal(id="tables-row"):
                yield MetricTable(id="metric-container")
                yield CategoryStats(id="category-container")
        yield Footer()

    def on_mount(self) -> None:
        """Start polling and do initial data load."""
        self._do_refresh()
        self.set_interval(2.0, self._poll)

    def _poll(self) -> None:
        """Check for TSV changes and refresh if needed."""
        if self._loader.has_changed():
            self._do_refresh()

    def _do_refresh(self) -> None:
        """Load data and update all widgets."""
        data = self._loader.load()
        self._update_widgets(data)

    def _update_widgets(self, data: DashboardData) -> None:
        """Push new data to all dashboard widgets."""
        self.query_one("#status-bar", StatusBar).update_data(data)
        self.query_one("#chart-container", ScoreChart).update_data(data)
        self.query_one("#experiment-detail", ExperimentDetail).update_data(data)
        self.query_one("#cost-tracker", CostTracker).update_data(data)
        self.query_one("#metric-container", MetricTable).update_data(data)
        self.query_one("#category-container", CategoryStats).update_data(data)

    def action_refresh(self) -> None:
        """Manual refresh via 'r' key."""
        self._do_refresh()

    def action_toggle_metrics(self) -> None:
        """Toggle per-metric lines on chart via 'm' key."""
        chart = self.query_one("#chart-container", ScoreChart)
        chart.toggle_per_metric()
        self._do_refresh()


def run_dashboard(log_path: Path, config: RunConfig | None = None) -> None:
    """Entry point for launching the dashboard."""
    app = AutoOptimDashboard(log_path=log_path, config=config)
    app.run()
