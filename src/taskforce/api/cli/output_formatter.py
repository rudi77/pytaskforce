"""Rich output formatting for Taskforce CLI.

Provides beautiful, eye-catching console output with clear visual separation
between agent and user messages.
"""


from rich.console import Console
from rich.panel import Panel
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

    def print_banner(self) -> None:
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

    def print_agent_message(self, message: str, thought: str | None = None) -> None:
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

    def print_user_message(self, message: str) -> None:
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

    def print_system_message(self, message: str, style: str = "system") -> None:
        """Print system message.

        Args:
            message: System message
            style: Rich style to apply (from theme)
        """
        self.console.print(f"[{style}][i] {message}[/{style}]")

    def print_error(self, message: str, exception: Exception | None = None) -> None:
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

    def print_success(self, message: str) -> None:
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

    def print_warning(self, message: str) -> None:
        """Print warning message.

        Args:
            message: Warning message
        """
        self.console.print(f"[warning][!] {message}[/warning]")

    def print_debug(self, message: str) -> None:
        """Print debug message (only if debug mode enabled).

        Args:
            message: Debug message
        """
        if self.debug_mode:
            self.console.print(f"[debug][DEBUG] {message}[/debug]")

    def print_action(self, action_type: str, details: str) -> None:
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

    def print_observation(self, observation: str) -> None:
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
    ) -> None:
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

    def print_divider(self, text: str | None = None) -> None:
        """Print a visual divider.

        Args:
            text: Optional text to display in divider
        """
        if text:
            self.console.print(f"\n[dim]{'=' * 20}[/dim] [bright_white]{text}[/bright_white] [dim]{'=' * 20}[/dim]\n")
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

    def print_token_usage(self, token_usage: dict[str, int]) -> None:
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

