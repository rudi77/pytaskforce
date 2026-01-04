"""Plan panel widget for displaying current task plan."""

from typing import Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container
from textual.reactive import reactive
from textual.widgets import Static


class PlanPanel(Container):
    """Panel displaying the current task execution plan."""

    DEFAULT_CSS = """
    PlanPanel {
        height: auto;
        width: 100%;
        background: $surface;
        border: solid $accent;
        margin: 1 0;
        padding: 1;
    }

    PlanPanel.hidden {
        display: none;
    }

    PlanPanel .plan-title {
        width: 100%;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    PlanPanel .plan-content {
        width: 100%;
        padding: 0 1;
    }
    """

    # Reactive attributes
    visible = reactive(False)

    def __init__(self, **kwargs):
        """Initialize plan panel."""
        super().__init__(**kwargs)
        self.plan_steps: list[dict] = []
        self.plan_text: Optional[str] = None

    def compose(self) -> ComposeResult:
        """Compose plan panel layout."""
        yield Static("🧭 Current Plan", classes="plan-title", id="plan-title")
        yield Static(self._render_plan(), classes="plan-content", id="plan-content")

    def _render_plan(self) -> Text:
        """Render the current plan."""
        if not self.plan_steps and not self.plan_text:
            return Text("No plan available", style="dim")

        result = Text()

        if self.plan_steps:
            # Render structured plan with checkboxes
            for index, step in enumerate(self.plan_steps, start=1):
                description = step.get("description", "").strip()
                status = step.get("status", "PENDING").upper()

                # Determine checkbox and style
                if status in {"DONE", "COMPLETED"}:
                    checkbox = "✓"
                    style = "green"
                elif status in {"IN_PROGRESS", "ACTIVE"}:
                    checkbox = "⏳"
                    style = "yellow"
                else:
                    checkbox = " "
                    style = "white"

                result.append(f"[{checkbox}] ", style=style)
                result.append(f"{index}. {description}\n", style=style)

        elif self.plan_text:
            # Render free-form plan text
            result.append(self.plan_text, style="cyan")

        return result

    def update_plan_steps(self, steps: list[str]) -> None:
        """Update plan with a list of step descriptions.

        Args:
            steps: List of step descriptions
        """
        self.plan_steps = [
            {"description": step, "status": "PENDING"} for step in steps
        ]
        self.plan_text = None
        self.visible = True
        self._refresh_content()

    def update_plan_text(self, text: str) -> None:
        """Update plan with free-form text.

        Args:
            text: Plan text
        """
        self.plan_text = text
        self.plan_steps = []
        self.visible = True
        self._refresh_content()

    def update_step_status(self, step_index: int, status: str) -> None:
        """Update the status of a specific step.

        Args:
            step_index: Step index (1-based)
            status: New status (PENDING, IN_PROGRESS, DONE, etc.)
        """
        if 0 < step_index <= len(self.plan_steps):
            self.plan_steps[step_index - 1]["status"] = status.upper()
            self._refresh_content()

    def clear_plan(self) -> None:
        """Clear the current plan."""
        self.plan_steps = []
        self.plan_text = None
        self.visible = False
        self._refresh_content()

    def _refresh_content(self) -> None:
        """Refresh the plan content display."""
        try:
            content_widget = self.query_one("#plan-content", Static)
            content_widget.update(self._render_plan())
        except Exception:
            # Widget might not be mounted yet
            pass

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
        """Toggle panel visibility.

        Returns:
            New visibility state
        """
        self.visible = not self.visible
        return self.visible
