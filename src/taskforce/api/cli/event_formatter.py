"""Event formatter for CLI output.

Formats and outputs agent events to console, typically stderr.
Used for verbose event output in non-interactive modes like Ralph Loop.
"""

import json
import sys
from typing import Any, TextIO

from rich.console import Console
from rich.text import Text

from taskforce.application.executor import ProgressUpdate


class EventFormatter:
    """Formats and outputs agent events to console.

    Provides event formatting similar to the chat UI EventsPanel,
    but outputs to a file stream (typically stderr) for CLI use.
    """

    def __init__(self, file: TextIO = sys.stderr, force_terminal: bool = True):
        """Initialize event formatter.

        Args:
            file: Output stream (default: stderr)
            force_terminal: Force terminal mode for colors/styles
        """
        self.console = Console(file=file, force_terminal=force_terminal)

    def format_event(self, update: ProgressUpdate) -> Text:
        """Format a progress update event for display.

        Args:
            update: Progress update event

        Returns:
            Formatted Rich Text object
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
            args = details.get("args") or details.get("params") or {}

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

    def print_event(self, update: ProgressUpdate) -> None:
        """Format and print event to console.

        Skips llm_token events to avoid flooding output.

        Args:
            update: Progress update event
        """
        if update.event_type == "llm_token":
            return

        text = self.format_event(update)
        self.console.print(text)
        # Ensure output is flushed immediately for scripts capturing stderr
        self.console.file.flush()

    @staticmethod
    def _truncate(value: str, max_len: int) -> str:
        """Truncate string to max length with ellipsis."""
        if len(value) <= max_len:
            return value
        return value[: max_len - 3] + "..."

    @staticmethod
    def _single_line(value: str) -> str:
        """Convert multiline string to single line."""
        return " ".join(value.split())

    @staticmethod
    def _compact_json(data: Any, max_len: int) -> str:
        """Convert data to compact JSON string, truncated if needed."""
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
