"""Run command - Execute agent missions."""

import asyncio
import json
from typing import Any

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

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
    profile = profile or global_opts.get("profile", "butler")
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

    # Display token usage
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
) -> None:
    """Execute mission with streaming Rich Live display."""
    from taskforce.api.cli.streaming_renderer import StreamingMissionRenderer

    executor = AgentExecutor()
    strategy_params = _parse_strategy_params(planning_strategy_params)

    renderer = StreamingMissionRenderer(console, mission)
    event_stream = executor.execute_mission_streaming(
        mission=mission,
        profile=profile,
        session_id=session_id,
        planning_strategy=planning_strategy,
        planning_strategy_params=strategy_params,
        plugin_path=plugin,
    )
    await renderer.render(event_stream)


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
    profile = profile or global_opts.get("profile", "butler")
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
