"""Chat command - Interactive chat mode with agent using Textual UI."""

import asyncio
import logging
import uuid

import structlog
import typer

from taskforce.api.cli.chat_ui import TaskforceChatApp
from taskforce.application.factory import AgentFactory
from taskforce.application.tracing_facade import init_tracing, shutdown_tracing

app = typer.Typer(help="Interactive chat mode")


@app.command()
def chat(
    ctx: typer.Context,
    profile: str | None = typer.Option(
        None, "--profile", "-p", help="Configuration profile (overrides global --profile)"
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
    """Start interactive chat session with agent using modern TUI.

    The chat interface features:
    - Fixed input bar at the bottom
    - Scrollable message history
    - Real-time status updates
    - Plan visualization
    - Token usage tracking

    For RAG agents, use --user-id, --org-id, and --scope to set user context.

    Examples:
        # Standard chat with new UI
        taskforce chat

        # Agent chat (new simplified architecture)
        taskforce chat --lean

        # Streaming chat with real-time output (default)
        taskforce chat --lean --stream

        # Non-streaming mode
        taskforce chat --no-stream

        # RAG chat with user context
        taskforce --profile rag_dev chat --user-id ms-user --org-id MS-corp

        # Debug mode to see agent thoughts and actions
        taskforce --debug chat
    """
    # Get global options from context, allow local override
    global_opts = ctx.obj or {}
    profile = profile or global_opts.get("profile", "dev")
    debug = debug if debug is not None else global_opts.get("debug", False)

    # Configure logging level based on debug flag
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

    # Initialize Phoenix OTEL tracing (auto-instruments LiteLLM calls)
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
        """Run the chat UI application."""
        # Create agent using Agent (the standard agent implementation)
        factory = AgentFactory()
        agent = await factory.create_agent(
            profile=profile, user_context=user_context
        )

        try:
            # Create and run the Textual app
            chat_app = TaskforceChatApp(
                session_id=session_id,
                profile=profile,
                agent=agent,
                debug=debug,
                stream=stream,
                user_context=user_context,
            )
            await chat_app.run_async()
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
