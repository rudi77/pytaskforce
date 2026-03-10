"""Taskforce Agent Bridge for Inspect AI.

Wraps the Taskforce AgentExecutor as an Inspect AI solver,
enabling evaluation of Taskforce agents against standardized benchmarks.
"""

import logging
import tempfile
from typing import Any

from inspect_ai.solver import Solver, TaskState, solver

logger = logging.getLogger(__name__)


@solver
def taskforce_solver(
    profile: str = "coding_agent",
    max_steps: int | None = None,
    planning_strategy: str | None = None,
    work_dir: str | None = None,
) -> Solver:
    """Inspect AI solver that delegates to a Taskforce agent.

    Uses execute_mission_streaming to capture fine-grained execution
    metrics (steps, tool calls, token usage) that the non-streaming
    path discards.

    Args:
        profile: Taskforce profile name (e.g. "coding_agent", "dev").
        max_steps: Override max execution steps (None = use profile default).
        planning_strategy: Override planning strategy (None = use profile default).
        work_dir: Working directory for agent persistence. Defaults to a temp dir.
    """

    async def solve(state: TaskState, generate: Any) -> TaskState:
        from taskforce.application.executor import AgentExecutor
        from taskforce.application.factory import AgentFactory
        from taskforce.core.domain.enums import EventType

        # Extract the user prompt from the conversation
        prompt = state.input_text

        factory = AgentFactory()
        executor = AgentExecutor(factory)

        # Accumulators for streaming events
        tool_calls = 0
        tool_results = 0
        total_steps = 0
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        final_message = ""
        status = "unknown"
        session_id = ""
        history_types: list[str] = []

        try:
            async for update in executor.execute_mission_streaming(
                mission=prompt,
                profile=profile,
                planning_strategy=planning_strategy,
                planning_strategy_params=None,
            ):
                evt = update.event_type

                # Normalize event type to string for comparison
                evt_str = evt.value if isinstance(evt, EventType) else str(evt)
                history_types.append(evt_str)

                if evt_str == EventType.TOOL_CALL.value:
                    tool_calls += 1
                elif evt_str == EventType.TOOL_RESULT.value:
                    tool_results += 1
                elif evt_str == EventType.TOKEN_USAGE.value:
                    usage = update.details or {}
                    prompt_tokens += usage.get("prompt_tokens", 0)
                    completion_tokens += usage.get("completion_tokens", 0)
                    total_tokens += usage.get("total_tokens", 0)
                elif evt_str == EventType.FINAL_ANSWER.value:
                    content = (update.details or {}).get("content", "")
                    if content:
                        final_message = str(content).strip()
                elif evt_str == EventType.COMPLETE.value:
                    details = update.details or {}
                    status = details.get("status", "completed")
                    session_id = details.get("session_id", "")
                    # Fall back to complete message if no final_answer was seen
                    if not final_message:
                        msg = details.get("final_message") or update.message or ""
                        final_message = str(msg).strip()

                # Count all non-meta events as steps
                step_events = {
                    EventType.TOOL_CALL.value,
                    EventType.TOOL_RESULT.value,
                    EventType.PLAN_UPDATED.value,
                    EventType.ASK_USER.value,
                }
                if evt_str in step_events:
                    total_steps += 1

        except Exception as e:
            logger.error(f"Taskforce agent execution failed: {e}")
            state.metadata = state.metadata or {}
            state.metadata["taskforce_status"] = "error"
            state.metadata["taskforce_error"] = str(e)
            state.metadata["taskforce_token_usage"] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
            state.metadata["taskforce_steps"] = 0
            state.metadata["taskforce_tool_calls"] = 0
            return state

        # Write the agent's final response back into Inspect state
        state.output = state.output.model_copy(
            update={"completion": final_message}
        )

        # Store execution metadata for custom scorers
        state.metadata = state.metadata or {}
        state.metadata["taskforce_status"] = str(status)
        state.metadata["taskforce_session_id"] = session_id
        state.metadata["taskforce_token_usage"] = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }
        state.metadata["taskforce_steps"] = total_steps
        state.metadata["taskforce_tool_calls"] = tool_calls

        return state

    return solve
