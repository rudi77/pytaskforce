"""Run command - Execute agent missions."""

import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import typer
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text

from taskforce.api.cli.event_formatter import EventFormatter
from taskforce.api.cli.output_formatter import TaskforceConsole
from taskforce.application.executor import AgentExecutor
from taskforce.core.domain.models import ExecutionResult

app = typer.Typer(help="Execute agent missions")


def _serialize_result_to_json(result: ExecutionResult) -> str:
    """
    Serialize ExecutionResult to JSON string for machine parsing.

    Args:
        result: ExecutionResult to serialize

    Returns:
        JSON string representation
    """
    result_dict = asdict(result)
    return json.dumps(result_dict, indent=None, ensure_ascii=False)


@app.command("mission")
def run_mission(
    ctx: typer.Context,
    mission: str = typer.Argument(..., help="Mission description"),
    profile: str | None = typer.Option(
        None, "--profile", "-p", help="Configuration profile (overrides global --profile)"
    ),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Resume existing session"),
    debug: bool | None = typer.Option(
        None, "--debug", help="Enable debug output (overrides global --debug)"
    ),
    lean: bool = typer.Option(
        False, "--lean", "-l", help="Use Agent (native tool calling, PlannerTool)"
    ),
    planning_strategy: str | None = typer.Option(
        None,
        "--planning-strategy",
        help="Agent planning strategy (native_react or plan_and_execute).",
    ),
    planning_strategy_params: str | None = typer.Option(
        None,
        "--planning-strategy-params",
        help="JSON string for planning strategy params.",
    ),
    stream: bool = typer.Option(
        False,
        "--stream",
        "-S",
        help="Enable real-time streaming output. Shows tool calls, results, and answer as they happen.",
    ),
    output_format: str = typer.Option(
        "text",
        "--output-format",
        "-f",
        help="Output format: 'text' (default, human-readable) or 'json' (machine-parseable)",
    ),
    verbose_events: bool = typer.Option(
        False,
        "--verbose-events",
        "--show-events",
        "--events",
        "-V",
        help="Show agent events on stderr (works with --output-format json)",
    ),
):
    """Execute an agent mission.

    Examples:
        # Execute a simple mission
        taskforce run mission "Analyze data.csv"

        # Use Agent (new simplified architecture)
        taskforce run mission "Plan and execute" --lean

        # Use streaming output for real-time progress
        taskforce run mission "Search and analyze" --lean --stream

        # Resume a previous session
        taskforce run mission "Continue analysis" --session abc-123

        # Debug mode to see agent internals
        taskforce --debug run mission "Debug this task"
    """
    # Validate output_format
    if output_format not in ("text", "json"):
        raise typer.BadParameter(
            f"Invalid output format: {output_format}. Must be 'text' or 'json'"
        )

    # Get global options from context, allow local override
    global_opts = ctx.obj or {}
    profile = profile or global_opts.get("profile", "dev")
    debug = debug if debug is not None else global_opts.get("debug", False)

    # Configure logging level based on debug flag
    import logging

    import structlog

    if debug:
        logging.basicConfig(level=logging.DEBUG, format="%(message)s")
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        )
    else:
        logging.basicConfig(level=logging.WARNING, format="%(message)s")
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
        )

    # Initialize fancy console (only used for text output)
    tf_console = TaskforceConsole(debug=debug) if output_format == "text" else None

    # Suppress UI for JSON output
    if output_format == "text":
        # Print banner
        tf_console.print_banner()

        # Show mission info
        tf_console.print_system_message(f"Mission: {mission}", "system")
        if session_id:
            tf_console.print_system_message(f"Resuming session: {session_id}", "info")
        tf_console.print_system_message(f"Profile: {profile}", "info")
        if planning_strategy and not lean:
            lean = True
            tf_console.print_system_message(
                "Planning strategy override requested; enabling Agent.", "info"
            )
        if lean:
            tf_console.print_system_message("Using Agent (native tool calling)", "info")
        if planning_strategy:
            tf_console.print_system_message(f"Planning strategy: {planning_strategy}", "info")
        if stream:
            tf_console.print_system_message("Streaming mode enabled", "info")
        tf_console.print_divider()

    # Use streaming or standard execution
    try:
        if stream:
            result = asyncio.run(
                _execute_streaming_mission(
                    mission=mission,
                    profile=profile,
                    session_id=session_id,
                    lean=lean,
                    planning_strategy=planning_strategy,
                    planning_strategy_params=planning_strategy_params,
                    console=tf_console.console if output_format == "text" else None,
                    output_format=output_format,
                    verbose_events=verbose_events,
                )
            )
        else:
            result = _execute_standard_mission(
                mission=mission,
                profile=profile,
                session_id=session_id,
                lean=lean,
                debug=debug,
                planning_strategy=planning_strategy,
                planning_strategy_params=planning_strategy_params,
                tf_console=tf_console,
                output_format=output_format,
                verbose_events=verbose_events,
            )

        # Output JSON if requested
        if output_format == "json":
            if result is None:
                # Fallback: create empty result (should not happen in JSON mode)
                result = ExecutionResult(
                    session_id=session_id or "unknown",
                    status="failed",
                    final_message="No result returned from execution",
                    token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                )
            print(_serialize_result_to_json(result))
        elif result is None:
            # Text mode already printed output
            pass

    except Exception as e:
        # Handle errors in JSON format if requested
        if output_format == "json":
            error_result = ExecutionResult(
                session_id=session_id or "unknown",
                status="failed",
                final_message=f"Execution failed: {str(e)}",
                token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )
            print(_serialize_result_to_json(error_result))
            raise typer.Exit(1) from e
        else:
            # Re-raise for normal error handling
            raise


async def _execute_with_verbose_events(
    executor: AgentExecutor,
    mission: str,
    profile: str,
    session_id: str | None,
    planning_strategy: str | None,
    planning_strategy_params: dict | None,
    event_formatter: EventFormatter,
) -> ExecutionResult:
    """Execute mission with verbose event output to stderr.

    Streams events to stderr while collecting result for JSON output.
    """
    execution_history: list[dict[str, Any]] = []
    final_message = ""
    status = "completed"
    resolved_session_id = session_id or "unknown"
    total_token_usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }

    async for update in executor.execute_mission_streaming(
        mission=mission,
        profile=profile,
        session_id=session_id,
        planning_strategy=planning_strategy,
        planning_strategy_params=planning_strategy_params,
    ):
        # Print event to stderr
        event_formatter.print_event(update)

        event_type = update.event_type

        # Extract session_id from "started" event if available
        if event_type == "started" and update.details:
            resolved_session_id = update.details.get("session_id", resolved_session_id)

        # Collect relevant events in execution_history
        if event_type in ("tool_call", "tool_result", "plan_updated", "final_answer", "error"):
            execution_history.append(
                {
                    "type": event_type,
                    **update.details,
                }
            )

        # Update final message and status
        if event_type == "final_answer":
            final_message = update.details.get("content", "")
        elif event_type == "complete":
            if not final_message and update.message:
                final_message = update.message
        elif event_type == "error":
            final_message = update.message
            status = "failed"
        elif event_type == "token_usage":
            usage = update.details
            total_token_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
            total_token_usage["completion_tokens"] += usage.get("completion_tokens", 0)
            total_token_usage["total_tokens"] += usage.get("total_tokens", 0)

    return ExecutionResult(
        session_id=resolved_session_id,
        status=status,
        final_message=final_message or "No answer generated",
        execution_history=execution_history,
        token_usage=total_token_usage,
    )


def _execute_standard_mission(
    mission: str,
    profile: str,
    session_id: str | None,
    lean: bool,
    debug: bool,
    planning_strategy: str | None,
    planning_strategy_params: str | None,
    tf_console: TaskforceConsole | None,
    output_format: str = "text",
    verbose_events: bool = False,
) -> ExecutionResult | None:
    """Execute mission with standard progress bar."""
    executor = AgentExecutor()

    # Suppress progress bar for JSON output
    if output_format == "json":
        strategy_params = _parse_strategy_params(planning_strategy_params)

        # Use streaming internally when verbose_events is enabled
        if verbose_events:
            event_formatter = EventFormatter()
            result = asyncio.run(
                _execute_with_verbose_events(
                    executor=executor,
                    mission=mission,
                    profile=profile,
                    session_id=session_id,
                    planning_strategy=planning_strategy,
                    planning_strategy_params=strategy_params,
                    event_formatter=event_formatter,
                )
            )
        else:
            # Execute without progress UI
            result = asyncio.run(
                executor.execute_mission(
                    mission=mission,
                    profile=profile,
                    session_id=session_id,
                    progress_callback=None,
                    planning_strategy=planning_strategy,
                    planning_strategy_params=strategy_params,
                )
            )
        return result

    # Standard text output with progress bar
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=tf_console.console,
    ) as progress:
        task = progress.add_task("[>] Executing mission...", total=None)

        def progress_callback(update):
            if debug:
                progress.update(task, description=f"[>] {update.message}")
            else:
                progress.update(task, description="[>] Working...")

        # Execute mission with progress tracking
        strategy_params = _parse_strategy_params(planning_strategy_params)
        result = asyncio.run(
            executor.execute_mission(
                mission=mission,
                profile=profile,
                session_id=session_id,
                progress_callback=progress_callback,
                planning_strategy=planning_strategy,
                planning_strategy_params=strategy_params,
            )
        )

    tf_console.print_divider()

    # Display results
    if result.status == "completed":
        tf_console.print_success("Mission completed!")
        tf_console.print_debug(f"Session ID: {result.session_id}")
        tf_console.print_agent_message(result.final_message)
    else:
        tf_console.print_error(f"Mission {result.status}")
        tf_console.print_debug(f"Session ID: {result.session_id}")
        tf_console.print_agent_message(result.final_message)

    # Display token usage statistics
    if result.token_usage and result.token_usage.get("total_tokens", 0) > 0:
        tf_console.print_token_usage(result.token_usage)

    return None  # Text mode already printed output


async def _execute_streaming_mission(
    mission: str,
    profile: str,
    session_id: str | None,
    lean: bool,
    planning_strategy: str | None,
    planning_strategy_params: str | None,
    console: Console | None,
    output_format: str = "text",
    verbose_events: bool = False,
) -> ExecutionResult:
    """Execute mission with streaming Rich Live display."""
    executor = AgentExecutor()

    strategy_params = _parse_strategy_params(planning_strategy_params)

    # For JSON output, collect result without UI
    if output_format == "json":
        # Create event formatter for verbose output to stderr
        event_formatter = EventFormatter() if verbose_events else None

        # Collect all events and build ExecutionResult
        execution_history: list[dict[str, Any]] = []
        final_message = ""
        status = "completed"
        resolved_session_id = session_id or "unknown"
        total_token_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        async for update in executor.execute_mission_streaming(
            mission=mission,
            profile=profile,
            session_id=session_id,
            planning_strategy=planning_strategy,
            planning_strategy_params=strategy_params,
        ):
            # Print event to stderr if verbose_events enabled
            if event_formatter:
                event_formatter.print_event(update)

            event_type = update.event_type

            # Extract session_id from "started" event if available
            if event_type == "started" and update.details:
                resolved_session_id = update.details.get("session_id", resolved_session_id)

            # Collect relevant events in execution_history
            if event_type in ("tool_call", "tool_result", "plan_updated", "final_answer", "error"):
                execution_history.append(
                    {
                        "type": event_type,
                        **update.details,
                    }
                )

            # Update final message and status
            if event_type == "final_answer":
                final_message = update.details.get("content", "")
            elif event_type == "complete":
                # Use complete event message if no final_answer was received
                if not final_message and update.message:
                    final_message = update.message
            elif event_type == "error":
                final_message = update.message
                status = "failed"
            elif event_type == "token_usage":
                usage = update.details
                total_token_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
                total_token_usage["completion_tokens"] += usage.get("completion_tokens", 0)
                total_token_usage["total_tokens"] += usage.get("total_tokens", 0)

        return ExecutionResult(
            session_id=resolved_session_id,
            status=status,
            final_message=final_message or "No answer generated",
            execution_history=execution_history,
            token_usage=total_token_usage,
        )

    # Standard text output with Rich Live display
    # State for live display
    current_step = 0
    current_tool: str | None = None
    tool_results: list[str] = []
    final_answer_tokens: list[str] = []
    status_message = "Starting..."
    plan_steps: list[dict[str, str]] = []
    plan_text: str | None = None
    total_token_usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }

    def format_plan() -> str | None:
        """Format current plan for display."""
        if plan_steps:
            lines = []
            for index, step in enumerate(plan_steps, start=1):
                description = step.get("description", "").strip()
                status = step.get("status", "PENDING").upper()
                checkbox = "x" if status in {"DONE", "COMPLETED"} else " "
                lines.append(f"[{checkbox}] {index}. {description}")
            return "\n".join(lines)
        return plan_text

    def build_display() -> Group:
        """Build Rich display group for current state."""
        elements = []

        # Header
        mission_display = mission[:60] + "..." if len(mission) > 60 else mission
        elements.append(Text(f"🚀 Mission: {mission_display}", style="bold cyan"))

        # Status line with token usage
        status_line = f"📋 Step: {current_step}  |  {status_message}"
        if total_token_usage["total_tokens"] > 0:
            status_line += f"  |  🎯 Tokens: {total_token_usage['total_tokens']}"
        elements.append(Text(status_line, style="dim"))
        elements.append(Text())

        # Current tool (if any)
        if current_tool:
            elements.append(
                Panel(
                    Text(f"🔧 {current_tool}", style="yellow"),
                    title="Current Tool",
                    border_style="yellow",
                )
            )

        # Recent tool results (last 5)
        if tool_results:
            results_text = "\n".join(tool_results[-5:])
            elements.append(
                Panel(
                    Text(results_text),
                    title="Tool Results",
                    border_style="green",
                )
            )

        plan_display = format_plan()
        if plan_display:
            elements.append(
                Panel(
                    Text(plan_display),
                    title="🧭 Plan",
                    border_style="magenta",
                )
            )

        # Streaming final answer
        if final_answer_tokens:
            answer_text = "".join(final_answer_tokens)
            elements.append(
                Panel(
                    Text(answer_text, style="white"),
                    title="💬 Answer",
                    border_style="blue",
                )
            )

        return Group(*elements)

    # Ensure console is available for text mode
    if not console:
        raise ValueError("Console must be provided for text output mode")

    with Live(build_display(), console=console, refresh_per_second=4) as live:
        async for update in executor.execute_mission_streaming(
            mission=mission,
            profile=profile,
            session_id=session_id,
            planning_strategy=planning_strategy,
            planning_strategy_params=strategy_params,
        ):
            event_type = update.event_type
            should_update = False  # Only update display on meaningful changes

            if event_type == "started":
                status_message = "Initializing..."
                should_update = True

            elif event_type == "step_start":
                current_step = update.details.get("step", current_step + 1)
                current_tool = None
                status_message = "Thinking..."
                should_update = True

            elif event_type == "tool_call":
                current_tool = update.details.get("tool", "unknown")
                status_message = f"Calling {current_tool}..."
                should_update = True

            elif event_type == "tool_result":
                tool = update.details.get("tool", "unknown")
                success = "✅" if update.details.get("success") else "❌"
                output = str(update.details.get("output", ""))[:100]
                tool_results.append(f"{success} {tool}: {output}")
                current_tool = None
                status_message = "Processing result..."
                should_update = True

            elif event_type == "llm_token":
                # Tokens are accumulated but we let Rich Live auto-refresh
                # Don't force update on every token to avoid terminal spam
                if not current_tool:
                    token = update.details.get("content", "")
                    if token:
                        final_answer_tokens.append(token)
                        status_message = "Generating response..."
                # No should_update = True - Rich Live refreshes automatically

            elif event_type == "plan_updated":
                action = update.details.get("action", "updated")
                if update.details.get("steps"):
                    plan_steps = [
                        {"description": step, "status": "PENDING"}
                        for step in update.details.get("steps", [])
                    ]
                    plan_text = None
                if update.details.get("plan"):
                    plan_text = update.details.get("plan")
                    plan_steps = []
                if update.details.get("step") and update.details.get("status"):
                    step_index = update.details.get("step") - 1
                    if 0 <= step_index < len(plan_steps):
                        plan_steps[step_index]["status"] = update.details.get("status", "PENDING")
                status_message = f"Plan {action}"
                should_update = True

            elif event_type == "token_usage":
                # Accumulate token usage from LLM calls
                usage = update.details
                total_token_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
                total_token_usage["completion_tokens"] += usage.get("completion_tokens", 0)
                total_token_usage["total_tokens"] += usage.get("total_tokens", 0)
                should_update = True

            elif event_type == "final_answer":
                # If we didn't get streaming tokens, use the full content
                if not final_answer_tokens:
                    content = update.details.get("content", "")
                    if content:
                        final_answer_tokens.append(content)
                status_message = "Complete!"
                should_update = True

            elif event_type == "complete":
                status_message = "Complete!"
                # If no final answer yet, use the message
                if not final_answer_tokens and update.message:
                    final_answer_tokens.append(update.message)
                should_update = True

            elif event_type == "error":
                status_message = f"Error: {update.message}"
                if console:
                    console.print(f"[red]Error: {update.message}[/red]")
                should_update = True

            # Only force update on meaningful state changes
            # For llm_token, Rich Live auto-refreshes at 4fps
            if should_update:
                live.update(build_display())

    # Final summary
    console.print()
    final_text = "".join(final_answer_tokens) if final_answer_tokens else "No answer generated"
    console.print(
        Panel(
            final_text,
            title="✅ Final Answer",
            border_style="green",
        )
    )

    # Display token usage summary
    if total_token_usage["total_tokens"] > 0:
        token_info = (
            f"Prompt Tokens: {total_token_usage['prompt_tokens']:,}  |  "
            f"Completion Tokens: {total_token_usage['completion_tokens']:,}  |  "
            f"Total: {total_token_usage['total_tokens']:,}"
        )
        console.print(
            Panel(
                token_info,
                title="🎯 Token Usage",
                border_style="cyan",
            )
        )

    # Return None for text mode (already printed)
    return None


def _parse_strategy_params(raw_params: str | None) -> dict | None:
    if not raw_params:
        return None
    try:
        data = json.loads(raw_params)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Invalid JSON for --planning-strategy-params: {exc}") from exc
    if not isinstance(data, dict):
        raise typer.BadParameter("--planning-strategy-params must be a JSON object")
    return data


@app.command("command")
def run_command(
    ctx: typer.Context,
    command: str = typer.Argument(..., help="Command name (without /)"),
    arguments: list[str] = typer.Argument(None, help="Arguments for the command"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Configuration profile"),
    debug: bool | None = typer.Option(None, "--debug", help="Enable debug output"),
    stream: bool = typer.Option(False, "--stream", "-S", help="Enable streaming output"),
    output_format: str = typer.Option(
        "text",
        "--output-format",
        "-f",
        help="Output format: 'text' (default, human-readable) or 'json' (machine-parseable)",
    ),
    verbose_events: bool = typer.Option(
        False,
        "--verbose-events",
        "--show-events",
        "--events",
        "-V",
        help="Show agent events on stderr (works with --output-format json)",
    ),
    spec_file: Path | None = typer.Option(
        None,
        "--spec-file",
        "-F",
        help="Path to file containing command arguments (mutually exclusive with positional args)",
    ),
) -> None:
    """
    Execute a custom slash command.

    Custom commands are loaded from:
    - Project: .taskforce/commands/*.md
    - User: ~/.taskforce/commands/*.md

    Examples:
        # Run a prompt command
        taskforce run command review path/to/file.py

        # Run with spec from file
        taskforce run command ralph:init --spec-file spec.md
        taskforce run command ralph:init -F spec.md

        # Run an agent command
        taskforce run command refactor src/module.py

        # With streaming
        taskforce run command analyze data.csv --stream
    """
    from taskforce.application.slash_command_registry import SlashCommandRegistry
    from taskforce.core.interfaces.slash_commands import CommandType

    # Validate output_format
    if output_format not in ("text", "json"):
        raise typer.BadParameter(
            f"Invalid output format: {output_format}. Must be 'text' or 'json'"
        )

    # Validate mutual exclusivity: --spec-file vs positional arguments
    if spec_file is not None and arguments:
        raise typer.BadParameter(
            "Cannot use both --spec-file and positional arguments. Use one or the other."
        )

    # Read spec file content if provided
    spec_content: str | None = None
    if spec_file is not None:
        if not spec_file.exists():
            if output_format == "json":
                error_result = ExecutionResult(
                    session_id="unknown",
                    status="failed",
                    final_message=f"Spec file not found: {spec_file}",
                    token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                )
                print(_serialize_result_to_json(error_result))
                raise typer.Exit(1)
            else:
                console = Console()
                console.print(f"[red]Spec file not found: {spec_file}[/red]")
                raise typer.Exit(1)

        try:
            spec_content = spec_file.read_text(encoding="utf-8")
        except OSError as e:
            if output_format == "json":
                error_result = ExecutionResult(
                    session_id="unknown",
                    status="failed",
                    final_message=f"Failed to read spec file: {e}",
                    token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                )
                print(_serialize_result_to_json(error_result))
                raise typer.Exit(1) from e
            else:
                console = Console()
                console.print(f"[red]Failed to read spec file: {e}[/red]")
                raise typer.Exit(1) from e

    # Get global options from context, allow local override
    global_opts = ctx.obj or {}
    profile = profile or global_opts.get("profile", "dev")
    debug = debug if debug is not None else global_opts.get("debug", False)

    # Configure logging
    import logging

    import structlog

    if debug:
        logging.basicConfig(level=logging.DEBUG, format="%(message)s")
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        )
    else:
        logging.basicConfig(level=logging.WARNING, format="%(message)s")
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
        )

    tf_console = TaskforceConsole(debug=debug) if output_format == "text" else None
    registry = SlashCommandRegistry()

    # Resolve command
    # Use spec file content if provided, otherwise join positional arguments
    if spec_content is not None:
        args_str = spec_content
    else:
        args_str = " ".join(arguments) if arguments else ""
    full_command = f"/{command} {args_str}".strip()
    command_def, args = registry.resolve_command(full_command)

    if not command_def:
        if output_format == "json":
            error_result = ExecutionResult(
                session_id="unknown",
                status="failed",
                final_message=f"Command not found: /{command}",
                token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )
            print(_serialize_result_to_json(error_result))
            raise typer.Exit(1)
        else:
            tf_console.print_error(f"Command not found: /{command}")
            tf_console.print_system_message(
                "Use 'taskforce commands list' to see available commands", "info"
            )
            raise typer.Exit(1)

    # Suppress UI for JSON output
    if output_format == "text":
        # Print banner and info
        tf_console.print_banner()
        tf_console.print_system_message(f"Command: /{command_def.name}", "system")
        tf_console.print_system_message(f"Type: {command_def.command_type.value}", "info")
        tf_console.print_system_message(f"Profile: {profile}", "info")
        if args:
            tf_console.print_system_message(f"Arguments: {args}", "info")
        tf_console.print_divider()

    # Prepare mission/prompt
    mission = registry.prepare_prompt(command_def, args)

    # Execute based on command type
    try:
        if command_def.command_type == CommandType.PROMPT:
            # Use standard execution with prepared prompt
            if stream:
                result = asyncio.run(
                    _execute_streaming_mission(
                        mission=mission,
                        profile=profile,
                        session_id=None,
                        lean=True,
                        planning_strategy=None,
                        planning_strategy_params=None,
                        console=tf_console.console if output_format == "text" else None,
                        output_format=output_format,
                        verbose_events=verbose_events,
                    )
                )
            else:
                result = _execute_standard_mission(
                    mission=mission,
                    profile=profile,
                    session_id=None,
                    lean=True,
                    debug=debug,
                    planning_strategy=None,
                    planning_strategy_params=None,
                    tf_console=tf_console,
                    output_format=output_format,
                    verbose_events=verbose_events,
                )

            # Output JSON if requested
            if output_format == "json" and result is not None:
                print(_serialize_result_to_json(result))

        elif command_def.command_type == CommandType.AGENT:
            # Create specialized agent and execute
            result = asyncio.run(
                _execute_agent_command(
                    command_def=command_def,
                    mission=mission,
                    profile=profile,
                    debug=debug,
                    stream=stream,
                    tf_console=tf_console,
                    output_format=output_format,
                    verbose_events=verbose_events,
                )
            )

            # Output JSON if requested
            if output_format == "json" and result is not None:
                print(_serialize_result_to_json(result))

    except Exception as e:
        # Handle errors in JSON format if requested
        if output_format == "json":
            error_result = ExecutionResult(
                session_id="unknown",
                status="failed",
                final_message=f"Execution failed: {str(e)}",
                token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )
            print(_serialize_result_to_json(error_result))
            raise typer.Exit(1) from e
        else:
            # Re-raise for normal error handling
            raise


async def _execute_agent_command(
    command_def,
    mission: str,
    profile: str,
    debug: bool,
    stream: bool,
    tf_console: TaskforceConsole | None,
    output_format: str = "text",
    verbose_events: bool = False,
) -> ExecutionResult | None:
    """Execute an agent-type command."""
    from taskforce.application.slash_command_registry import SlashCommandRegistry
    from taskforce.application.executor import ProgressUpdate
    from taskforce.core.domain.models import ExecutionResult as DomainExecutionResult

    registry = SlashCommandRegistry()

    try:
        agent = await registry.create_agent_for_command(command_def, profile)

        # Use streaming with verbose events for JSON output
        if output_format == "json" and verbose_events:
            event_formatter = EventFormatter()
            execution_history: list[dict[str, Any]] = []
            final_message = ""
            status = "completed"
            session_id = None
            total_token_usage = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }

            async for event in agent.execute_stream(mission=mission, session_id=session_id):
                # Convert StreamEvent to ProgressUpdate for EventFormatter
                update = ProgressUpdate(
                    timestamp=event.timestamp,
                    event_type=event.event_type,
                    message=event.data.get("message", ""),
                    details=event.data,
                )
                event_formatter.print_event(update)

                # Collect execution history
                if event.event_type in ("tool_call", "tool_result", "plan_updated", "final_answer", "error"):
                    execution_history.append({
                        "type": event.event_type,
                        **event.data,
                    })

                # Update final message and status
                if event.event_type == "final_answer":
                    final_message = event.data.get("content", "")
                elif event.event_type == "error":
                    final_message = event.data.get("message", str(event.data))
                    status = "failed"
                elif event.event_type == "token_usage":
                    usage = event.data
                    total_token_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
                    total_token_usage["completion_tokens"] += usage.get("completion_tokens", 0)
                    total_token_usage["total_tokens"] += usage.get("total_tokens", 0)

            return ExecutionResult(
                session_id=session_id or "unknown",
                status=status,
                final_message=final_message or "No answer generated",
                execution_history=execution_history,
                token_usage=total_token_usage,
            )

        # Execute with the specialized agent (non-streaming)
        result = await agent.execute(mission=mission, session_id=None)

        # Suppress UI for JSON output
        if output_format == "text":
            tf_console.print_divider()
            if result.status == "completed":
                tf_console.print_success("Command completed!")
                tf_console.print_agent_message(result.final_message)
            else:
                tf_console.print_error(f"Command {result.status}")
                tf_console.print_agent_message(result.final_message)

            if result.token_usage:
                tf_console.print_token_usage(result.token_usage)
            return None  # Text mode already printed output
        else:
            return result  # Return result for JSON serialization

    except Exception as e:
        if output_format == "text":
            tf_console.print_error(f"Failed to execute command: {str(e)}")
        raise typer.Exit(1) from e
    finally:
        if "agent" in locals() and hasattr(agent, "close"):
            await agent.close()
