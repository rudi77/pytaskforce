"""Butler CLI commands for managing the event-driven agent daemon."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Butler agent daemon management")
console = Console()


@app.command("start")
def butler_start(
    ctx: typer.Context,
    profile: str = typer.Option("butler", "--profile", "-p", help="Butler profile"),
    detach: bool = typer.Option(False, "--detach", "-d", help="Run in background"),
) -> None:
    """Start the butler daemon."""
    import logging

    import structlog

    global_opts = ctx.obj or {}
    debug = global_opts.get("debug", False)

    if debug:
        logging.basicConfig(level=logging.DEBUG, format="%(message)s")
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        )
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        )

    console.print(f"[bold green]Starting butler daemon[/bold green] (profile: {profile})")
    asyncio.run(_run_butler(profile))


async def _run_butler(profile: str) -> None:
    """Initialize and run the butler daemon."""
    from taskforce.api.butler_daemon import ButlerDaemon

    daemon = ButlerDaemon(profile=profile)
    try:
        await daemon.start()
        console.print("[bold green]Butler daemon is running.[/bold green] Press Ctrl+C to stop.")
        # Keep running until interrupted
        while daemon.is_running:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down butler daemon...[/yellow]")
    finally:
        await daemon.stop()
        console.print("[green]Butler daemon stopped.[/green]")


@app.command("status")
def butler_status(ctx: typer.Context) -> None:
    """Show butler daemon status."""
    asyncio.run(_show_status())


async def _show_status() -> None:
    """Display the butler service status."""
    import json
    from pathlib import Path

    # Try to read status from a status file
    status_path = Path(".taskforce/butler/status.json")
    if not status_path.exists():
        console.print("[yellow]Butler daemon is not running (no status file found).[/yellow]")
        return

    data = json.loads(status_path.read_text())
    table = Table(title="Butler Status")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details", style="white")

    table.add_row("Daemon", "Running" if data.get("running") else "Stopped", "")
    table.add_row(
        "Gateway", "Configured" if data.get("gateway_configured") else "Not configured", ""
    )
    table.add_row(
        "Executor", "Configured" if data.get("executor_configured") else "Not configured", ""
    )

    scheduler = data.get("scheduler", {})
    table.add_row(
        "Scheduler",
        "Running" if scheduler.get("running") else "Stopped",
        f"{scheduler.get('jobs', 0)} jobs",
    )

    table.add_row("Rules", "", f"{data.get('rules', 0)} active")
    table.add_row("Events Processed", "", str(data.get("events_processed", 0)))
    table.add_row("Actions Dispatched", "", str(data.get("actions_dispatched", 0)))

    for source in data.get("event_sources", []):
        table.add_row(
            f"Source: {source['name']}",
            "Running" if source.get("running") else "Stopped",
            "",
        )

    console.print(table)


@app.command("rules")
def butler_rules(
    ctx: typer.Context,
    action: str = typer.Argument("list", help="Action: list, add, remove"),
    name: str = typer.Option("", "--name", "-n", help="Rule name"),
    rule_id: str = typer.Option("", "--id", help="Rule ID (for remove)"),
    trigger_source: str = typer.Option("*", "--source", "-s", help="Event source to match"),
    trigger_type: str = typer.Option("*", "--type", "-t", help="Event type to match"),
    action_type: str = typer.Option(
        "notify", "--action-type", "-a", help="Action type: notify, execute_mission, log_memory"
    ),
    channel: str = typer.Option("telegram", "--channel", "-c", help="Notification channel"),
    template: str = typer.Option("", "--template", help="Message template"),
) -> None:
    """Manage butler trigger rules."""
    asyncio.run(
        _manage_rules(
            action,
            name,
            rule_id,
            trigger_source,
            trigger_type,
            action_type,
            channel,
            template,
        )
    )


async def _manage_rules(
    action: str,
    name: str,
    rule_id: str,
    trigger_source: str,
    trigger_type: str,
    action_type_str: str,
    channel: str,
    template: str,
) -> None:
    """Manage trigger rules via the rule engine."""
    from taskforce.application.rule_engine import RuleEngine
    from taskforce.core.domain.trigger_rule import (
        RuleAction,
        RuleActionType,
        TriggerCondition,
        TriggerRule,
    )

    engine = RuleEngine(work_dir=".taskforce")
    await engine.load()

    if action == "list":
        rules = await engine.list_rules()
        if not rules:
            console.print("[yellow]No rules configured.[/yellow]")
            return
        table = Table(title="Trigger Rules")
        table.add_column("ID", style="dim")
        table.add_column("Name", style="cyan")
        table.add_column("Source", style="green")
        table.add_column("Event Type", style="green")
        table.add_column("Action", style="yellow")
        table.add_column("Enabled")
        for rule in rules:
            table.add_row(
                rule.rule_id[:8],
                rule.name,
                rule.trigger.source,
                rule.trigger.event_type,
                rule.action.action_type.value,
                "Yes" if rule.enabled else "No",
            )
        console.print(table)

    elif action == "add":
        if not name:
            console.print("[red]--name is required for adding a rule.[/red]")
            return
        rule = TriggerRule(
            name=name,
            trigger=TriggerCondition(
                source=trigger_source,
                event_type=trigger_type,
            ),
            action=RuleAction(
                action_type=RuleActionType(action_type_str),
                params={"channel": channel},
                template=template or None,
            ),
        )
        rule_id_created = await engine.add_rule(rule)
        console.print(f"[green]Rule '{name}' created (ID: {rule_id_created[:8]})[/green]")

    elif action == "remove":
        if not rule_id:
            console.print("[red]--id is required for removing a rule.[/red]")
            return
        removed = await engine.remove_rule(rule_id)
        if removed:
            console.print(f"[green]Rule {rule_id[:8]} removed.[/green]")
        else:
            console.print(f"[red]Rule {rule_id[:8]} not found.[/red]")

    else:
        console.print(f"[red]Unknown action: {action}[/red]")


@app.command("schedules")
def butler_schedules(
    ctx: typer.Context,
    action: str = typer.Argument("list", help="Action: list"),
) -> None:
    """List butler scheduled jobs."""
    asyncio.run(_list_schedules())


async def _list_schedules() -> None:
    """List all scheduled jobs from the file store."""
    from taskforce.application.infrastructure_builder import InfrastructureBuilder

    store = InfrastructureBuilder().build_job_store(work_dir=".taskforce")
    jobs = await store.load_all()

    if not jobs:
        console.print("[yellow]No scheduled jobs.[/yellow]")
        return

    table = Table(title="Scheduled Jobs")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Expression", style="yellow")
    table.add_column("Action", style="white")
    table.add_column("Enabled")
    table.add_column("Last Run", style="dim")

    for job in jobs:
        table.add_row(
            job.job_id[:8],
            job.name,
            job.schedule_type.value,
            job.expression,
            job.action.action_type.value,
            "Yes" if job.enabled else "No",
            job.last_run.isoformat()[:19] if job.last_run else "Never",
        )
    console.print(table)
