"""Custom scorers for Taskforce agent evaluation.

Provides scoring functions that assess:
- Task completion (did the agent finish successfully?)
- Output quality (model-graded assessment)
- Efficiency (steps and token usage)
"""

from inspect_ai.scorer import (
    CORRECT,
    INCORRECT,
    Score,
    Target,
    accuracy,
    mean,
    scorer,
    stderr,
)
from inspect_ai.solver import TaskState


@scorer(metrics=[accuracy(), stderr()])
def task_completion():
    """Score based on whether the Taskforce agent completed successfully."""

    async def score(state: TaskState, target: Target) -> Score:
        metadata = state.metadata or {}
        status = metadata.get("taskforce_status", "unknown")
        # Handle both string and enum representations
        completed = any(
            s in status.lower() for s in ("completed", "complete")
        )

        return Score(
            value=CORRECT if completed else INCORRECT,
            answer=state.output.completion[:500] if state.output else "",
            explanation=f"Agent status: {status}",
        )

    return score


@scorer(
    metrics={
        "steps": [mean()],
        "tool_calls": [mean()],
        "total_tokens": [mean()],
        "prompt_tokens": [mean()],
        "completion_tokens": [mean()],
    }
)
def efficiency():
    """Score execution efficiency (steps, tool calls, and token usage)."""

    async def score(state: TaskState, target: Target) -> Score:
        metadata = state.metadata or {}
        steps = metadata.get("taskforce_steps", 0)
        tool_calls = metadata.get("taskforce_tool_calls", 0)
        token_usage = metadata.get("taskforce_token_usage", {})
        prompt_tokens = token_usage.get("prompt_tokens", 0)
        completion_tokens = token_usage.get("completion_tokens", 0)
        total_tokens = token_usage.get("total_tokens", 0)

        return Score(
            value={
                "steps": steps,
                "tool_calls": tool_calls,
                "total_tokens": total_tokens,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
            answer=f"Steps: {steps}, Tool calls: {tool_calls}, Tokens: {total_tokens}",
            explanation=(
                f"Agent used {steps} history events, {tool_calls} tool calls, "
                f"{total_tokens} total tokens "
                f"({prompt_tokens} prompt + {completion_tokens} completion)"
            ),
        )

    return score


@scorer(metrics=[accuracy(), stderr()])
def output_contains_target(ignore_case: bool = True):
    """Score whether the agent output contains the expected target string."""

    async def score(state: TaskState, target: Target) -> Score:
        answer = state.output.completion if state.output else ""
        target_text = target.text

        if ignore_case:
            found = target_text.lower() in answer.lower()
        else:
            found = target_text in answer

        return Score(
            value=CORRECT if found else INCORRECT,
            answer=answer[:500],
            explanation=f"Target '{target_text}' {'found' if found else 'not found'} in output",
        )

    return score
