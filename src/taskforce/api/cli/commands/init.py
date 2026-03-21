"""Interactive setup wizard for Taskforce.

Guides users through initial configuration after installation:
LLM provider selection, API key setup, profile choice, and workspace creation.
"""

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

# ── Provider definitions ────────────────────────────────────────────────────

PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "env_keys": {"OPENAI_API_KEY": "OpenAI API key"},
        "default_models": {
            "main": "gpt-4.1-mini",
            "powerful": "gpt-4.1",
            "fast": "gpt-4.1-nano",
        },
        "prefix": "",
    },
    "anthropic": {
        "name": "Anthropic",
        "env_keys": {"ANTHROPIC_API_KEY": "Anthropic API key"},
        "default_models": {
            "main": "anthropic/claude-sonnet-4-6",
            "powerful": "anthropic/claude-opus-4-6",
            "fast": "anthropic/claude-haiku-4-5-20251001",
        },
        "prefix": "anthropic/",
    },
    "gemini": {
        "name": "Google Gemini",
        "env_keys": {"GEMINI_API_KEY": "Gemini API key"},
        "default_models": {
            "main": "gemini/gemini-2.5-flash",
            "powerful": "gemini/gemini-2.5-pro",
            "fast": "gemini/gemini-2.0-flash-lite",
        },
        "prefix": "gemini/",
    },
    "azure": {
        "name": "Azure OpenAI",
        "env_keys": {
            "AZURE_API_KEY": "Azure OpenAI API key",
            "AZURE_API_BASE": "Azure endpoint URL (https://your-resource.openai.azure.com/)",
            "AZURE_API_VERSION": "API version (e.g. 2024-02-15-preview)",
        },
        "default_models": {
            "main": "azure/gpt-4.1-mini",
            "powerful": "azure/gpt-4.1",
            "fast": "azure/gpt-4.1-nano",
        },
        "prefix": "azure/",
    },
    "ollama": {
        "name": "Ollama (local)",
        "env_keys": {},
        "default_models": {
            "main": "ollama/llama3",
            "powerful": "ollama/llama3",
            "fast": "ollama/llama3",
        },
        "prefix": "ollama/",
    },
}

PROFILES = {
    "dev": "General-purpose development agent",
    "coding_agent": "Coding specialist with sub-agents",
    "butler": "Personal AI assistant daemon (event-driven)",
    "rag_agent": "RAG-enabled agent (requires Azure AI Search)",
    "security": "Security-hardened profile",
}

EXTRAS = {
    "browser": "Browser automation (Playwright headless)",
    "rag": "RAG / Azure AI Search integration",
    "pdf": "PDF processing (read, extract, generate)",
    "postgres": "PostgreSQL persistence (production)",
    "personal-assistant": "Google Calendar / personal assistant",
}


@dataclass
class InitConfig:
    """Collected configuration from the init wizard."""

    provider: str = "openai"
    api_keys: dict[str, str] = field(default_factory=dict)
    model_aliases: dict[str, str] = field(default_factory=dict)
    profile: str = "dev"
    extras: list[str] = field(default_factory=list)
    work_dir: Path = field(default_factory=lambda: Path(".taskforce"))
    ollama_model: str = "llama3"


# ── Wizard steps ────────────────────────────────────────────────────────────


def _print_welcome() -> None:
    """Print welcome banner and explain what init does."""
    from taskforce import __version__

    banner = Text()
    banner.append("TASKFORCE", style="bold cyan")
    banner.append(f"  v{__version__}", style="dim")

    console.print()
    console.print(
        Panel(
            banner,
            title="Setup Wizard",
            border_style="cyan",
            padding=(1, 4),
        )
    )
    console.print()
    console.print(
        "This wizard will configure Taskforce so you can start immediately.\n"
        "It will:\n"
        "  1. Set up your LLM provider and API key\n"
        "  2. Choose a default profile\n"
        "  3. Create the workspace directory and config files\n"
    )


def _select_provider() -> str:
    """Prompt user to select an LLM provider."""
    console.print("[bold]Step 1:[/bold] Select your LLM provider\n")

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="cyan bold", min_width=4)
    table.add_column("Provider")

    provider_keys = list(PROVIDERS.keys())
    for i, key in enumerate(provider_keys, 1):
        table.add_row(str(i), PROVIDERS[key]["name"])

    console.print(table)
    console.print()

    while True:
        choice = typer.prompt("Enter number", default="1")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(provider_keys):
                selected = provider_keys[idx]
                console.print(f"  Selected: [cyan]{PROVIDERS[selected]['name']}[/cyan]\n")
                return selected
        except ValueError:
            pass
        console.print("[red]Invalid choice. Please enter a number.[/red]")


def _collect_api_keys(provider: str) -> dict[str, str]:
    """Prompt for provider-specific API keys."""
    provider_info = PROVIDERS[provider]
    env_keys = provider_info["env_keys"]

    if not env_keys:
        console.print("[dim]No API key required for this provider.[/dim]\n")
        return {}

    console.print("[bold]Step 2:[/bold] Enter your API credentials\n")
    keys: dict[str, str] = {}

    for env_var, description in env_keys.items():
        # Check if already set in environment
        existing = os.environ.get(env_var)
        if existing:
            masked = existing[:8] + "..." if len(existing) > 8 else "***"
            use_existing = typer.confirm(
                f"  {env_var} already set ({masked}). Use existing?", default=True
            )
            if use_existing:
                keys[env_var] = existing
                continue

        value = typer.prompt(f"  {description}", hide_input="KEY" in env_var.upper())
        if value.strip():
            keys[env_var] = value.strip()

    console.print()
    return keys


def _configure_models(provider: str) -> dict[str, str]:
    """Configure model aliases for the selected provider."""
    provider_info = PROVIDERS[provider]
    defaults = provider_info["default_models"]

    console.print("[bold]Step 3:[/bold] Model configuration\n")

    table = Table(show_header=True, box=None, padding=(0, 2))
    table.add_column("Alias", style="cyan")
    table.add_column("Model", style="white")
    table.add_column("Usage", style="dim")

    table.add_row("main", defaults["main"], "Default for most tasks")
    table.add_row("powerful", defaults["powerful"], "Complex reasoning, planning")
    table.add_row("fast", defaults["fast"], "Quick tasks, summaries")

    console.print(table)
    console.print()

    use_defaults = typer.confirm("Use these defaults?", default=True)

    if use_defaults:
        console.print()
        return dict(defaults)

    models = {}
    for alias, default in defaults.items():
        value = typer.prompt(f"  Model for '{alias}'", default=default)
        models[alias] = value.strip()

    console.print()
    return models


def _select_profile() -> str:
    """Prompt user to select a default profile."""
    console.print("[bold]Step 4:[/bold] Select your default profile\n")

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="cyan bold", min_width=4)
    table.add_column("Profile", style="white", min_width=16)
    table.add_column("Description", style="dim")

    profile_keys = list(PROFILES.keys())
    for i, key in enumerate(profile_keys, 1):
        table.add_row(str(i), key, PROFILES[key])

    console.print(table)
    console.print()

    while True:
        choice = typer.prompt("Enter number", default="1")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(profile_keys):
                selected = profile_keys[idx]
                console.print(f"  Selected: [cyan]{selected}[/cyan]\n")
                return selected
        except ValueError:
            pass
        console.print("[red]Invalid choice.[/red]")


def _select_extras() -> list[str]:
    """Prompt user to select optional dependency groups."""
    console.print("[bold]Step 5:[/bold] Optional features (install later with pip)\n")

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="cyan bold", min_width=4)
    table.add_column("Extra", style="white", min_width=20)
    table.add_column("Description", style="dim")

    extra_keys = list(EXTRAS.keys())
    for i, key in enumerate(extra_keys, 1):
        table.add_row(str(i), key, EXTRAS[key])

    console.print(table)
    console.print()

    raw = typer.prompt(
        "Enter numbers separated by commas (or 'none')",
        default="none",
    )

    if raw.strip().lower() == "none":
        console.print()
        return []

    selected = []
    for part in raw.split(","):
        part = part.strip()
        try:
            idx = int(part) - 1
            if 0 <= idx < len(extra_keys):
                selected.append(extra_keys[idx])
        except ValueError:
            pass

    if selected:
        console.print(f"  Selected: [cyan]{', '.join(selected)}[/cyan]\n")
    else:
        console.print()

    return selected


# ── File generation ─────────────────────────────────────────────────────────


def _generate_env_file(config: InitConfig, target: Path) -> None:
    """Generate .env file with collected API keys."""
    lines = [
        "# Taskforce environment configuration",
        "# Generated by 'taskforce init'",
        "",
    ]

    # Write all API keys
    for key, value in config.api_keys.items():
        lines.append(f"{key}={value}")

    # Add commented-out placeholders for other common keys
    existing_keys = set(config.api_keys.keys())
    optional = {
        "GITHUB_TOKEN": "GitHub API token (for git tools)",
    }
    if optional.keys() - existing_keys:
        lines.append("")
        lines.append("# Optional")
        for key, desc in optional.items():
            if key not in existing_keys:
                lines.append(f"# {key}=  # {desc}")

    lines.append("")
    target.write_text("\n".join(lines))


def _generate_llm_config(config: InitConfig, target: Path) -> None:
    """Generate provider-specific llm_config.yaml."""
    llm_config = {
        "default_model": "main",
        "models": config.model_aliases,
        "default_params": {
            "temperature": 0.7,
            "max_tokens": 8000,
        },
        "retry": {
            "max_attempts": 3,
            "backoff_multiplier": 2,
            "timeout": 60,
        },
        "logging": {
            "log_prompts": False,
            "log_completions": False,
            "log_token_usage": True,
            "log_latency": True,
        },
        "routing": {
            "enabled": True,
            "default_model": "main",
            "rules": [
                {"condition": "hint:planning", "model": "powerful"},
                {"condition": "hint:reasoning", "model": "main"},
                {"condition": "hint:summarizing", "model": "fast"},
                {"condition": "has_tools", "model": "main"},
            ],
        },
    }

    # Add provider-specific model params
    if config.provider == "anthropic":
        llm_config["model_params"] = {
            config.model_aliases.get("main", ""): {
                "max_tokens": 8192,
                "temperature": 0.7,
            }
        }
    elif config.provider == "ollama":
        llm_config["model_params"] = {
            config.model_aliases.get("main", ""): {
                "max_tokens": 4096,
                "temperature": 0.7,
            }
        }

    target.write_text(yaml.dump(llm_config, default_flow_style=False, sort_keys=False))


def _generate_profile_override(config: InitConfig, target: Path) -> None:
    """Generate a local profile override that points to the local llm_config."""
    override = {
        "profile": config.profile,
        "llm": {
            "config_path": str(config.work_dir / "config" / "llm_config.yaml"),
            "default_model": "main",
        },
        "persistence": {
            "type": "file",
            "work_dir": str(config.work_dir),
        },
    }
    target.write_text(yaml.dump(override, default_flow_style=False, sort_keys=False))


def _setup_workspace(config: InitConfig) -> None:
    """Create workspace directory and configuration files."""
    console.print("[bold]Setting up workspace...[/bold]\n")

    work_dir = config.work_dir
    config_dir = work_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    # Generate files
    env_path = Path(".env")
    if env_path.exists():
        overwrite = typer.confirm("  .env already exists. Overwrite?", default=False)
        if not overwrite:
            console.print("  [dim]Keeping existing .env[/dim]")
        else:
            _generate_env_file(config, env_path)
            console.print("  [green]Created .env[/green]")
    else:
        _generate_env_file(config, env_path)
        console.print("  [green]Created .env[/green]")

    llm_config_path = config_dir / "llm_config.yaml"
    _generate_llm_config(config, llm_config_path)
    console.print(f"  [green]Created {llm_config_path}[/green]")

    profile_path = config_dir / "profile.yaml"
    _generate_profile_override(config, profile_path)
    console.print(f"  [green]Created {profile_path}[/green]")

    # Add .env to .gitignore if present
    gitignore = Path(".gitignore")
    if gitignore.exists():
        content = gitignore.read_text()
        if ".env" not in content:
            with open(gitignore, "a") as f:
                f.write("\n# Taskforce secrets\n.env\n")
            console.print("  [green]Added .env to .gitignore[/green]")

    console.print()


def _validate_llm(config: InitConfig) -> bool:
    """Test LLM connectivity with a minimal API call."""
    console.print("[bold]Validating LLM connection...[/bold]")

    # Set env vars temporarily for validation
    for key, value in config.api_keys.items():
        os.environ[key] = value

    try:
        import asyncio

        from litellm import acompletion

        async def _test() -> str:
            model = config.model_aliases.get("fast") or config.model_aliases.get("main", "")
            response = await acompletion(
                model=model,
                messages=[{"role": "user", "content": "Say 'hello' in one word."}],
                max_tokens=5,
                timeout=15,
            )
            return response.choices[0].message.content or ""

        result = asyncio.run(_test())
        console.print(f"  [green]Success![/green] Response: {result.strip()}\n")
        return True
    except Exception as e:
        console.print(f"  [red]Failed:[/red] {e}\n")
        console.print(
            "  [dim]You can fix the configuration later by editing .env "
            "or running 'taskforce init' again.[/dim]\n"
        )
        return False


def _install_extras(extras: list[str]) -> None:
    """Install selected optional dependency groups."""
    if not extras:
        return

    extras_str = ",".join(extras)
    console.print(f"[bold]Installing extras:[/bold] {extras_str}\n")

    # Detect if we're in a development environment (uv sync) or installed via pip
    is_dev = Path("pyproject.toml").exists() and Path("uv.lock").exists()

    if is_dev:
        cmd = ["uv", "sync"] + [f"--extra={e}" for e in extras]
    else:
        cmd = [sys.executable, "-m", "pip", "install", f"taskforce[{extras_str}]"]

    console.print(f"  Running: [dim]{' '.join(cmd)}[/dim]")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            console.print("  [green]Extras installed successfully.[/green]\n")
        else:
            console.print(f"  [red]Installation failed.[/red]\n  {result.stderr[:500]}\n")
            console.print(
                f"  [dim]You can install manually: {' '.join(cmd)}[/dim]\n"
            )
    except FileNotFoundError:
        console.print(
            f"  [yellow]Command not found. Install manually:[/yellow]\n"
            f"  pip install taskforce[{extras_str}]\n"
        )
    except subprocess.TimeoutExpired:
        console.print("  [yellow]Installation timed out. Install manually.[/yellow]\n")


def _print_summary(config: InitConfig, validation_ok: bool) -> None:
    """Print final setup summary."""
    table = Table(title="Setup Summary", show_header=False, border_style="cyan")
    table.add_column("Setting", style="bold")
    table.add_column("Value", style="cyan")

    table.add_row("Provider", PROVIDERS[config.provider]["name"])
    table.add_row("Main model", config.model_aliases.get("main", "—"))
    table.add_row("Profile", config.profile)
    table.add_row("Workspace", str(config.work_dir))
    table.add_row(
        "LLM connection",
        "[green]OK[/green]" if validation_ok else "[yellow]Not verified[/yellow]",
    )
    if config.extras:
        table.add_row("Extras", ", ".join(config.extras))

    console.print(table)
    console.print()
    console.print("[bold]Next steps:[/bold]")
    console.print("  taskforce chat                     # Interactive chat")
    console.print('  taskforce run mission "Your task"   # Run a mission')
    console.print("  taskforce doctor                   # Check setup health")
    console.print()


# ── Main command ────────────────────────────────────────────────────────────


def init_command(
    provider: Optional[str] = typer.Option(
        None,
        "--provider",
        help="LLM provider (openai, anthropic, gemini, azure, ollama)",
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        help="Primary API key for the selected provider",
    ),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        help="Default profile (dev, coding_agent, butler, etc.)",
    ),
    extras: Optional[str] = typer.Option(
        None,
        "--extras",
        help="Comma-separated optional extras to install (browser,pdf,rag,...)",
    ),
    no_validate: bool = typer.Option(
        False,
        "--no-validate",
        help="Skip LLM connection validation",
    ),
    work_dir: str = typer.Option(
        ".taskforce",
        "--work-dir",
        help="Workspace directory",
    ),
) -> None:
    """Set up Taskforce with an interactive wizard.

    Configures your LLM provider, API keys, default profile, and
    workspace so you can start using Taskforce immediately.

    Run non-interactively with flags:
        taskforce init --provider openai --api-key sk-... --profile dev
    """
    is_interactive = provider is None

    if is_interactive:
        _print_welcome()

    config = InitConfig(work_dir=Path(work_dir))

    # Step 1: Provider
    if provider:
        if provider not in PROVIDERS:
            console.print(f"[red]Unknown provider: {provider}[/red]")
            console.print(f"Available: {', '.join(PROVIDERS.keys())}")
            raise typer.Exit(1)
        config.provider = provider
    else:
        config.provider = _select_provider()

    # Step 2: API keys
    if api_key and not is_interactive:
        # Non-interactive: map single api-key to the provider's primary key
        primary_key = next(iter(PROVIDERS[config.provider]["env_keys"]), None)
        if primary_key:
            config.api_keys = {primary_key: api_key}
    else:
        config.api_keys = _collect_api_keys(config.provider)

    # Step 3: Models
    if is_interactive:
        config.model_aliases = _configure_models(config.provider)
    else:
        config.model_aliases = dict(PROVIDERS[config.provider]["default_models"])

    # Step 4: Profile
    if profile:
        config.profile = profile
    elif is_interactive:
        config.profile = _select_profile()
    else:
        config.profile = "dev"

    # Step 5: Extras
    if extras:
        config.extras = [e.strip() for e in extras.split(",") if e.strip()]
    elif is_interactive:
        config.extras = _select_extras()

    # Step 6: Workspace setup
    _setup_workspace(config)

    # Step 7: Validation
    validation_ok = False
    if not no_validate and config.api_keys:
        validation_ok = _validate_llm(config)
    elif no_validate:
        console.print("[dim]Skipping LLM validation (--no-validate)[/dim]\n")

    # Step 8: Install extras
    if config.extras:
        install_now = True
        if is_interactive:
            install_now = typer.confirm("Install selected extras now?", default=True)
        if install_now:
            _install_extras(config.extras)

    # Step 9: Summary
    _print_summary(config, validation_ok)
