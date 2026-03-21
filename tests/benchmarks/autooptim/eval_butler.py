"""AutoOptim evaluator for Butler agent efficiency.

Runs the efficiency benchmark missions and outputs JSON scores to stdout.
Supports two eval modes via command-line argument:
  - "quick"  : runs only Minimal + Single Tool missions (faster iteration)
  - "full"   : runs all three missions

Output format (JSON on last line):
{
  "task_completion": 0.0-1.0,    # fraction of missions that produced an answer
  "avg_steps": <float>,          # average steps across missions (lower = better)
  "avg_input_tokens": <float>,   # average prompt tokens (lower = better)
  "avg_ratio": <float>,          # average input:output ratio (lower = better)
  "avg_wall_seconds": <float>,   # average wall-clock time (lower = better)
  "total_tool_calls": <float>,   # total tool calls across missions (lower = better)
  "efficiency_tokens": <float>,  # total input tokens (for cost estimation)
}
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

from taskforce.application.factory import AgentFactory
from taskforce.application.executor import AgentExecutor
from taskforce.application.token_analytics_facade import get_execution_token_summary
from taskforce.core.domain.enums import EventType

# Quick missions: fast iteration (baseline + one delegation task)
QUICK_MISSIONS = [
    (
        "Minimal (Baseline)",
        "Wie spaet ist es gerade? Antworte in einem Satz.",
    ),
    (
        "Single Tool",
        "Lies die Datei pyproject.toml mit PowerShell und nenne mir die "
        "aktuelle Version von taskforce. Antworte in einem Satz.",
    ),
]

# Full missions: comprehensive evaluation
FULL_MISSIONS = QUICK_MISSIONS + [
    (
        "Multi-Step Tool Chain",
        "Check meine letzten 3 E-Mails und fasse jede in einem Satz zusammen.",
    ),
]

PROFILE = "butler"


async def run_mission(name: str, mission: str, executor: AgentExecutor) -> dict:
    """Run a single mission and return metrics."""
    # Drain leftover analytics
    get_execution_token_summary()

    wall_start = time.monotonic()
    final_answer = ""
    had_error = False

    async for update in executor.execute_mission_streaming(
        mission=mission,
        profile=PROFILE,
    ):
        event = update.event_type
        if event == EventType.FINAL_ANSWER.value:
            final_answer = update.details.get("content", "")
        elif event == EventType.ERROR.value:
            had_error = True

    wall_seconds = time.monotonic() - wall_start
    summary = get_execution_token_summary()

    result = {
        "name": name,
        "wall_seconds": wall_seconds,
        "completed": bool(final_answer) and not had_error,
    }

    if summary:
        result.update({
            "steps": len(summary.step_breakdown),
            "input_tokens": summary.total_prompt_tokens,
            "output_tokens": summary.total_completion_tokens,
            "tool_calls": sum(len(s.tool_call_names) for s in summary.step_breakdown),
            "ratio": round(summary.prompt_to_completion_ratio, 1),
            "latency_ms": summary.total_latency_ms,
        })
    else:
        result.update({
            "steps": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "tool_calls": 0,
            "ratio": 0.0,
            "latency_ms": 0,
        })

    return result


async def main(task_name: str) -> None:
    """Run benchmark missions and output JSON scores."""
    missions = FULL_MISSIONS if task_name == "full" else QUICK_MISSIONS

    executor = AgentExecutor()
    results = []

    for name, mission_text in missions:
        r = await run_mission(name, mission_text, executor)
        results.append(r)
        # Log progress to stderr (not captured by score parser)
        print(f"  [{r['name']}] steps={r['steps']} in={r['input_tokens']:,} "
              f"tools={r['tool_calls']} wall={r['wall_seconds']:.1f}s "
              f"ok={r['completed']}", file=sys.stderr)

    # Compute aggregate scores
    n = len(results)
    completed = sum(1 for r in results if r["completed"])
    total_steps = sum(r["steps"] for r in results)
    total_input = sum(r["input_tokens"] for r in results)
    total_tools = sum(r["tool_calls"] for r in results)
    total_wall = sum(r["wall_seconds"] for r in results)
    avg_ratio = sum(r["ratio"] for r in results) / n if n else 0

    scores = {
        "task_completion": completed / n if n else 0.0,
        "avg_steps": total_steps / n if n else 0.0,
        "avg_input_tokens": total_input / n if n else 0.0,
        "avg_ratio": avg_ratio,
        "avg_wall_seconds": total_wall / n if n else 0.0,
        "total_tool_calls": float(total_tools),
        "efficiency_tokens": float(total_input),
    }

    # Output JSON on stdout (last line — picked up by AutoOptim's JsonScoreParser)
    print(json.dumps(scores))


if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "quick"
    asyncio.run(main(task))
