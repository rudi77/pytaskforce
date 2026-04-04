"""Run the three efficiency benchmark missions and collect token analytics."""

from __future__ import annotations

import asyncio
import time

from taskforce.application.factory import AgentFactory
from taskforce.application.executor import AgentExecutor
from taskforce.application.token_analytics_facade import get_execution_token_summary
from taskforce.core.domain.enums import EventType

MISSIONS = [
    (
        "Minimal (Baseline)",
        "Wie spaet ist es gerade? Antworte in einem Satz.",
    ),
    (
        "Single Tool",
        "Lies die Datei pyproject.toml mit PowerShell und nenne mir die "
        "aktuelle Version von taskforce. Antworte in einem Satz.",
    ),
    (
        "Multi-Step Tool Chain",
        "Check meine letzten 3 E-Mails und fasse jede in einem Satz zusammen.",
    ),
]

PROFILE = "butler"


async def run_mission(name: str, mission: str, executor: AgentExecutor) -> dict:
    """Run a single mission and return analytics."""
    # Drain any leftover analytics from previous run
    get_execution_token_summary()

    print(f"\n{'=' * 60}")
    print(f"  {name}")
    print(f"{'=' * 60}")

    wall_start = time.monotonic()
    final_answer = ""

    async for update in executor.execute_mission_streaming(
        mission=mission,
        profile=PROFILE,
    ):
        event = update.event_type
        if event == EventType.STEP_START.value:
            step = update.details.get("step", "?")
            print(f"  Step {step}...")
        elif event == EventType.TOOL_CALL.value:
            tool = update.details.get("tool", "?")
            print(f"    -> {tool}")
        elif event == EventType.FINAL_ANSWER.value:
            final_answer = update.details.get("content", "")
        elif event == EventType.ERROR.value:
            print(f"  ERROR: {update.message}")

    wall_ms = int((time.monotonic() - wall_start) * 1000)
    summary = get_execution_token_summary()

    result = {
        "name": name,
        "wall_ms": wall_ms,
        "answer_len": len(final_answer),
    }

    if summary:
        result.update(
            {
                "steps": len(summary.step_breakdown),
                "total_in": summary.total_prompt_tokens,
                "total_out": summary.total_completion_tokens,
                "tool_calls": sum(
                    len(s.tool_call_names) for s in summary.step_breakdown
                ),
                "llm_calls": summary.total_llm_calls,
                "latency_ms": summary.total_latency_ms,
                "ratio": round(summary.prompt_to_completion_ratio, 1),
            }
        )

        print(f"\n  Steps: {result['steps']}  |  "
              f"In: {result['total_in']:,}  |  Out: {result['total_out']:,}  |  "
              f"Tools: {result['tool_calls']}  |  "
              f"Ratio: {result['ratio']}x  |  "
              f"LLM: {result['latency_ms'] / 1000:.1f}s  |  "
              f"Wall: {wall_ms / 1000:.1f}s")
    else:
        print("  (no token analytics collected)")

    return result


async def main() -> None:
    executor = AgentExecutor()
    results = []

    for name, mission in MISSIONS:
        r = await run_mission(name, mission, executor)
        results.append(r)

    # Summary table
    print(f"\n\n{'=' * 60}")
    print("  BENCHMARK SUMMARY")
    print(f"{'=' * 60}")
    print(f"  {'Mission':<25} {'Steps':>5} {'In':>8} {'Out':>6} "
          f"{'Tools':>5} {'Ratio':>6} {'LLM':>6} {'Wall':>6}")
    print(f"  {'-' * 25} {'-' * 5} {'-' * 8} {'-' * 6} "
          f"{'-' * 5} {'-' * 6} {'-' * 6} {'-' * 6}")

    for r in results:
        if "steps" in r:
            print(
                f"  {r['name']:<25} {r['steps']:>5} "
                f"{r['total_in']:>8,} {r['total_out']:>6,} "
                f"{r['tool_calls']:>5} {r['ratio']:>5.1f}x "
                f"{r['latency_ms'] / 1000:>5.1f}s "
                f"{r['wall_ms'] / 1000:>5.1f}s"
            )
        else:
            print(f"  {r['name']:<25}  (failed)")


if __name__ == "__main__":
    asyncio.run(main())
