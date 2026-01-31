"""Chat command - Interactive chat mode with a simple REPL console."""

import asyncio
import contextlib
import logging
from datetime import datetime, timezone
from pathlib import Path
import uuid

import structlog
import typer

from taskforce.api.cli.simple_chat import run_simple_chat
from taskforce.application.factory import AgentFactory
from taskforce.application.tracing_facade import init_tracing, shutdown_tracing

app = typer.Typer(help="Interactive chat mode", invoke_without_command=True)


def _run_chat(
    ctx: typer.Context,
    profile: str | None = typer.Option(
        None, "--profile", "-p", help="Configuration profile (overrides global --profile)"
    ),
    plugin: str | None = typer.Option(
        None, "--plugin", "-P", help="Path to external plugin directory (e.g., examples/accounting_agent)"
    ),
    user_id: str | None = typer.Option(
        None, "--user-id", help="User ID for RAG context"
    ),
    org_id: str | None = typer.Option(
        None, "--org-id", help="Organization ID for RAG context"
    ),
    scope: str | None = typer.Option(
        None, "--scope", help="Scope for RAG context (shared/org/user)"
    ),
    debug: bool | None = typer.Option(
        None, "--debug", help="Enable debug output (overrides global --debug)"
    ),
    lean: bool = typer.Option(
        False, "--lean", "-l", help="Use Agent (native tool calling, PlannerTool)"
    ),
    stream: bool = typer.Option(
        True, "--stream/--no-stream", "-S",
        help="Enable real-time streaming output (default: enabled)",
    ),
):
    """Start interactive chat session with agent in a simple console.

    The chat interface features:
    - Streaming responses
    - Inline events and plan updates
    - Slash commands (/help, /clear, /tokens, /commands, /quit)

    For RAG agents, use --user-id, --org-id, and --scope to set user context.

    Examples:
        # Standard chat
        taskforce chat

        # Agent chat (new simplified architecture)
        taskforce chat --lean

        # Load external plugin with custom tools
        taskforce chat --plugin examples/accounting_agent

        # RAG chat with user context
        taskforce --profile rag_dev chat --user-id ms-user --org-id MS-corp
    """
    # Get global options from context, allow local override
    global_opts = ctx.obj or {}
    profile = profile or global_opts.get("profile", "dev")
    debug = debug if debug is not None else global_opts.get("debug", False)

    # Configure logging to file to avoid interfering with console output
    log_dir = Path.home() / ".taskforce" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = log_dir / f"taskforce_chat_{timestamp}.log"

    logging.captureWarnings(True)
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.WARNING,
        format="%(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8")],
        force=True,
    )
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if debug else logging.WARNING
        ),
    )

    # Initialize Phoenix OTEL tracing (auto-instruments LiteLLM calls)
    with log_path.open("a", encoding="utf-8") as log_file:
        with contextlib.redirect_stdout(log_file), contextlib.redirect_stderr(log_file):
            init_tracing()

    # Build user context if provided
    user_context = None
    if user_id or org_id or scope:
        user_context = {}
        if user_id:
            user_context["user_id"] = user_id
        if org_id:
            user_context["org_id"] = org_id
        if scope:
            user_context["scope"] = scope

    # Generate session ID
    session_id = str(uuid.uuid4())

    async def run_chat_ui():
        """Run the chat session."""
        # Create agent using Agent (the standard agent implementation)
        factory = AgentFactory()

        # Determine display name for the profile/plugin
        display_profile = profile

        if plugin:
            # Load agent with plugin tools
            agent = await factory.create_agent_with_plugin(
                plugin_path=plugin,
                profile=profile,
                user_context=user_context,
            )
            # Use plugin name for display
            if hasattr(agent, '_plugin_manifest') and agent._plugin_manifest:
                display_profile = f"plugin:{agent._plugin_manifest.name}"
        else:
            # Standard agent creation
            agent = await factory.create_agent(
                config=profile, user_context=user_context
            )

        try:
            if not stream:
                logging.warning(
                    "Simple chat supports streaming only; forcing --stream."
                )
            await run_simple_chat(
                session_id=session_id,
                profile=display_profile,
                agent=agent,
                stream=True,
                user_context=user_context,
            )
        finally:
            # Clean up agent connections
            if agent:
                await agent.close()

    # Run the async UI
    try:
        asyncio.run(run_chat_ui())
    finally:
        # Shutdown tracing and flush pending spans
        shutdown_tracing()


@app.callback()
def chat(
    ctx: typer.Context,
    profile: str | None = typer.Option(
        None, "--profile", "-p", help="Configuration profile (overrides global --profile)"
    ),
    plugin: str | None = typer.Option(
        None, "--plugin", "-P", help="Path to external plugin directory (e.g., examples/accounting_agent)"
    ),
    user_id: str | None = typer.Option(
        None, "--user-id", help="User ID for RAG context"
    ),
    org_id: str | None = typer.Option(
        None, "--org-id", help="Organization ID for RAG context"
    ),
    scope: str | None = typer.Option(
        None, "--scope", help="Scope for RAG context (shared/org/user)"
    ),
    debug: bool | None = typer.Option(
        None, "--debug", help="Enable debug output (overrides global --debug)"
    ),
    lean: bool = typer.Option(
        False, "--lean", "-l", help="Use Agent (native tool calling, PlannerTool)"
    ),
    stream: bool = typer.Option(
        True, "--stream/--no-stream", "-S",
        help="Enable real-time streaming output (default: enabled)",
    ),
):
    """Run chat when no subcommand is provided."""
    if ctx.invoked_subcommand is not None:
        return
    _run_chat(
        ctx=ctx,
        profile=profile,
        plugin=plugin,
        user_id=user_id,
        org_id=org_id,
        scope=scope,
        debug=debug,
        lean=lean,
        stream=stream,
    )


@app.command("chat")
def chat_command(
    ctx: typer.Context,
    profile: str | None = typer.Option(
        None, "--profile", "-p", help="Configuration profile (overrides global --profile)"
    ),
    plugin: str | None = typer.Option(
        None, "--plugin", "-P", help="Path to external plugin directory (e.g., examples/accounting_agent)"
    ),
    user_id: str | None = typer.Option(
        None, "--user-id", help="User ID for RAG context"
    ),
    org_id: str | None = typer.Option(
        None, "--org-id", help="Organization ID for RAG context"
    ),
    scope: str | None = typer.Option(
        None, "--scope", help="Scope for RAG context (shared/org/user)"
    ),
    debug: bool | None = typer.Option(
        None, "--debug", help="Enable debug output (overrides global --debug)"
    ),
    lean: bool = typer.Option(
        False, "--lean", "-l", help="Use Agent (native tool calling, PlannerTool)"
    ),
    stream: bool = typer.Option(
        True, "--stream/--no-stream", "-S",
        help="Enable real-time streaming output (default: enabled)",
    ),
):
    """Backwards-compatible subcommand for chat."""
    _run_chat(
        ctx=ctx,
        profile=profile,
        plugin=plugin,
        user_id=user_id,
        org_id=org_id,
        scope=scope,
        debug=debug,
        lean=lean,
        stream=stream,
    )
