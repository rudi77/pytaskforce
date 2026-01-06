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
        height: 4;
        width: 100%;
        background: $panel;
        color: $text;
        padding: 0 2;
        border-bottom: solid $primary;
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
        # Create child widgets up-front so reactive watchers can safely update them
        # even before composition/mounting is complete.
        self._title_line = Static(self._render_title(), classes="title-line", id="title-line")
        self._info_line = Static(self._render_info(), classes="info-line", id="info-line")

    def compose(self) -> ComposeResult:
        """Compose header layout."""
        yield self._title_line
        yield self._info_line

    def _render_title(self) -> Text:
        """Render title line."""
        title = Text()
        title.append("TASKFORCE", style="bold bright_white")
        title.append(" - ReAct Agent Framework", style="dim")
        return title

    def _render_info(self) -> Text:
        """Render info line with session, profile, status, and tokens."""
        info = Text()
        info.append(f"Session: ", style="dim")
        info.append(f"{self.session_id[:8]}...", style="dim cyan")
        info.append(f"  │  ", style="dim")
        info.append(f"Profile: ", style="dim")
        info.append(f"{self.profile}", style="bright_white")

        if self.user_context:
            info.append(f"  │  ", style="dim")
            info.append(f"RAG: ", style="dim")
            info.append("enabled", style="dim magenta")

        info.append(f"  │  ", style="dim")
        info.append(f"Status: ", style="dim")
        info.append(self._get_status_text(), style=self._get_status_color())

        if self.token_count > 0:
            info.append(f"  │  ", style="dim")
            info.append(f"🎯 Tokens: ", style="dim")
            info.append(f"{self.token_count:,}", style="dim cyan")

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
            "Idle": "dim white",
            "Initializing": "yellow",
            "Thinking": "dim cyan",
            "Working": "cyan",
            "Calling Tool": "yellow",
            "Processing": "dim magenta",
            "Responding": "green",
            "Complete": "green",
            "Error": "red",
        }
        return status_colors.get(self.status, "dim white")

    def watch_status(self, new_status: str) -> None:
        """React to status changes.

        Args:
            new_status: New status value
        """
        # Update info line when status changes
        if not hasattr(self, "_info_line"):
            return
        self._info_line.update(self._render_info())

    def watch_token_count(self, new_count: int) -> None:
        """React to token count changes.

        Args:
            new_count: New token count
        """
        # Update info line when token count changes
        if not hasattr(self, "_info_line"):
            return
        self._info_line.update(self._render_info())

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
