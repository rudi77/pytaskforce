"""Run command - Execute agent missions."""

import asyncio
import json
from typing import Any

import typer
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text

from taskforce.api.cli.output_formatter import TaskforceConsole
from taskforce.application.executor import AgentExecutor

app = typer.Typer(help="Execute agent missions")


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
        help="Agent planning strategy (native_react, plan_and_execute, plan_and_react, spar).",
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
    plugin: str | None = typer.Option(
        None,
        "--plugin",
        "-P",
        help="Path to external plugin directory (e.g., examples/accounting_agent)",
    ),
    auto_epic: bool | None = typer.Option(
        None,
        "--auto-epic/--no-auto-epic",
        help=(
            "Auto-detect complex missions and escalate to Epic Orchestration "
            "(planner/worker/judge). Default: from profile config."
        ),
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

        # Use plugin with custom tools
        taskforce run mission "Prüfe diese Rechnung" --plugin examples/accounting_agent

        # Debug mode to see agent internals
        taskforce --debug run mission "Debug this task"
    """
    # Get global options from context, allow local override
    global_opts = ctx.obj or {}
    profile = profile or global_opts.get("profile", "universal")
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

    # Initialize fancy console
    tf_console = TaskforceConsole(debug=debug)

    # Print banner
    tf_console.print_banner()

    # Show mission info
    tf_console.print_system_message("Starting mission", "system")
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
    if plugin:
        tf_console.print_system_message(f"Plugin: {plugin}", "info")
    if auto_epic is True:
        tf_console.print_system_message("Auto-epic detection: enabled", "info")
    elif auto_epic is False:
        tf_console.print_system_message("Auto-epic detection: disabled", "info")
    tf_console.print_divider()

    # Use streaming or standard execution
    if stream:
        asyncio.run(
            _execute_streaming_mission(
                mission=mission,
                profile=profile,
                session_id=session_id,
                lean=lean,
                planning_strategy=planning_strategy,
                planning_strategy_params=planning_strategy_params,
                console=tf_console.console,
                plugin=plugin,
                auto_epic=auto_epic,
            )
        )
    else:
        _execute_standard_mission(
            mission=mission,
            profile=profile,
            session_id=session_id,
            lean=lean,
            debug=debug,
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
            tf_console=tf_console,
            plugin=plugin,
            auto_epic=auto_epic,
        )


def _execute_standard_mission(
    mission: str,
    profile: str,
    session_id: str | None,
    lean: bool,
    debug: bool,
    planning_strategy: str | None,
    planning_strategy_params: str | None,
    tf_console: TaskforceConsole,
    plugin: str | None = None,
    auto_epic: bool | None = None,
) -> None:
    """Execute mission with standard progress bar."""
    executor = AgentExecutor()

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
                plugin_path=plugin,
                auto_epic=auto_epic,
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
    token_usage = (
        result.token_usage.to_dict()
        if hasattr(result.token_usage, "to_dict")
        else result.token_usage
    )
    if token_usage and token_usage.get("total_tokens", 0) > 0:
        tf_console.print_token_usage(token_usage)


async def _execute_streaming_mission(
    mission: str,
    profile: str,
    session_id: str | None,
    lean: bool,
    console: Console,
    planning_strategy: str | None = None,
    planning_strategy_params: str | None = None,
    plugin: str | None = None,
    auto_epic: bool | None = None,
) -> None:
    """Execute mission with streaming Rich Live display."""
    executor = AgentExecutor()

    strategy_params = _parse_strategy_params(planning_strategy_params)

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

    with Live(build_display(), console=console, refresh_per_second=4) as live:
        async for update in executor.execute_mission_streaming(
            mission=mission,
            profile=profile,
            session_id=session_id,
            planning_strategy=planning_strategy,
            planning_strategy_params=strategy_params,
            plugin_path=plugin,
            auto_epic=auto_epic,
        ):
            event_type = update.event_type
            should_update = False  # Only update display on meaningful changes

            if event_type == "epic_escalation":
                workers = update.details.get("worker_count", "?")
                est_tasks = update.details.get("estimated_tasks", "?")
                reasoning = update.details.get("reasoning", "")
                console.print(
                    Panel(
                        (
                            f"[bold yellow]Mission classified as complex[/]\n"
                            f"Escalating to Epic Orchestration "
                            f"(Planner / Worker / Judge)\n\n"
                            f"Reasoning: {reasoning}\n"
                            f"Workers: {workers}  |  "
                            f"Estimated tasks: {est_tasks}"
                        ),
                        title="Epic Orchestration",
                        border_style="yellow",
                    )
                )
                status_message = "Running Epic Orchestration..."
                should_update = True

            elif event_type == "started":
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


@app.command("skill")
def run_skill(
    ctx: typer.Context,
    skill_name: str = typer.Argument(..., help="Skill name (without /)"),
    arguments: list[str] = typer.Argument(None, help="Arguments for the skill"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Configuration profile"),
    debug: bool | None = typer.Option(None, "--debug", help="Enable debug output"),
    stream: bool = typer.Option(False, "--stream", "-S", help="Enable streaming output"),
) -> None:
    """
    Execute a skill directly.

    Skills are loaded from:
    - Project: .taskforce/skills/<name>/SKILL.md
    - User: ~/.taskforce/skills/<name>/SKILL.md

    Examples:
        # Run a prompt skill
        taskforce run skill code-review path/to/file.py

        # Run an agent skill
        taskforce run skill agents:refactor src/module.py

        # With streaming
        taskforce run skill analyze data.csv --stream
    """
    from taskforce.application.skill_service import get_skill_service
    from taskforce.core.domain.enums import SkillType

    # Get global options from context, allow local override
    global_opts = ctx.obj or {}
    profile = profile or global_opts.get("profile", "universal")
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

    tf_console = TaskforceConsole(debug=debug)
    skill_service = get_skill_service()

    # Resolve skill via /name args format
    args_str = " ".join(arguments) if arguments else ""
    full_command = f"/{skill_name} {args_str}".strip()
    skill, args = skill_service.resolve_slash_command(full_command)

    if not skill:
        tf_console.print_error(f"Skill not found: /{skill_name}")
        tf_console.print_system_message(
            "Use 'taskforce skills list' to see available skills", "info"
        )
        raise typer.Exit(1)

    # Print banner and info
    tf_console.print_banner()
    tf_console.print_system_message(f"Skill: /{skill.effective_slash_name}", "system")
    tf_console.print_system_message(f"Type: {skill.skill_type.value}", "info")
    tf_console.print_system_message(f"Profile: {profile}", "info")
    if args:
        tf_console.print_system_message(f"Arguments: {args}", "info")
    tf_console.print_divider()

    # Execute based on skill type
    if skill.skill_type == SkillType.PROMPT:
        mission = skill_service.prepare_skill_prompt(skill, args)
        if stream:
            asyncio.run(
                _execute_streaming_mission(
                    mission=mission,
                    profile=profile,
                    session_id=None,
                    lean=True,
                    planning_strategy=None,
                    planning_strategy_params=None,
                    console=tf_console.console,
                )
            )
        else:
            _execute_standard_mission(
                mission=mission,
                profile=profile,
                session_id=None,
                lean=True,
                debug=debug,
                planning_strategy=None,
                planning_strategy_params=None,
                tf_console=tf_console,
            )
    elif skill.skill_type == SkillType.AGENT:
        asyncio.run(
            _execute_skill_agent(
                skill=skill,
                args=args,
                profile=profile,
                debug=debug,
                stream=stream,
                tf_console=tf_console,
            )
        )
    else:
        tf_console.print_system_message(
            f"Context skill '{skill.name}' activated (no direct execution)", "info"
        )


async def _execute_skill_agent(
    skill: Any,
    args: str,
    profile: str,
    debug: bool,
    stream: bool,
    tf_console: TaskforceConsole,
) -> None:
    """Execute an AGENT-type skill."""
    from taskforce.application.factory import AgentFactory

    agent_config = skill.agent_config or {}
    skill_profile = agent_config.get("profile") or profile
    factory = AgentFactory()
    agent = None

    try:
        agent = await factory.create_agent(
            config=skill_profile,
        )
        mission = skill.substitute_arguments(args) if args else skill.instructions
        result = await agent.execute(mission=mission, session_id=None)

        tf_console.print_divider()
        if result.status == "completed":
            tf_console.print_success("Skill completed!")
            tf_console.print_agent_message(result.final_message)
        else:
            tf_console.print_error(f"Skill {result.status}")
            tf_console.print_agent_message(result.final_message)

        if result.token_usage:
            tf_console.print_token_usage(result.token_usage)
    except Exception as e:
        tf_console.print_error(f"Failed to execute skill: {str(e)}")
        raise typer.Exit(1) from e
    finally:
        if agent and hasattr(agent, "close"):
            await agent.close()
