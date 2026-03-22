"""Score trend chart widget using textual-plotext or sparkline fallback."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from autooptim.dashboard.data_loader import DashboardData
from autooptim.models import ExperimentStatus

try:
    from textual_plotext import PlotextPlot

    HAS_PLOTEXT = True
except ImportError:
    HAS_PLOTEXT = False


class ScoreChart(Vertical):
    """Composite score trend chart with color-coded markers."""

    DEFAULT_CSS = """
    ScoreChart {
        height: 1fr;
        min-height: 10;
        border: solid $primary;
        padding: 0 1;
    }
    """

    def __init__(self, show_per_metric: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self._show_per_metric = show_per_metric
        self._plot: PlotextPlot | None = None
        self._fallback: Static | None = None

    def compose(self) -> ComposeResult:
        if HAS_PLOTEXT:
            self._plot = PlotextPlot()
            yield self._plot
        else:
            self._fallback = Static("Score Trend (install textual-plotext for chart)")
            yield self._fallback

    def toggle_per_metric(self) -> None:
        """Toggle per-metric lines on the chart."""
        self._show_per_metric = not self._show_per_metric

    def update_data(self, data: DashboardData) -> None:
        """Refresh chart with new experiment data."""
        if not data.results:
            return

        if HAS_PLOTEXT and self._plot is not None:
            self._render_plotext(data)
        elif self._fallback is not None:
            self._render_sparkline(data)

    def _render_plotext(self, data: DashboardData) -> None:
        """Render full chart with textual-plotext."""
        plt = self._plot.plt  # type: ignore[union-attr]
        plt.clear_data()
        plt.clear_figure()
        plt.title("Composite Score Trend")
        plt.xlabel("Experiment")
        plt.ylabel("Score")

        # Separate by status for color-coding
        status_groups: dict[str, tuple[list[int], list[float], str]] = {
            "kept": ([], [], "green"),
            "discarded": ([], [], "red"),
            "error": ([], [], "yellow"),
            "baseline": ([], [], "blue"),
        }

        for r in data.results:
            group = status_groups.get(r.status.value)
            if group:
                group[0].append(r.experiment_id)
                group[1].append(r.composite_score)

        for label, (x_vals, y_vals, color) in status_groups.items():
            if x_vals:
                plt.scatter(x_vals, y_vals, label=label, color=color, marker="dot")

        # Composite line (all experiments, sorted)
        all_x = [r.experiment_id for r in data.results]
        all_y = [r.composite_score for r in data.results]
        if all_x:
            plt.plot(all_x, all_y, color="white")

        # Optional per-metric lines
        if self._show_per_metric and data.score_names:
            colors = ["cyan", "magenta", "yellow+", "green+"]
            for i, name in enumerate(data.score_names):
                m_x = []
                m_y = []
                for r in data.results:
                    val = r.scores.get(name)
                    if val > 0:
                        m_x.append(r.experiment_id)
                        m_y.append(val)
                if m_x:
                    color = colors[i % len(colors)]
                    plt.plot(m_x, m_y, label=name, color=color)

        self._plot.refresh()  # type: ignore[union-attr]

    def _render_sparkline(self, data: DashboardData) -> None:
        """Render a simple text-based sparkline fallback."""
        if not data.results:
            self._fallback.update("No data yet")  # type: ignore[union-attr]
            return

        scores = [r.composite_score for r in data.results]
        min_s, max_s = min(scores), max(scores)
        spread = max_s - min_s if max_s > min_s else 1.0
        blocks = " ▁▂▃▄▅▆▇█"

        spark = ""
        for s in scores:
            idx = int((s - min_s) / spread * (len(blocks) - 1))
            spark += blocks[idx]

        latest = scores[-1]
        self._fallback.update(  # type: ignore[union-attr]
            f"Score Trend: {spark}  (latest: {latest:.4f})"
        )
