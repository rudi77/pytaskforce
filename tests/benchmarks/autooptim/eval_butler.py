"""AutoOptim evaluator for Butler agent efficiency.

Runs efficiency benchmark missions and outputs JSON scores to stdout.
Also writes a detailed trace file for the proposer LLM.

Eval modes:
  - "quick"  : Baseline + Single Tool + Document Report (3 missions)
  - "full"   : All 4 missions including Multi-Step Tool Chain

Output: JSON with aggregate scores + per-mission breakdowns + notification_spam count.
Sidecar: .autooptim/last_eval_trace.md with tool traces per mission.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

from taskforce.application.executor import AgentExecutor
from taskforce.application.token_analytics_facade import get_execution_token_summary
from taskforce.core.domain.enums import EventType

# Mission definitions: (display_name, score_prefix, prompt)
QUICK_MISSIONS = [
    (
        "Minimal (Baseline)",
        "baseline",
        "Wie spaet ist es gerade? Antworte in einem Satz.",
    ),
    (
        "Single Tool",
        "singletool",
        "Lies die Datei pyproject.toml mit PowerShell und nenne mir die "
        "aktuelle Version von taskforce. Antworte in einem Satz.",
    ),
    (
        "Document Report",
        "docreport",
        "Welche Dokumente gibt es in meinem privaten Documents Ordner. "
        "Schau dir die Dokumente an, kategorisiere sie und liefere mir "
        "einen kurzen Report dazu.",
    ),
]

FULL_MISSIONS = QUICK_MISSIONS + [
    (
        "Multi-Step Tool Chain",
        "multistep",
        "Check meine letzten 3 E-Mails und fasse jede in einem Satz zusammen.",
    ),
]

PROFILE = "butler"
TRACE_PATH = Path(".autooptim/last_eval_trace.md")


def _summarize_args(args: dict) -> str:
    """One-line summary of tool call arguments (max 120 chars)."""
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        if k.startswith("_"):
            continue
        s = str(v)
        if len(s) > 60:
            s = s[:57] + "..."
        parts.append(f"{k}={s}")
    result = ", ".join(parts)
    return result[:120]


async def run_mission(
    name: str, prefix: str, mission: str, executor: AgentExecutor
) -> dict:
    """Run a single mission and return metrics + tool trace."""
    # Drain leftover analytics
    get_execution_token_summary()

    wall_start = time.monotonic()
    final_answer = ""
    had_error = False
    tool_trace: list[dict] = []
    errors: list[str] = []
    notification_count = 0

    async for update in executor.execute_mission_streaming(
        mission=mission,
        profile=PROFILE,
    ):
        event = update.event_type
        details = update.details or {}

        if event == EventType.TOOL_CALL.value:
            tool_name = details.get("tool", "")
            tool_trace.append({
                "type": "call",
                "tool": tool_name,
                "args": _summarize_args(details.get("args", {})),
            })
            if tool_name == "send_notification":
                notification_count += 1

        elif event == EventType.TOOL_RESULT.value:
            tool_trace.append({
                "type": "result",
                "tool": details.get("tool", ""),
                "success": details.get("success", False),
                "preview": str(details.get("output", ""))[:100],
            })

        elif event == EventType.FINAL_ANSWER.value:
            final_answer = details.get("content", "")

        elif event == EventType.ERROR.value:
            had_error = True
            errors.append(str(details.get("message", details))[:200])

    wall_seconds = time.monotonic() - wall_start
    summary = get_execution_token_summary()

    result = {
        "name": name,
        "prefix": prefix,
        "wall_seconds": wall_seconds,
        "completed": bool(final_answer) and not had_error,
        "final_answer": final_answer[:300],
        "tool_trace": tool_trace,
        "errors": errors,
        "notification_count": notification_count,
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


def write_trace(results: list[dict], mode: str) -> None:
    """Write detailed trace file for the proposer LLM."""
    TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# Last Eval Trace (mode: {mode}, {len(results)} missions)\n"]

    for r in results:
        status = "OK" if r["completed"] else "FAILED"
        lines.append(f"## {r['name']} [{status}]")
        lines.append(
            f"Steps: {r['steps']} | Tokens: {r['input_tokens']:,} | "
            f"Wall: {r['wall_seconds']:.1f}s | Tools: {r['tool_calls']} | "
            f"Notifications: {r['notification_count']}"
        )

        if r["errors"]:
            lines.append(f"ERRORS: {'; '.join(r['errors'])}")

        if r["notification_count"] > 2:
            lines.append(
                f"WARNING: Notification spam detected ({r['notification_count']} calls)"
            )

        # Tool trace
        lines.append("\nTool trace:")
        for t in r.get("tool_trace", []):
            if t["type"] == "call":
                lines.append(f"  -> {t['tool']}({t['args']})")
            else:
                tag = "OK" if t["success"] else "FAIL"
                lines.append(f"  <- {tag} {t['tool']}: {t['preview']}")

        # Final answer
        answer = r.get("final_answer", "")
        if answer:
            lines.append(f"\nAnswer: {answer[:200]}")
        else:
            lines.append("\nAnswer: (none - mission did not produce a final answer)")

        lines.append("")

    TRACE_PATH.write_text("\n".join(lines), encoding="utf-8")


async def main(task_name: str) -> None:
    """Run benchmark missions and output JSON scores."""
    missions = FULL_MISSIONS if task_name == "full" else QUICK_MISSIONS

    executor = AgentExecutor()
    results = []

    for name, prefix, mission_text in missions:
        r = await run_mission(name, prefix, mission_text, executor)
        results.append(r)
        print(
            f"  [{r['name']}] steps={r['steps']} in={r['input_tokens']:,} "
            f"tools={r['tool_calls']} notif={r['notification_count']} "
            f"wall={r['wall_seconds']:.1f}s ok={r['completed']}",
            file=sys.stderr,
        )

    # Write trace file for proposer context
    write_trace(results, task_name)

    # Compute aggregate scores
    n = len(results)
    completed = sum(1 for r in results if r["completed"])
    total_steps = sum(r["steps"] for r in results)
    total_input = sum(r["input_tokens"] for r in results)
    total_tools = sum(r["tool_calls"] for r in results)
    total_wall = sum(r["wall_seconds"] for r in results)
    avg_ratio = sum(r["ratio"] for r in results) / n if n else 0
    total_notifications = sum(r["notification_count"] for r in results)

    scores: dict[str, float] = {
        "task_completion": completed / n if n else 0.0,
        "avg_steps": total_steps / n if n else 0.0,
        "avg_input_tokens": total_input / n if n else 0.0,
        "avg_ratio": avg_ratio,
        "avg_wall_seconds": total_wall / n if n else 0.0,
        "total_tool_calls": float(total_tools),
        "efficiency_tokens": float(total_input),
        "notification_spam": float(total_notifications),
    }

    # Per-mission scores
    for r in results:
        p = r["prefix"]
        scores[f"{p}_steps"] = float(r["steps"])
        scores[f"{p}_tokens"] = float(r["input_tokens"])
        scores[f"{p}_wall"] = round(r["wall_seconds"], 1)
        scores[f"{p}_tools"] = float(r["tool_calls"])
        scores[f"{p}_completed"] = 1.0 if r["completed"] else 0.0

    # Output JSON on stdout
    print(json.dumps(scores), flush=True)
    sys.stdout.flush()


if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "quick"
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(main(task))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
    finally:
        try:
            loop.close()
        except Exception:
            pass
        os._exit(0)
