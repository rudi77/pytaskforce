"""Streaming Mission Renderer - Extracted from run.py.

Encapsulates Rich Live display state and rendering for streaming
mission execution. Separates UI rendering from business logic.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from taskforce.application.executor import ProgressUpdate


class StreamingMissionRenderer:
    """Rich Live display renderer for streaming mission execution.

    Encapsulates all display state (step counter, tool results, tokens,
    plan) and provides methods for handling events and building the
    Rich display group.
    """

    def __init__(self, console: Console, mission: str) -> None:
        self._console = console
        self._mission = mission
        # Display state
        self.current_step: int = 0
        self.current_tool: str | None = None
        self.tool_results: list[str] = []
        self.final_answer_tokens: list[str] = []
        self.status_message: str = "Starting..."
        self.plan_steps: list[dict[str, str]] = []
        self.plan_text: str | None = None
        self.total_token_usage: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    async def render(
        self, event_stream: AsyncIterator[ProgressUpdate]
    ) -> None:
        """Run the live display loop consuming the event stream."""
        with Live(
            self.build_display(),
            console=self._console,
            refresh_per_second=4,
        ) as live:
            async for update in event_stream:
                should_update = self.handle_event(update)
                if should_update:
                    live.update(self.build_display())

        self.display_summary()

    def handle_event(self, update: ProgressUpdate) -> bool:
        """Process a single event and update internal state.

        Returns True if the display should be refreshed.
        """
        event_type = update.event_type
        if event_type == "started":
            self.status_message = "Initializing..."
            return True
        if event_type == "step_start":
            return self._handle_step_start(update)
        if event_type == "tool_call":
            return self._handle_tool_call(update)
        if event_type == "tool_result":
            return self._handle_tool_result(update)
        if event_type == "llm_token":
            return self._handle_llm_token(update)
        if event_type == "plan_updated":
            return self._handle_plan_updated(update)
        if event_type == "token_usage":
            return self._handle_token_usage(update)
        if event_type == "final_answer":
            return self._handle_final_answer(update)
        if event_type == "complete":
            return self._handle_complete(update)
        if event_type == "error":
            self.status_message = f"Error: {update.message}"
            self._console.print(f"[red]Error: {update.message}[/red]")
            return True
        return False

    def _handle_step_start(self, update: ProgressUpdate) -> bool:
        self.current_step = update.details.get(
            "step", self.current_step + 1
        )
        self.current_tool = None
        self.status_message = "Thinking..."
        return True

    def _handle_tool_call(self, update: ProgressUpdate) -> bool:
        self.current_tool = update.details.get("tool", "unknown")
        self.status_message = f"Calling {self.current_tool}..."
        return True

    def _handle_tool_result(self, update: ProgressUpdate) -> bool:
        tool = update.details.get("tool", "unknown")
        icon = "\u2705" if update.details.get("success") else "\u274c"
        output = str(update.details.get("output", ""))[:100]
        self.tool_results.append(f"{icon} {tool}: {output}")
        self.current_tool = None
        self.status_message = "Processing result..."
        return True

    def _handle_llm_token(self, update: ProgressUpdate) -> bool:
        if not self.current_tool:
            token = update.details.get("content", "")
            if token:
                self.final_answer_tokens.append(token)
                self.status_message = "Generating response..."
        return False  # Rich Live auto-refreshes at 4fps

    def _handle_plan_updated(self, update: ProgressUpdate) -> bool:
        action = update.details.get("action", "updated")
        if update.details.get("steps"):
            self.plan_steps = [
                {"description": step, "status": "PENDING"}
                for step in update.details.get("steps", [])
            ]
            self.plan_text = None
        if update.details.get("plan"):
            self.plan_text = update.details.get("plan")
            self.plan_steps = []
        if update.details.get("step") and update.details.get("status"):
            step_index = update.details.get("step") - 1
            if 0 <= step_index < len(self.plan_steps):
                self.plan_steps[step_index]["status"] = update.details.get(
                    "status", "PENDING"
                )
        self.status_message = f"Plan {action}"
        return True

    def _handle_token_usage(self, update: ProgressUpdate) -> bool:
        usage = update.details
        self.total_token_usage["prompt_tokens"] += usage.get(
            "prompt_tokens", 0
        )
        self.total_token_usage["completion_tokens"] += usage.get(
            "completion_tokens", 0
        )
        self.total_token_usage["total_tokens"] += usage.get(
            "total_tokens", 0
        )
        return True

    def _handle_final_answer(self, update: ProgressUpdate) -> bool:
        if not self.final_answer_tokens:
            content = update.details.get("content", "")
            if content:
                self.final_answer_tokens.append(content)
        self.status_message = "Complete!"
        return True

    def _handle_complete(self, update: ProgressUpdate) -> bool:
        self.status_message = "Complete!"
        if not self.final_answer_tokens and update.message:
            self.final_answer_tokens.append(update.message)
        return True

    def format_plan(self) -> str | None:
        """Format current plan for display."""
        if self.plan_steps:
            lines = []
            for index, step in enumerate(self.plan_steps, start=1):
                description = step.get("description", "").strip()
                status = step.get("status", "PENDING").upper()
                checkbox = "x" if status in {"DONE", "COMPLETED"} else " "
                lines.append(f"[{checkbox}] {index}. {description}")
            return "\n".join(lines)
        return self.plan_text

    def build_display(self) -> Group:
        """Build Rich display group for current state."""
        elements: list[Any] = []

        mission_display = (
            self._mission[:60] + "..."
            if len(self._mission) > 60
            else self._mission
        )
        elements.append(
            Text(f"\U0001f680 Mission: {mission_display}", style="bold cyan")
        )

        status_line = (
            f"\U0001f4cb Step: {self.current_step}  |  {self.status_message}"
        )
        if self.total_token_usage["total_tokens"] > 0:
            status_line += (
                f"  |  \U0001f3af Tokens: "
                f"{self.total_token_usage['total_tokens']}"
            )
        elements.append(Text(status_line, style="dim"))
        elements.append(Text())

        if self.current_tool:
            elements.append(
                Panel(
                    Text(f"\U0001f527 {self.current_tool}", style="yellow"),
                    title="Current Tool",
                    border_style="yellow",
                )
            )

        if self.tool_results:
            results_text = "\n".join(self.tool_results[-5:])
            elements.append(
                Panel(
                    Text(results_text),
                    title="Tool Results",
                    border_style="green",
                )
            )

        plan_display = self.format_plan()
        if plan_display:
            elements.append(
                Panel(
                    Text(plan_display),
                    title="\U0001f9ed Plan",
                    border_style="magenta",
                )
            )

        if self.final_answer_tokens:
            answer_text = "".join(self.final_answer_tokens)
            elements.append(
                Panel(
                    Text(answer_text, style="white"),
                    title="\U0001f4ac Answer",
                    border_style="blue",
                )
            )

        return Group(*elements)

    def display_summary(self) -> None:
        """Display final summary after the live display ends."""
        self._console.print()
        final_text = (
            "".join(self.final_answer_tokens)
            if self.final_answer_tokens
            else "No answer generated"
        )
        self._console.print(
            Panel(
                final_text,
                title="\u2705 Final Answer",
                border_style="green",
            )
        )

        from taskforce.api.cli.output_formatter import TaskforceConsole

        tf_console = TaskforceConsole(self._console)

        if self.total_token_usage["total_tokens"] > 0:
            token_info = (
                f"Prompt Tokens: {self.total_token_usage['prompt_tokens']:,}"
                f"  |  Completion Tokens: "
                f"{self.total_token_usage['completion_tokens']:,}"
                f"  |  Total: {self.total_token_usage['total_tokens']:,}"
            )
            self._console.print(
                Panel(
                    token_info,
                    title="\U0001f3af Token Usage",
                    border_style="cyan",
                )
            )
