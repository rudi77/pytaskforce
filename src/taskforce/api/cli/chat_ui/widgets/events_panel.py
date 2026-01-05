"""Events panel widget for displaying execution progress events."""

from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Static

from taskforce.application.executor import ProgressUpdate


class EventsPanel(VerticalScroll):
    """Scrollable panel displaying execution progress events."""

    DEFAULT_CSS = """
    EventsPanel {
        width: 100%;
        height: 6;
        max-height: 8;
        background: $panel;
        border-top: solid $accent;
        padding: 0 1;
        scrollbar-gutter: stable;
    }

    EventsPanel.hidden {
        display: none;
    }

    EventsPanel > Static {
        width: 100%;
        height: auto;
    }
    """

    def __init__(self, max_events: int = 100, **kwargs):
        """Initialize events panel.

        Args:
            max_events: Maximum number of events to keep (ring buffer)
        """
        super().__init__(**kwargs)
        self.max_events = max_events
        self.auto_scroll = True

    def add_event(self, update: ProgressUpdate) -> None:
        """Add a progress update event to the panel.

        Args:
            update: Progress update event
        """
        # Skip llm_token events to avoid flooding
        if update.event_type == "llm_token":
            return

        # Ring buffer: remove oldest if limit exceeded
        if len(self.children) >= self.max_events:
            if self.children:
                self.children[0].remove()

        # Create and mount event widget
        event_widget = Static(self._format_event(update))
        self.mount(event_widget)

        # Show panel when events arrive
        self.remove_class("hidden")

        # Auto-scroll to bottom
        if self.auto_scroll:
            self.scroll_end(animate=False)

    def clear(self) -> None:
        """Clear all events from the panel."""
        for child in list(self.children):
            child.remove()

    def hide(self) -> None:
        """Hide the events panel."""
        self.add_class("hidden")

    def show(self) -> None:
        """Show the events panel."""
        self.remove_class("hidden")

    def _format_event(self, update: ProgressUpdate) -> Text:
        """Format a progress update event for display.

        Args:
            update: Progress update event

        Returns:
            Formatted text for display
        """
        time_str = update.timestamp.strftime("%H:%M:%S")
        event_type = update.event_type
        details = update.details

        text = Text()
        text.append(f"[{time_str}] ", style="dim")

        if event_type == "started":
            text.append("🚀 Started", style="green")

        elif event_type == "step_start":
            step = details.get("step", "?")
            text.append(f"🧠 Step {step}", style="blue")

        elif event_type == "tool_call":
            tool_name = details.get("tool", "unknown")
            params = details.get("params", {})
            text.append(f"🔧 {tool_name}", style="yellow")
            if params:
                params_str = str(params)
                if len(params_str) > 60:
                    params_str = params_str[:57] + "..."
                text.append(f" {params_str}", style="dim yellow")

        elif event_type == "tool_result":
            tool_name = details.get("tool", "unknown")
            success = details.get("success", True)
            output = str(details.get("output", ""))
            icon = "✅" if success else "❌"
            color = "green" if success else "red"
            text.append(f"{icon} {tool_name}: ", style=color)
            if len(output) > 80:
                output = output[:77] + "..."
            text.append(output, style=color)

        elif event_type == "plan_updated":
            action = details.get("action", "updated")
            text.append(f"📋 Plan {action}", style="magenta")

        elif event_type == "token_usage":
            tokens = details.get("total_tokens", 0)
            text.append(f"🎯 Tokens: {tokens:,}", style="cyan")

        elif event_type == "final_answer":
            text.append("💬 Response ready", style="green")

        elif event_type == "complete":
            text.append("✅ Complete", style="green")

        elif event_type == "error":
            msg = details.get("message", update.message or "Error")
            text.append(f"❌ {msg}", style="red")

        else:
            text.append(f"ℹ️ {update.message or event_type}", style="white")

        return text
