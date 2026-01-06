"""Sidebar widget with directory tree navigation."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container
from textual.reactive import reactive
from textual.widgets import DirectoryTree, Static


class Sidebar(Container):
    """Collapsible sidebar with directory tree navigation."""

    DEFAULT_CSS = """
    Sidebar {
        width: 30%;
        height: 100%;
        background: $panel;
        border-right: solid $primary;
        padding: 1;
    }

    Sidebar.hidden {
        display: none;
    }

    Sidebar .sidebar-title {
        width: 100%;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    Sidebar DirectoryTree {
        width: 100%;
        height: 1fr;
        background: $panel;
        scrollbar-gutter: stable;
    }
    """

    visible = reactive(True)

    def __init__(self, root_path: str | None = None, **kwargs):
        """Initialize sidebar.

        Args:
            root_path: Root directory path (defaults to cwd)
        """
        super().__init__(**kwargs)
        self.root_path = Path(root_path) if root_path else Path.cwd()

    def compose(self) -> ComposeResult:
        """Compose sidebar layout."""
        yield Static("Directory Tree", classes="sidebar-title")
        yield DirectoryTree(str(self.root_path))

    def watch_visible(self, new_visible: bool) -> None:
        """React to visibility changes.

        Args:
            new_visible: New visibility state
        """
        if new_visible:
            self.remove_class("hidden")
        else:
            self.add_class("hidden")

    def toggle_visibility(self) -> bool:
        """Toggle sidebar visibility.

        Returns:
            New visibility state
        """
        self.visible = not self.visible
        return self.visible
