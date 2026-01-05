"""Events panel widget for displaying execution progress events."""

import json
from typing import Any

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
            step = details.get("step")
            if step is not None:
                text.append(f" (step={step})", style="dim green")

        elif event_type == "step_start":
            step = details.get("step", "?")
            text.append(f"🧠 Step {step}", style="blue")
            if update.message:
                text.append(f" — {update.message}", style="dim blue")

        elif event_type == "tool_call":
            tool_name = details.get("tool", "unknown")
            status = details.get("status")
            args = (
                details.get("args")
                or details.get("params")
                or {}
            )

            text.append(f"🔧 {tool_name}", style="yellow")
            if status:
                text.append(f" [{status}]", style="dim yellow")

            args_str = self._compact_json(args, max_len=160)
            if args_str:
                text.append(f" args={args_str}", style="dim yellow")
            else:
                text.append(" args={}", style="dim yellow")

        elif event_type == "tool_result":
            tool_name = details.get("tool", "unknown")
            success = details.get("success", True)
            output = details.get("output", "")
            args = details.get("args") or {}
            icon = "✅" if success else "❌"
            color = "green" if success else "red"
            text.append(f"{icon} {tool_name}: ", style=color)

            output_str = self._single_line(str(output))
            if not output_str:
                output_str = "<empty>"
            output_str = self._truncate(output_str, 160)
            text.append(output_str, style=color)

            args_str = self._compact_json(args, max_len=140)
            if args_str:
                text.append(f"  args={args_str}", style=f"dim {color}")

        elif event_type == "plan_updated":
            action = details.get("action", "updated")
            text.append(f"📋 Plan {action}", style="magenta")
            step = details.get("step")
            status = details.get("status")
            if step is not None and status:
                text.append(f" (step={step}, status={status})", style="dim magenta")

        elif event_type == "token_usage":
            tokens = details.get("total_tokens", 0)
            text.append(f"🎯 Tokens: {tokens:,}", style="cyan")

        elif event_type == "final_answer":
            text.append("💬 Response ready", style="green")

        elif event_type == "complete":
            text.append("✅ Complete", style="green")

        elif event_type == "error":
            msg = details.get("message", update.message or "Error")
            step = details.get("step")
            text.append(f"❌ {msg}", style="red")
            if step is not None:
                text.append(f" (step={step})", style="dim red")

        else:
            text.append(f"ℹ️ {update.message or event_type}", style="white")

        return text

    @staticmethod
    def _truncate(value: str, max_len: int) -> str:
        if len(value) <= max_len:
            return value
        return value[: max_len - 3] + "..."

    @staticmethod
    def _single_line(value: str) -> str:
        return " ".join(value.split())

    @staticmethod
    def _compact_json(data: Any, max_len: int) -> str:
        try:
            encoded = json.dumps(
                data,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
        except TypeError:
            encoded = str(data)

        encoded = " ".join(str(encoded).split())
        if encoded == "null":
            return ""
        if len(encoded) > max_len:
            return encoded[: max_len - 3] + "..."
        return encoded
