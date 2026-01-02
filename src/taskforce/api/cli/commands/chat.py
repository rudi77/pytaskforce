"""Chat command - Interactive chat mode with agent."""

import asyncio

import typer
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from taskforce.api.cli.output_formatter import TaskforceConsole
from taskforce.application.executor import AgentExecutor
from taskforce.application.factory import AgentFactory
from taskforce.infrastructure.tracing import init_tracing, shutdown_tracing

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
        False, "--lean", "-l", help="Use LeanAgent (native tool calling, PlannerTool)"
    ),
    stream: bool = typer.Option(
        False, "--stream", "-S",
        help="Enable real-time streaming output. Shows tool calls, results, and answer as they happen.",
    ),
):
    """Start interactive chat session with agent.

    For RAG agents, use --user-id, --org-id, and --scope to set user context.

    Examples:
        # Standard chat
        taskforce --profile dev chat

        # LeanAgent chat (new simplified architecture)
        taskforce chat --lean

        # Streaming chat with real-time output
        taskforce chat --lean --stream

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

    # Initialize Phoenix OTEL tracing (auto-instruments LiteLLM calls)
    init_tracing()

    # Initialize our fancy console
    tf_console = TaskforceConsole(debug=debug)

    # Print banner
    tf_console.print_banner()

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

    # Show session info
    import uuid
    session_id = str(uuid.uuid4())
    tf_console.print_session_info(session_id, profile, user_context)

    if lean:
        tf_console.print_system_message("Using LeanAgent (native tool calling)", "info")
    if stream:
        tf_console.print_system_message("Streaming mode enabled", "info")
    tf_console.print_system_message("Type 'exit', 'quit', or press Ctrl+C to end session", "info")
    tf_console.print_divider()

    async def run_chat_loop():
        # Create agent once for the entire chat session
        factory = AgentFactory()

        agent = None

        # LeanAgent with optional RAG context
        if lean:
            try:
                agent = await factory.create_lean_agent(
                    profile=profile, user_context=user_context
                )
                if user_context:
                    tf_console.print_system_message(
                        "LeanAgent initialized with RAG context", "success"
                    )
                else:
                    tf_console.print_system_message("LeanAgent initialized", "success")
                tf_console.print_divider()
            except Exception as e:
                tf_console.print_warning(
                    f"Could not create LeanAgent: {e}. Falling back to standard agent."
                )
        # Legacy RAG agent with user context
        elif user_context:
            try:
                agent = await factory.create_rag_agent(
                    profile=profile, user_context=user_context
                )
                tf_console.print_system_message(
                    "RAG agent initialized with user context", "success"
                )
                tf_console.print_divider()
            except Exception as e:
                tf_console.print_warning(
                    f"Could not create RAG agent: {e}. Falling back to standard agent."
                )

        if not agent:
            agent = await factory.create_agent(profile=profile)
            tf_console.print_system_message("Agent initialized", "success")
            tf_console.print_divider()

        try:
            while True:
                # Get user input (blocking, but that's okay in CLI)
                try:
                    user_input = tf_console.prompt()
                except (KeyboardInterrupt, EOFError):
                    tf_console.print_divider()
                    tf_console.print_system_message("Goodbye! 👋", "info")
                    break

                # Check for exit commands
                if user_input.lower() in ["exit", "quit", "bye"]:
                    tf_console.print_divider()
                    tf_console.print_system_message("Goodbye! 👋", "info")
                    break

                if not user_input.strip():
                    continue

                # Show user message in panel
                tf_console.print_user_message(user_input)

                try:
                    # === CONVERSATION HISTORY MANAGEMENT ===
                    # Load current state and update conversation history with user message
                    state = await agent.state_manager.load_state(session_id) or {}
                    history = state.get("conversation_history", [])

                    # If there's a pending question, save user input as the answer
                    pending_q = state.get("pending_question")
                    if pending_q:
                        answer_key = pending_q.get("answer_key")
                        if answer_key:
                            answers = state.get("answers", {})
                            answers[answer_key] = user_input
                            state["answers"] = answers
                        # Clear pending question after answer is stored
                        state["pending_question"] = None

                    # Append user message to history
                    history.append({"role": "user", "content": user_input})
                    state["conversation_history"] = history

                    # Save state so agent can access the updated history
                    await agent.state_manager.save_state(session_id, state)

                    if stream:
                        # Streaming execution with Rich Live display
                        final_message = await _execute_streaming_chat(
                            user_input=user_input,
                            profile=profile,
                            session_id=session_id,
                            conversation_history=history,
                            user_context=user_context,
                            lean=lean,
                            console=tf_console.console,
                        )

                        # Save response to history
                        state = await agent.state_manager.load_state(session_id) or {}
                        history = state.get("conversation_history", [])
                        history.append({"role": "assistant", "content": final_message})
                        state["conversation_history"] = history
                        await agent.state_manager.save_state(session_id, state)

                        tf_console.print_debug("Status: completed")
                    else:
                        # Standard execution
                        result = await agent.execute(mission=user_input, session_id=session_id)

                        # Reload state (agent may have modified it) and append agent response
                        state = await agent.state_manager.load_state(session_id) or {}
                        history = state.get("conversation_history", [])
                        history.append({"role": "assistant", "content": result.final_message})
                        state["conversation_history"] = history
                        await agent.state_manager.save_state(session_id, state)
                        # === END CONVERSATION HISTORY MANAGEMENT ===

                        # Extract thought if available (for debug mode)
                        thought = None
                        if debug and hasattr(result, 'thoughts') and result.thoughts:
                            thought = result.thoughts[-1] if result.thoughts else None

                        # Display agent response
                        tf_console.print_agent_message(result.final_message, thought=thought)

                        # If there's a pending question, show it prominently
                        if result.status == "paused" and result.pending_question:
                            question = result.pending_question.get("question", "")
                            if question and question != result.final_message:
                                tf_console.print_warning(f"Question: {question}")

                        # Debug info
                        tf_console.print_debug(f"Status: {result.status}")

                except Exception as e:
                    tf_console.print_error(f"Execution failed: {str(e)}", exception=e if debug else None)
        finally:
            # Clean up MCP connections to avoid cancel scope errors
            if agent:
                await agent.close()

    # Run the async loop
    try:
        asyncio.run(run_chat_loop())
    finally:
        # Shutdown tracing and flush pending spans
        shutdown_tracing()


async def _execute_streaming_chat(
    user_input: str,
    profile: str,
    session_id: str,
    conversation_history: list[dict],
    user_context: dict | None,
    lean: bool,
    console: Console,
) -> str:
    """Execute chat message with streaming Rich Live display.

    Returns the final answer text for history tracking.
    """
    executor = AgentExecutor()

    # State for live display
    current_step = 0
    current_tool: str | None = None
    tool_results: list[str] = []
    final_answer_tokens: list[str] = []
    status_message = "Thinking..."

    def build_display() -> Group:
        """Build Rich display group for current state."""
        elements = []

        # Status header
        elements.append(Text(f"📋 Step: {current_step}  |  {status_message}", style="dim"))

        # Current tool (if any)
        if current_tool:
            elements.append(Panel(
                Text(f"🔧 {current_tool}", style="yellow"),
                title="Current Tool",
                border_style="yellow",
            ))

        # Recent tool results (last 3 for chat)
        if tool_results:
            results_text = "\n".join(tool_results[-3:])
            elements.append(Panel(
                Text(results_text),
                title="Tool Results",
                border_style="green",
            ))

        # Streaming answer
        if final_answer_tokens:
            answer_text = "".join(final_answer_tokens)
            elements.append(Panel(
                Text(answer_text, style="white"),
                title="💬 Response",
                border_style="blue",
            ))

        return Group(*elements)

    with Live(build_display(), console=console, refresh_per_second=4) as live:
        async for update in executor.execute_mission_streaming(
            mission=user_input,
            profile=profile,
            session_id=session_id,
            conversation_history=conversation_history,
            user_context=user_context,
            use_lean_agent=lean,
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
                output = str(update.details.get("output", ""))[:80]
                tool_results.append(f"{success} {tool}: {output}")
                current_tool = None
                status_message = "Processing..."
                should_update = True

            elif event_type == "llm_token":
                # Tokens are accumulated but we let Rich Live auto-refresh
                # Don't force update on every token to avoid terminal spam
                if not current_tool:
                    token = update.details.get("content", "")
                    if token:
                        final_answer_tokens.append(token)
                        status_message = "Responding..."
                # No should_update = True here - Rich Live refreshes automatically

            elif event_type == "plan_updated":
                action = update.details.get("action", "updated")
                status_message = f"Plan {action}"
                should_update = True

            elif event_type == "final_answer":
                if not final_answer_tokens:
                    content = update.details.get("content", "")
                    if content:
                        final_answer_tokens.append(content)
                status_message = "Complete!"
                should_update = True

            elif event_type == "complete":
                status_message = "Complete!"
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

    # Return final text for history (no extra panel - already shown in streaming display)
    return "".join(final_answer_tokens) if final_answer_tokens else "No response"
