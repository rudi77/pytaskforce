"""Category statistics widget showing kept/discarded/error counts per category."""

from __future__ import annotations

from textual.widgets import DataTable

from autooptim.dashboard.data_loader import DashboardData


class CategoryStats(DataTable):
    """DataTable showing per-category experiment outcomes."""

    DEFAULT_CSS = """
    CategoryStats {
        height: auto;
        max-height: 12;
        border: solid $primary;
    }
    """

    def on_mount(self) -> None:
        self.add_columns("Category", "Kept", "Disc", "Err", "Rate")
        self.cursor_type = "none"

    def update_data(self, data: DashboardData) -> None:
        """Refresh category stats."""
        self.clear()

        total_kept = 0
        total_total = 0

        for cat, stats in sorted(data.categories.items()):
            kept = stats["kept"]
            disc = stats["discarded"]
            err = stats["error"]
            total = stats["total"]
            rate = f"{(kept / total * 100):.0f}%" if total > 0 else "-"

            self.add_row(cat, str(kept), str(disc), str(err), rate)
            total_kept += kept
            total_total += total

        if data.categories:
            overall_rate = f"{(total_kept / total_total * 100):.0f}%" if total_total > 0 else "-"
            self.add_row("[bold]TOTAL[/]", str(total_kept), str(data.discarded_count),
                         str(data.error_count), overall_rate)
