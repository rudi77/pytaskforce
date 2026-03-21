"""Rich output formatting for Taskforce CLI.

Provides beautiful, eye-catching console output with clear visual separation
between agent and user messages.
"""

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

# Custom theme for Taskforce CLI - Cursor Dark Modern style
TASKFORCE_THEME = Theme(
    {
        "agent": "cyan",  # Reduced from bold cyan
        "user": "bright_white",  # Changed from bold green for better contrast
        "system": "dim white",  # Changed from bold blue to subtle
        "error": "red",  # Reduced from bold red
        "warning": "yellow",  # Reduced from bold yellow
        "success": "green",  # Reduced from bold green
        "debug": "dim white",
        "info": "white",
        "thought": "dim magenta",  # Reduced from italic magenta
        "action": "yellow",  # Reduced from bold yellow
        "observation": "dim cyan",  # Reduced from cyan
    }
)


class TaskforceConsole:
    """Enhanced console with Taskforce branding and formatting."""

    def __init__(self, debug: bool = False):
        """Initialize console with optional debug mode.

        Args:
            debug: Enable debug logging output
        """
        self.console = Console(theme=TASKFORCE_THEME)
        self.debug_mode = debug

    def print_banner(self):
        """Print Taskforce startup banner."""
        banner = Text()
        banner.append("\n")
        banner.append("  ╔══════════════════════════════════════════════════════╗\n", style="cyan")
        banner.append("  ║                                                      ║\n", style="cyan")
        banner.append("  ║     ", style="cyan")
        banner.append("TASKFORCE", style="bold bright_white")
        banner.append(" - ReAct Agent Framework       ║\n", style="cyan")
        banner.append("  ║                                                      ║\n", style="cyan")
        banner.append("  ╚══════════════════════════════════════════════════════╝\n", style="cyan")
        self.console.print(banner)
        self.console.print()

    def print_agent_message(self, message: str, thought: str | None = None):
        """Print agent message with distinctive styling.

        Args:
            message: Agent's response message
            thought: Optional agent's reasoning/thought process
        """
        # Show thought process if in debug mode
        if thought and self.debug_mode:
            thought_panel = Panel(
                thought,
                title="[Agent Thought]",
                title_align="left",
                border_style="magenta",
                padding=(0, 1),
            )
            self.console.print(thought_panel)

        # Main agent message
        agent_panel = Panel(
            message,
            title="[Agent]",
            title_align="left",
            border_style="dim cyan",  # More subtle border
            padding=(0, 1),
        )
        self.console.print(agent_panel)
        self.console.print()

    def print_user_message(self, message: str):
        """Print user message with distinctive styling.

        Args:
            message: User's input message
        """
        user_panel = Panel(
            message,
            title="[You]",
            title_align="left",
            border_style="dim bright_white",  # Changed from green to neutral
            padding=(0, 1),
        )
        self.console.print(user_panel)
        self.console.print()

    def print_system_message(self, message: str, style: str = "system"):
        """Print system message.

        Args:
            message: System message
            style: Rich style to apply (from theme)
        """
        self.console.print(f"[{style}][i] {message}[/{style}]")

    def print_error(self, message: str, exception: Exception | None = None):
        """Print error message with optional exception details.

        Args:
            message: Error message
            exception: Optional exception for debug mode
        """
        error_panel = Panel(
            f"[X] {message}",
            title="[Error]",
            title_align="left",
            border_style="red",
            padding=(0, 1),
        )
        self.console.print(error_panel)

        if exception and self.debug_mode:
            import traceback

            self.console.print("[debug]" + traceback.format_exc() + "[/debug]")

    def print_success(self, message: str):
        """Print success message.

        Args:
            message: Success message
        """
        success_panel = Panel(
            f"[OK] {message}",
            title="[Success]",
            title_align="left",
            border_style="green",
            padding=(0, 1),
        )
        self.console.print(success_panel)

    def print_warning(self, message: str):
        """Print warning message.

        Args:
            message: Warning message
        """
        self.console.print(f"[warning][!] {message}[/warning]")

    def print_debug(self, message: str):
        """Print debug message (only if debug mode enabled).

        Args:
            message: Debug message
        """
        if self.debug_mode:
            self.console.print(f"[debug][DEBUG] {message}[/debug]")

    def print_action(self, action_type: str, details: str):
        """Print agent action with details.

        Args:
            action_type: Type of action (tool_call, ask_user, etc.)
            details: Action details
        """
        if self.debug_mode:
            action_text = f"[action][Action][/action] {action_type}\n[info]{details}[/info]"
            action_panel = Panel(
                action_text,
                title="[Agent Action]",
                title_align="left",
                border_style="yellow",
                padding=(0, 1),
            )
            self.console.print(action_panel)

    def print_observation(self, observation: str):
        """Print observation result.

        Args:
            observation: Observation text
        """
        if self.debug_mode:
            obs_panel = Panel(
                observation,
                title="[Observation]",
                title_align="left",
                border_style="cyan",
                padding=(0, 1),
            )
            self.console.print(obs_panel)

    def print_session_info(
        self,
        session_id: str,
        profile: str,
        user_context: dict | None = None,
    ):
        """Print session information.

        Args:
            session_id: Session ID
            profile: Configuration profile
            user_context: Optional RAG user context
        """
        info_lines = [
            f"[info]Session ID:[/info] [debug]{session_id}[/debug]",
            f"[info]Profile:[/info] [debug]{profile}[/debug]",
        ]

        if user_context:
            info_lines.append("[info]RAG Context:[/info]")
            for key, value in user_context.items():
                info_lines.append(f"  [debug]{key}:[/debug] {value}")

        info_text = "\n".join(info_lines)
        info_panel = Panel(
            info_text,
            title="[Session Info]",
            title_align="left",
            border_style="dim",  # Changed from blue to neutral
            padding=(0, 1),
        )
        self.console.print(info_panel)
        self.console.print()

    def print_divider(self, text: str | None = None):
        """Print a visual divider.

        Args:
            text: Optional text to display in divider
        """
        if text:
            self.console.print(
                f"\n[dim]{'=' * 20}[/dim] [bright_white]{text}[/bright_white] [dim]{'=' * 20}[/dim]\n"
            )
        else:
            self.console.print(f"[dim]{'-' * 60}[/dim]")

    def prompt(self, message: str = "You") -> str:
        """Prompt user for input with styled prompt.

        Args:
            message: Prompt message

        Returns:
            User input string
        """
        from rich.prompt import Prompt

        return Prompt.ask(f"[user]> {message}[/user]")

    def print_token_usage(self, token_usage: dict[str, int]):
        """Print token usage statistics.

        Args:
            token_usage: Dict with prompt_tokens, completion_tokens, total_tokens
        """
        prompt_tokens = token_usage.get("prompt_tokens", 0)
        completion_tokens = token_usage.get("completion_tokens", 0)
        total_tokens = token_usage.get("total_tokens", 0)

        token_info = (
            f"[info]Prompt Tokens:[/info] [cyan]{prompt_tokens:,}[/cyan]  |  "
            f"[info]Completion Tokens:[/info] [cyan]{completion_tokens:,}[/cyan]  |  "
            f"[info]Total:[/info] [cyan]{total_tokens:,}[/cyan]"
        )

        token_panel = Panel(
            token_info,
            title="[🎯 Token Usage]",
            title_align="left",
            border_style="dim cyan",  # More subtle border
            padding=(0, 1),
        )
        self.console.print(token_panel)

    def print_token_analytics(self, analytics: dict[str, Any] | Any) -> None:
        """Print detailed token analytics breakdown.

        Args:
            analytics: ExecutionTokenSummary dict or object with to_dict().
        """
        if analytics is None:
            return

        data: dict[str, Any] = analytics.to_dict() if hasattr(analytics, "to_dict") else analytics

        total = data.get("total_tokens", 0)
        if total == 0:
            return

        # Phase breakdown table
        phase_breakdown = data.get("phase_breakdown", {})
        if phase_breakdown:
            table = Table(
                title="Token Analytics - Phase Breakdown",
                border_style="dim cyan",
                show_header=True,
                header_style="bold cyan",
                padding=(0, 1),
            )
            table.add_column("Phase", style="white")
            table.add_column("Tokens", justify="right", style="cyan")
            table.add_column("%", justify="right", style="yellow")
            table.add_column("Calls", justify="right", style="dim")
            table.add_column("Avg/Call", justify="right", style="dim")

            for phase_name, phase_data in sorted(
                phase_breakdown.items(),
                key=lambda x: x[1].get("total_tokens", 0) if isinstance(x[1], dict) else 0,
                reverse=True,
            ):
                if isinstance(phase_data, dict):
                    phase_tokens = phase_data.get("total_tokens", 0)
                    pct = (phase_tokens / total * 100) if total > 0 else 0.0
                    calls = phase_data.get("call_count", 0)
                    avg = phase_data.get("avg_tokens_per_call", 0.0)
                    table.add_row(
                        phase_name,
                        f"{phase_tokens:,}",
                        f"{pct:.1f}%",
                        str(calls),
                        f"{avg:,.0f}",
                    )

            self.console.print(table)

        # Efficiency metrics
        ratio = data.get("prompt_to_completion_ratio", 0.0)
        tokens_per_step = data.get("tokens_per_step_avg", 0.0)
        compressions = data.get("compression_events", 0)
        total_steps = data.get("total_steps", 0)
        total_calls = data.get("total_llm_calls", 0)
        most_expensive_step = data.get("most_expensive_step")
        most_expensive_tool = data.get("most_expensive_tool", "")

        lines = []
        lines.append(
            f"[info]Steps:[/info] [cyan]{total_steps}[/cyan]  |  "
            f"[info]LLM Calls:[/info] [cyan]{total_calls}[/cyan]  |  "
            f"[info]Avg Tokens/Step:[/info] [cyan]{tokens_per_step:,.0f}[/cyan]"
        )

        ratio_style = "green" if ratio < 5.0 else "yellow" if ratio < 10.0 else "red"
        ratio_label = (
            "efficient" if ratio < 5.0 else "context-heavy" if ratio < 10.0 else "wasteful"
        )
        lines.append(
            f"[info]Prompt/Completion Ratio:[/info] [{ratio_style}]{ratio:.1f}x[/{ratio_style}]"
            f" ({ratio_label})"
        )

        if compressions > 0:
            lines.append(f"[info]Compressions Triggered:[/info] [yellow]{compressions}[/yellow]")

        if most_expensive_step is not None:
            lines.append(f"[info]Most Expensive Step:[/info] [cyan]#{most_expensive_step}[/cyan]")

        if most_expensive_tool:
            lines.append(f"[info]Highest Context Tool:[/info] [cyan]{most_expensive_tool}[/cyan]")

        # Tool impact summary (top 5)
        tool_impact = data.get("tool_impact", {})
        if tool_impact:
            sorted_tools = sorted(
                tool_impact.items(),
                key=lambda x: (
                    x[1].get("estimated_tokens_added", 0) if isinstance(x[1], dict) else 0
                ),
                reverse=True,
            )[:5]
            tool_lines = []
            for tool_name, tool_data in sorted_tools:
                if isinstance(tool_data, dict):
                    est_tokens = tool_data.get("estimated_tokens_added", 0)
                    calls = tool_data.get("call_count", 0)
                    avg_chars = tool_data.get("avg_result_chars", 0.0)
                    tool_lines.append(
                        f"  {tool_name}: ~{est_tokens:,} tokens "
                        f"({calls} calls, avg {avg_chars:,.0f} chars)"
                    )
            if tool_lines:
                lines.append("[info]Top Tools by Context Impact:[/info]")
                lines.extend(tool_lines)

        analytics_panel = Panel(
            "\n".join(lines),
            title="[📊 Token Analytics]",
            title_align="left",
            border_style="dim cyan",
            padding=(0, 1),
        )
        self.console.print(analytics_panel)
