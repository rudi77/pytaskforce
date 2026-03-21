"""Health check command for Taskforce installation.

Validates that the environment is correctly set up:
Python version, package installation, config files, LLM connectivity,
and optional extras.
"""

import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Health check and diagnostics")
console = Console()

CHECK = "[green]✓[/green]"
CROSS = "[red]✗[/red]"
WARN = "[yellow]![/yellow]"


def _check_python_version() -> tuple[str, str]:
    """Check Python version is 3.11+."""
    major, minor = sys.version_info[:2]
    version_str = f"{major}.{minor}.{sys.version_info.micro}"
    if (major, minor) >= (3, 11):
        return CHECK, f"Python {version_str}"
    return CROSS, f"Python {version_str} (requires 3.11+)"


def _check_package_version() -> tuple[str, str]:
    """Check taskforce is importable and get version."""
    try:
        from taskforce import __version__

        return CHECK, f"Taskforce {__version__}"
    except ImportError:
        return CROSS, "Taskforce package not importable"


def _check_workspace() -> tuple[str, str]:
    """Check .taskforce workspace directory exists."""
    work_dir = Path(".taskforce")
    if work_dir.is_dir():
        return CHECK, f"Workspace: {work_dir.resolve()}"
    return CROSS, "Workspace .taskforce/ not found (run 'taskforce init')"


def _check_env_file() -> tuple[str, str]:
    """Check .env file exists and has content."""
    env_path = Path(".env")
    if not env_path.exists():
        return WARN, "No .env file (API keys may be set in environment)"

    content = env_path.read_text().strip()
    # Count non-comment, non-empty lines
    active_lines = [
        line for line in content.splitlines() if line.strip() and not line.strip().startswith("#")
    ]
    if active_lines:
        return CHECK, f".env configured ({len(active_lines)} variable(s))"
    return WARN, ".env file exists but has no active variables"


def _check_llm_config() -> tuple[str, str]:
    """Check LLM config exists."""
    paths_to_check = [
        Path(".taskforce/config/llm_config.yaml"),
        Path("src/taskforce/configs/llm_config.yaml"),
    ]
    for p in paths_to_check:
        if p.exists():
            return CHECK, f"LLM config: {p}"
    return WARN, "No llm_config.yaml found"


def _check_llm_keys() -> tuple[str, str]:
    """Check if any LLM API key is set in environment."""
    # Load .env if present
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if value and key not in os.environ:
                    os.environ[key] = value

    key_names = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "AZURE_API_KEY",
        "AZURE_OPENAI_API_KEY",
    ]
    found = [k for k in key_names if os.environ.get(k)]

    if found:
        providers = ", ".join(found)
        return CHECK, f"API key(s): {providers}"

    # Check for Ollama
    try:
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", 11434))
        sock.close()
        if result == 0:
            return CHECK, "Ollama detected on localhost:11434"
    except Exception:
        pass

    return CROSS, "No LLM API key found in environment or .env"


def _check_extra(name: str, import_check: str, description: str) -> tuple[str, str]:
    """Check if an optional extra is installed."""
    try:
        __import__(import_check)
        return CHECK, f"{description}"
    except ImportError:
        return WARN, f"{description} (not installed)"


def _check_profile(profile_name: Optional[str]) -> tuple[str, str]:
    """Check if the selected profile is valid."""
    if not profile_name:
        profile_name = "dev"

    # Check local config first
    local_profile = Path(".taskforce/config/profile.yaml")
    if local_profile.exists():
        return CHECK, f"Profile: {profile_name} (local override)"

    # Check bundled profiles
    paths_to_check = [
        Path("src/taskforce/configs") / f"{profile_name}.yaml",
    ]

    # Also check installed package location
    try:
        import importlib.resources

        pkg_configs = importlib.resources.files("taskforce") / "configs"
        if (pkg_configs / f"{profile_name}.yaml").is_file():  # type: ignore[union-attr]
            return CHECK, f"Profile: {profile_name} (bundled)"
    except Exception:
        pass

    for p in paths_to_check:
        if p.exists():
            return CHECK, f"Profile: {profile_name} ({p})"

    return CROSS, f"Profile '{profile_name}' not found"


@app.callback(invoke_without_command=True)
def doctor(
    ctx: typer.Context,
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile to validate"),
) -> None:
    """Run health checks on the Taskforce installation.

    Validates Python version, package installation, workspace setup,
    LLM configuration, and optional extras.
    """
    console.print()
    console.print("[bold cyan]Taskforce Doctor[/bold cyan]")
    console.print("─" * 40)
    console.print()

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Status", min_width=3)
    table.add_column("Check")

    # Core checks
    checks = [
        _check_python_version(),
        _check_package_version(),
        _check_workspace(),
        _check_env_file(),
        _check_llm_config(),
        _check_llm_keys(),
        _check_profile(profile),
    ]

    # Optional extras
    extras = [
        ("playwright", "playwright", "Browser automation (playwright)"),
        ("azure.search.documents", "azure.search.documents", "RAG (azure-search-documents)"),
        ("pypdf", "pypdf", "PDF processing (pypdf)"),
        ("sqlalchemy", "sqlalchemy", "PostgreSQL (sqlalchemy)"),
        ("tiktoken", "tiktoken", "Tokenizer (tiktoken)"),
    ]

    for import_name, import_check, description in extras:
        checks.append(_check_extra(import_name, import_check, description))

    for status, message in checks:
        table.add_row(status, message)

    console.print(table)
    console.print()

    # Count issues
    errors = sum(1 for s, _ in checks if CROSS in s)
    warnings = sum(1 for s, _ in checks if WARN in s)

    if errors:
        console.print(
            f"[red]{errors} error(s) found.[/red] "
            "Run 'taskforce init' to fix configuration issues."
        )
    elif warnings:
        console.print(f"[yellow]{warnings} warning(s).[/yellow] Setup is functional.")
    else:
        console.print("[green]All checks passed![/green] Taskforce is ready.")

    console.print()
