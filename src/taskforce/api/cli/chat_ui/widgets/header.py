"""Header widget displaying session info and status."""

from typing import Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Static


class Header(Static):
    """Header bar showing session info, profile, tokens, and status."""

    DEFAULT_CSS = """
    Header {
        dock: top;
        height: 3;
        width: 100%;
        background: $primary;
        color: $text;
        padding: 1 2;
    }

    Header .title-line {
        width: 100%;
        text-style: bold;
    }

    Header .info-line {
        width: 100%;
        color: $text-muted;
    }
    """

    # Reactive attributes for live updates
    status = reactive("Idle")
    token_count = reactive(0)

    def __init__(
        self,
        session_id: str,
        profile: str,
        user_context: Optional[dict] = None,
        **kwargs,
    ):
        """Initialize header.

        Args:
            session_id: Current session ID
            profile: Configuration profile
            user_context: Optional RAG user context
        """
        super().__init__(**kwargs)
        self.session_id = session_id
        self.profile = profile
        self.user_context = user_context

    def compose(self) -> ComposeResult:
        """Compose header layout."""
        yield Static(self._render_title(), classes="title-line", id="title-line")
        yield Static(self._render_info(), classes="info-line", id="info-line")

    def _render_title(self) -> Text:
        """Render title line."""
        title = Text()
        title.append("TASKFORCE", style="bold cyan")
        title.append(" - ReAct Agent Framework", style="bold blue")
        return title

    def _render_info(self) -> Text:
        """Render info line with session, profile, status, and tokens."""
        info = Text()
        info.append(f"Session: ", style="dim")
        info.append(f"{self.session_id[:8]}...", style="cyan")
        info.append(f"  │  ", style="dim")
        info.append(f"Profile: ", style="dim")
        info.append(f"{self.profile}", style="yellow")

        if self.user_context:
            info.append(f"  │  ", style="dim")
            info.append(f"RAG: ", style="dim")
            info.append("enabled", style="magenta")

        info.append(f"  │  ", style="dim")
        info.append(f"Status: ", style="dim")
        info.append(self._get_status_text(), style=self._get_status_color())

        if self.token_count > 0:
            info.append(f"  │  ", style="dim")
            info.append(f"🎯 Tokens: ", style="dim")
            info.append(f"{self.token_count:,}", style="cyan")

        return info

    def _get_status_text(self) -> str:
        """Get status display text with icon."""
        status_icons = {
            "Idle": "💤",
            "Initializing": "🔄",
            "Thinking": "🧠",
            "Working": "⚙️",
            "Calling Tool": "🔧",
            "Processing": "⚡",
            "Responding": "💬",
            "Complete": "✅",
            "Error": "❌",
        }
        icon = status_icons.get(self.status, "❓")
        return f"{icon} {self.status}"

    def _get_status_color(self) -> str:
        """Get color for current status."""
        status_colors = {
            "Idle": "white",
            "Initializing": "yellow",
            "Thinking": "blue",
            "Working": "cyan",
            "Calling Tool": "yellow",
            "Processing": "magenta",
            "Responding": "green",
            "Complete": "green",
            "Error": "red",
        }
        return status_colors.get(self.status, "white")

    def watch_status(self, new_status: str) -> None:
        """React to status changes.

        Args:
            new_status: New status value
        """
        # Update info line when status changes
        info_line = self.query_one("#info-line", Static)
        info_line.update(self._render_info())

    def watch_token_count(self, new_count: int) -> None:
        """React to token count changes.

        Args:
            new_count: New token count
        """
        # Update info line when token count changes
        info_line = self.query_one("#info-line", Static)
        info_line.update(self._render_info())

    def update_status(self, status: str) -> None:
        """Update the status display.

        Args:
            status: New status text
        """
        self.status = status

    def update_tokens(self, count: int) -> None:
        """Update the token count.

        Args:
            count: New token count
        """
        self.token_count = count

    def add_tokens(self, count: int) -> None:
        """Add to the token count.

        Args:
            count: Tokens to add
        """
        self.token_count += count
