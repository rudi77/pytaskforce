"""Skills command - List and inspect available agent skills."""

from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from taskforce.application.skill_service import SkillService

app = typer.Typer(help="Skill management")
console = Console()

# Cache for skill service instance
_cli_skill_service: SkillService | None = None


def _get_skill_service() -> SkillService:
    """Get skill service with extension directories included."""
    global _cli_skill_service
    if _cli_skill_service is not None:
        return _cli_skill_service

    # Include taskforce_extensions/skills if it exists
    extension_dirs: list[str] = []

    # Check for src/taskforce_extensions/skills
    ext_dir = Path.cwd() / "src" / "taskforce_extensions" / "skills"
    if ext_dir.exists():
        extension_dirs.append(str(ext_dir))

    _cli_skill_service = SkillService(extension_directories=extension_dirs)
    return _cli_skill_service


@app.command("list")
def list_skills(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full descriptions"),
) -> None:
    """List available skills."""
    skill_service = _get_skill_service()
    metadata_list = skill_service.get_all_metadata()

    if not metadata_list:
        console.print("[yellow]No skills found.[/yellow]")
        console.print(
            "\nAdd skill directories to:\n"
            "  - ~/.taskforce/skills/ (user-level)\n"
            "  - .taskforce/skills/ (project-level)\n"
            "  - src/taskforce_extensions/skills/ (extensions)"
        )
        return

    table = Table(title="Available Skills")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Description", style="white")
    table.add_column("Source", style="dim")

    for metadata in metadata_list:
        description = metadata.description
        if not verbose and len(description) > 80:
            description = description[:77] + "..."

        # Get relative source path for display
        source_path = Path(metadata.source_path)
        try:
            source_display = str(source_path.relative_to(Path.cwd()))
        except ValueError:
            source_display = str(source_path)

        table.add_row(metadata.name, description, source_display)

    console.print(table)
    console.print(f"\n[dim]Total: {len(metadata_list)} skill(s)[/dim]")


@app.command("show")
def show_skill(
    name: str = typer.Argument(..., help="Skill name to inspect"),
    full: bool = typer.Option(False, "--full", "-f", help="Show full instructions (can be long)"),
) -> None:
    """Show details of a specific skill."""
    skill_service = _get_skill_service()
    skill = skill_service.get_skill(name)

    if not skill:
        console.print(f"[red]Skill not found: {name}[/red]")
        available = skill_service.list_skills()
        if available:
            console.print(f"\n[dim]Available skills: {', '.join(available)}[/dim]")
        raise typer.Exit(1)

    # Header
    console.print(Panel(f"[bold cyan]{skill.name}[/bold cyan]", expand=False))

    # Metadata
    console.print("\n[bold]Description:[/bold]")
    console.print(f"  {skill.description}")

    console.print("\n[bold]Source:[/bold]")
    console.print(f"  {skill.source_path}")

    # Resources
    resources = skill.get_resources()
    if resources:
        console.print(f"\n[bold]Resources:[/bold] ({len(resources)} files)")
        for resource_path in sorted(resources.keys()):
            console.print(f"  - {resource_path}")

    # Instructions
    if full:
        console.print("\n[bold]Instructions:[/bold]")
        console.print(Markdown(skill.instructions))
    else:
        # Show truncated instructions
        lines = skill.instructions.split("\n")
        preview_lines = lines[:20]
        console.print("\n[bold]Instructions preview:[/bold] (first 20 lines)")
        console.print(Markdown("\n".join(preview_lines)))
        if len(lines) > 20:
            console.print(
                f"\n[dim]... {len(lines) - 20} more lines. " f"Use --full to see all.[/dim]"
            )


@app.command("resources")
def list_resources(
    name: str = typer.Argument(..., help="Skill name"),
) -> None:
    """List resources bundled with a skill."""
    skill_service = _get_skill_service()
    skill = skill_service.get_skill(name)

    if not skill:
        console.print(f"[red]Skill not found: {name}[/red]")
        raise typer.Exit(1)

    resources = skill.get_resources()

    if not resources:
        console.print(f"[yellow]No resources found for skill '{name}'[/yellow]")
        return

    tree = Tree(f"[bold cyan]{name}[/bold cyan]")

    # Group resources by directory
    dirs: dict[str, list[str]] = {}
    root_files: list[str] = []

    for resource_path in sorted(resources.keys()):
        parts = resource_path.split("/")
        if len(parts) == 1:
            root_files.append(resource_path)
        else:
            dir_name = parts[0]
            if dir_name not in dirs:
                dirs[dir_name] = []
            dirs[dir_name].append("/".join(parts[1:]))

    # Add root files
    for f in root_files:
        tree.add(f"[green]{f}[/green]")

    # Add directories
    for dir_name, files in sorted(dirs.items()):
        dir_branch = tree.add(f"[blue]{dir_name}/[/blue]")
        for f in files:
            dir_branch.add(f"[green]{f}[/green]")

    console.print(tree)
    console.print(f"\n[dim]Total: {len(resources)} resource(s)[/dim]")


@app.command("read")
def read_resource(
    name: str = typer.Argument(..., help="Skill name"),
    resource_path: str = typer.Argument(..., help="Resource path within the skill"),
) -> None:
    """Read a specific resource from a skill."""
    skill_service = _get_skill_service()
    content = skill_service.read_skill_resource(name, resource_path)

    if content is None:
        console.print(f"[red]Resource not found: {resource_path}[/red]")

        # Show available resources
        skill = skill_service.get_skill(name)
        if skill:
            resources = skill.get_resources()
            if resources:
                console.print("\n[dim]Available resources:[/dim]")
                for r in sorted(resources.keys()):
                    console.print(f"  - {r}")
        raise typer.Exit(1)

    # Determine if it's markdown
    if resource_path.endswith(".md"):
        console.print(Markdown(content))
    else:
        console.print(content)


@app.command("paths")
def show_paths() -> None:
    """Show directories searched for skills."""
    skill_service = _get_skill_service()

    # Get search paths from the registry
    registry = skill_service._registry
    search_dirs = registry.directories

    console.print("[bold]Skill Search Paths:[/bold]")
    for i, path_obj in enumerate(search_dirs, 1):
        exists = path_obj.exists()
        status = "[green](exists)[/green]" if exists else "[dim](not found)[/dim]"
        console.print(f"  {i}. {path_obj} {status}")

    console.print("\n[bold]Default directories:[/bold]")
    console.print("  - ~/.taskforce/skills/ (user-level)")
    console.print("  - .taskforce/skills/ (project-level)")
    console.print("  - src/taskforce_extensions/skills/ (extensions)")
