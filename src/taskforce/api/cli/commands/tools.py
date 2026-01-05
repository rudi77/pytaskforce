"""Tools command - List and inspect available tools."""

import asyncio

import typer
from rich.console import Console
from rich.table import Table

from taskforce.application.factory import AgentFactory

app = typer.Typer(help="Tool management")
console = Console()


@app.command("list")
def list_tools(
    ctx: typer.Context,
    profile: str = typer.Option(None, "--profile", "-p", help="Configuration profile (overrides global --profile)")
):
    """List available tools."""
    # Get global options from context, allow local override
    global_opts = ctx.obj or {}
    profile = profile or global_opts.get("profile", "dev")

    async def _list_tools():
        factory = AgentFactory()
        agent = await factory.create_agent(profile=profile)

        try:
            table = Table(title="Available Tools")
            table.add_column("Name", style="cyan")
            table.add_column("Description", style="white")

            # agent.tools is a dict, iterate over values
            for tool in agent.tools.values():
                table.add_row(tool.name, tool.description)

            console.print(table)
        finally:
            await agent.close()

    asyncio.run(_list_tools())


@app.command("inspect")
def inspect_tool(
    ctx: typer.Context,
    tool_name: str = typer.Argument(..., help="Tool name to inspect"),
    profile: str = typer.Option(None, "--profile", "-p", help="Configuration profile (overrides global --profile)"),
):
    """Inspect tool details and parameters."""
    # Get global options from context, allow local override
    global_opts = ctx.obj or {}
    profile = profile or global_opts.get("profile", "dev")

    async def _inspect_tool():
        factory = AgentFactory()
        agent = await factory.create_agent(profile=profile)

        try:
            # agent.tools is a dict, access by key
            tool = agent.tools.get(tool_name)

            if not tool:
                console.print(f"[red]Tool '{tool_name}' not found[/red]")
                raise typer.Exit(1)

            console.print(f"\n[bold cyan]{tool.name}[/bold cyan]")
            console.print(f"{tool.description}\n")

            console.print("[bold]Parameters:[/bold]")
            console.print_json(data=tool.parameters_schema)
        finally:
            await agent.close()

    asyncio.run(_inspect_tool())

