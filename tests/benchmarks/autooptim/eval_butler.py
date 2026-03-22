"""AutoOptim evaluator for Butler agent efficiency.

Runs efficiency benchmark missions and outputs JSON scores to stdout.
Also writes a detailed trace file for the proposer LLM.

Eval modes:
  - "quick"  : Baseline + Single Tool + Document Report (3 missions)
  - "full"   : All 4 missions including Multi-Step Tool Chain
  - "daily"  : Full + 5 daily assistant missions (parallelization, delegation, memory)
  - "memory" : Multi-turn memory & learning sequences (preference recall, fact retention, etc.)
  - "future" : Aspirational self-improvement missions (expected to fail today)
  - "all"    : Full + daily + memory + future

Output: JSON with aggregate scores + per-mission breakdowns + notification_spam count.
Sidecar: .autooptim/last_eval_trace.md with tool traces per mission.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

from taskforce.application.executor import AgentExecutor
from taskforce.application.token_analytics_facade import get_execution_token_summary
from taskforce.core.domain.enums import EventType

# ---------------------------------------------------------------------------
# Mission definitions: (display_name, score_prefix, prompt)
# ---------------------------------------------------------------------------

# --- Tier 1: Efficiency Baseline (existing) ---
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

# --- Tier 2: Daily Assistant (testable today) ---
DAILY_MISSIONS = [
    (
        "Tagesplanung",
        "tagesplan",
        "Was steht heute an? Schau in meinen Kalender und meine E-Mails "
        "und erstelle mir eine priorisierte Tagesuebersicht.",
    ),
    (
        "Dateiverwaltung",
        "datei",
        "Liste alle PDF-Dateien in meinem Downloads-Ordner auf und "
        "schlage vor, sie nach Documents/Rechnungen zu verschieben. "
        "Fuehre die Aktion aber NICHT aus ohne meine explizite Bestaetigung.",
    ),
    (
        "Recherche + Briefing",
        "recherche",
        "Was sind die wichtigsten Neuerungen bei Python 3.13? "
        "Recherchiere und schreib mir ein kurzes Briefing mit den "
        "Top-5 Features als Markdown-Liste.",
    ),
    (
        "Erinnerung setzen",
        "reminder",
        "Erinnere mich morgen um 9 Uhr an das Meeting mit Peter. "
        "Bestaetige mir danach, dass die Erinnerung gesetzt wurde.",
    ),
    (
        "Praeferenz merken",
        "praeferenz",
        "Ich mag Reports immer als Markdown-Tabelle formatiert. "
        "Merke dir das fuer die Zukunft.",
    ),
]

# --- Tier 3: Memory & Learning (multi-turn sequences) ---
# Each entry is a dict with a sequence of prompts. The final prompt is the "test"
# that checks whether the butler retained/applied the information from earlier steps.
MEMORY_MISSIONS: list[dict] = [
    {
        "name": "Preference Recall",
        "prefix": "mem_pref",
        "description": "Set a format preference, run filler missions, then test recall.",
        "sequence": [
            ("Setup", "Mein bevorzugtes Ausgabeformat ist immer CSV. Merke dir das."),
            ("Filler 1", "Wie spaet ist es gerade?"),
            ("Filler 2", "Wie heisst die aktuelle Python-Version?"),
            (
                "Test",
                "Exportiere eine Liste meiner naechsten 3 Termine. "
                "Nutze mein bevorzugtes Format.",
            ),
        ],
        "check": "csv",
    },
    {
        "name": "Fact Retention",
        "prefix": "mem_fact",
        "description": "Store a personal fact, then recall it later.",
        "sequence": [
            (
                "Setup",
                "Mein Steuerberater ist Herr Mueller, Tel 0664-1234567. "
                "Merke dir das bitte.",
            ),
            ("Filler", "Was steht in der Datei pyproject.toml?"),
            (
                "Test",
                "Wie heisst mein Steuerberater und was ist seine Telefonnummer?",
            ),
        ],
        "check": "mueller",
    },
    {
        "name": "Contradiction Handling",
        "prefix": "mem_contra",
        "description": "Set preference, update it, check if the update is used.",
        "sequence": [
            (
                "Setup 1",
                "Mein Lieblings-Reportformat ist CSV. Merke dir das.",
            ),
            (
                "Update",
                "Korrektur: Mein Lieblings-Reportformat ist eigentlich Excel, "
                "nicht CSV. Bitte update das.",
            ),
            (
                "Test",
                "Erstelle mir einen Report ueber die Dateien in meinem Documents-Ordner. "
                "Nutze mein Lieblingsformat.",
            ),
        ],
        "check_type": "llm_judge",
        "check_prompt": (
            "The user initially set their preferred report format to CSV, then "
            "corrected it to Excel. Does the assistant's final report use Excel "
            "format (not CSV)? Answer YES or NO."
        ),
    },
    {
        "name": "Memory Search",
        "prefix": "mem_search",
        "description": "Store multiple facts, then recall a specific one.",
        "sequence": [
            ("Setup 1", "Merke dir: Mein Projektleiter heisst Anna Schmidt."),
            ("Setup 2", "Merke dir: Unser Sprint endet jeden zweiten Freitag."),
            ("Setup 3", "Merke dir: Das Daily Standup ist um 9:15 Uhr."),
            ("Test", "Wann ist unser Daily Standup?"),
        ],
        "check": "9:15",
    },
    {
        "name": "Proactive Suggestion",
        "prefix": "mem_proactive",
        "description": "Repeat the same request 3x — does butler suggest automation?",
        "sequence": [
            ("Req 1", "Fasse meine E-Mails zusammen."),
            ("Req 2", "Fasse meine E-Mails zusammen."),
            ("Req 3", "Fasse meine E-Mails zusammen."),
        ],
        "check_type": "llm_judge",
        "check_prompt": (
            "The user asked the assistant to summarize emails three times in a row. "
            "Did the assistant at any point suggest automating, scheduling, or "
            "creating a rule for this repeated task? Answer YES or NO."
        ),
    },
]

# --- Tier 4: Future / Aspirational (expected to score 0 today) ---
# These missions test capabilities that Taskforce does not yet support.
# They serve as specifications for future features. AutoOptim can target
# them once the underlying features are implemented.
FUTURE_MISSIONS = [
    (
        "Agent Creation",
        "fut_agent",
        "Erstelle mir einen Reise-Planungs-Agenten mit Zugriff auf "
        "web_search, calendar und file_write. Er soll Reisen planen koennen. "
        "Registriere ihn so dass ich ihn in Zukunft mit 'reise-agent' aufrufen kann.",
    ),
    (
        "Tool Authoring",
        "fut_tool",
        "Bau mir ein Tool das CSV-Dateien lesen und als Markdown-Tabelle "
        "formatieren kann. Registriere es als 'csv_to_markdown' Tool "
        "so dass ich es in Zukunft nutzen kann.",
    ),
    (
        "Meta-Optimization",
        "fut_meta",
        "Der PC-Agent braucht zu viele Steps fuer einfache Dateioperationen. "
        "Analysiere seine letzten Ausfuehrungen und optimiere seinen System-Prompt "
        "so dass er effizienter arbeitet.",
    ),
    (
        "Pattern Learning",
        "fut_learn",
        "Analysiere meine letzten 10 Conversations und extrahiere Muster. "
        "Erstelle daraus Skills oder Rules die mir in Zukunft helfen.",
    ),
    (
        "Workflow Composition",
        "fut_workflow",
        "Wenn ich montags 'Wochenstart' sage, soll automatisch folgendes passieren: "
        "(1) Kalender der Woche anzeigen, (2) E-Mails zusammenfassen, "
        "(3) offene Tasks priorisieren. Erstelle dafuer eine Trigger-Rule.",
    ),
]

PROFILE = "butler"
TRACE_PATH = Path(".autooptim/last_eval_trace.md")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _count_tool_calls_before_delegation(tool_trace: list[dict]) -> int:
    """Count tool calls before the first sub-agent delegation.

    Returns the number of tool calls before the first ``call_agents_parallel``
    (or ``parallel_agent``) invocation. Lower is better — the butler should
    delegate quickly without unnecessary tool calls.
    Returns -1 if no delegation occurred.
    """
    delegation_tools = {"call_agents_parallel", "parallel_agent"}
    idx = 0
    for t in tool_trace:
        if t["type"] == "call":
            if t["tool"] in delegation_tools:
                return idx
            idx += 1
    return -1


# ---------------------------------------------------------------------------
# LLM-as-Judge for quality grading
# ---------------------------------------------------------------------------


async def _llm_judge(answer: str, question: str) -> bool:
    """Use LLM to grade an answer with a yes/no question. Returns True if passes."""
    try:
        from taskforce.infrastructure.llm.litellm_service import LiteLLMService

        llm = LiteLLMService()
        result = await llm.complete_json(
            prompt=(
                f"## Answer to evaluate\n{answer[:500]}\n\n"
                f"## Question\n{question}\n\n"
                "Respond with a JSON object: {\"pass\": true} or {\"pass\": false}"
            ),
            system_prompt=(
                "You are a strict evaluator. Only respond with valid JSON. "
                "Evaluate objectively based on the content of the answer."
            ),
            model="fast",
        )
        return bool(result.get("pass", False))
    except Exception as e:
        print(f"  [LLM judge error: {e}]", file=sys.stderr)
        return False


async def _llm_quality_grade(answer: str, mission: str) -> float:
    """LLM-graded answer quality on a 0.0-1.0 scale.

    Evaluates correctness, completeness, and formatting.
    """
    try:
        from taskforce.infrastructure.llm.litellm_service import LiteLLMService

        llm = LiteLLMService()
        result = await llm.complete_json(
            prompt=(
                f"## Mission\n{mission[:300]}\n\n"
                f"## Agent Answer\n{answer[:500]}\n\n"
                "Rate the answer quality on a scale from 0.0 to 1.0:\n"
                "- 1.0 = correct, complete, well-formatted\n"
                "- 0.7 = mostly correct but missing minor details\n"
                "- 0.4 = partially correct or poorly formatted\n"
                "- 0.0 = wrong, empty, or completely off-topic\n\n"
                'Respond with JSON: {"quality": 0.X, "reason": "..."}'
            ),
            system_prompt="You are a strict answer quality evaluator. Respond only with JSON.",
            model="fast",
        )
        score = float(result.get("quality", 0.0))
        return max(0.0, min(1.0, score))
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Mission runners
# ---------------------------------------------------------------------------


async def run_mission(
    name: str, prefix: str, mission: str, executor: AgentExecutor,
    session_id: str | None = None,
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
        session_id=session_id,
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

    delegation_steps = _count_tool_calls_before_delegation(tool_trace)

    result = {
        "name": name,
        "prefix": prefix,
        "wall_seconds": wall_seconds,
        "completed": bool(final_answer) and not had_error,
        "final_answer": final_answer[:300],
        "tool_trace": tool_trace,
        "errors": errors,
        "notification_count": notification_count,
        "delegation_steps": delegation_steps,
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


async def run_memory_sequence(
    seq: dict, executor: AgentExecutor
) -> dict:
    """Run a multi-turn memory sequence and check the final answer.

    All steps in the sequence share the same executor (and thus the same
    session/memory state). Only the final "test" step is scored.
    """
    steps = seq["sequence"]
    prefix = seq["prefix"]
    all_results: list[dict] = []

    # All steps in a memory sequence share the same session so that
    # memory written in early turns is visible in later turns.
    shared_session_id = f"bench-mem-{prefix}-{uuid.uuid4().hex[:8]}"

    for step_name, prompt in steps:
        r = await run_mission(
            f"{seq['name']}/{step_name}", prefix, prompt, executor,
            session_id=shared_session_id,
        )
        all_results.append(r)
        print(
            f"    [{seq['name']}/{step_name}] steps={r['steps']} "
            f"ok={r['completed']}",
            file=sys.stderr,
        )

    last = all_results[-1]

    # Check memory recall
    if seq.get("check_type") == "llm_judge":
        # Concatenate all final answers for the judge to evaluate
        all_answers = "\n---\n".join(
            f"Turn {i + 1}: {r['final_answer']}"
            for i, r in enumerate(all_results)
            if r["final_answer"]
        )
        recall_ok = await _llm_judge(all_answers, seq["check_prompt"])
    else:
        check_str = seq["check"].lower()
        recall_ok = check_str in last.get("final_answer", "").lower()

    # Aggregate metrics across the sequence
    total_steps = sum(r["steps"] for r in all_results)
    total_tokens = sum(r["input_tokens"] for r in all_results)
    total_tools = sum(r["tool_calls"] for r in all_results)
    total_wall = sum(r["wall_seconds"] for r in all_results)
    total_notif = sum(r["notification_count"] for r in all_results)
    all_completed = all(r["completed"] for r in all_results)

    # Merge tool traces from all steps
    merged_trace: list[dict] = []
    for i, r in enumerate(all_results):
        step_name = steps[i][0]
        merged_trace.append({"type": "step_marker", "tool": f"--- {step_name} ---", "args": ""})
        merged_trace.extend(r.get("tool_trace", []))

    return {
        "name": seq["name"],
        "prefix": prefix,
        "wall_seconds": total_wall,
        "completed": all_completed,
        "final_answer": last.get("final_answer", "")[:300],
        "tool_trace": merged_trace,
        "errors": [e for r in all_results for e in r["errors"]],
        "notification_count": total_notif,
        "delegation_steps": last.get("delegation_steps", -1),
        "steps": total_steps,
        "input_tokens": total_tokens,
        "output_tokens": sum(r["output_tokens"] for r in all_results),
        "tool_calls": total_tools,
        "ratio": round(total_tokens / max(1, sum(r["output_tokens"] for r in all_results)), 1),
        "latency_ms": sum(r.get("latency_ms", 0) for r in all_results),
        # Memory-specific metrics
        "memory_recall": 1.0 if recall_ok else 0.0,
        "sequence_turns": len(all_results),
    }


# ---------------------------------------------------------------------------
# Trace writer
# ---------------------------------------------------------------------------


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

        # Memory recall (if present)
        if "memory_recall" in r:
            recall_tag = "PASS" if r["memory_recall"] > 0 else "FAIL"
            lines.append(
                f"Memory Recall: {recall_tag} | Turns: {r.get('sequence_turns', '?')}"
            )

        # Delegation efficiency
        ds = r.get("delegation_steps", -1)
        if ds >= 0:
            lines.append(f"Delegation after {ds} tool calls")

        if r["errors"]:
            lines.append(f"ERRORS: {'; '.join(r['errors'])}")

        if r["notification_count"] > 2:
            lines.append(
                f"WARNING: Notification spam detected ({r['notification_count']} calls)"
            )

        # Tool trace
        lines.append("\nTool trace:")
        for t in r.get("tool_trace", []):
            if t["type"] == "step_marker":
                lines.append(f"\n  {t['tool']}")
            elif t["type"] == "call":
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


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def compute_scores(results: list[dict], memory_results: list[dict]) -> dict[str, float]:
    """Compute aggregate and per-mission scores from all results."""
    all_results = results + memory_results
    n = len(all_results)
    if n == 0:
        return {"task_completion": 0.0}

    completed = sum(1 for r in all_results if r["completed"])
    total_steps = sum(r["steps"] for r in all_results)
    total_input = sum(r["input_tokens"] for r in all_results)
    total_tools = sum(r["tool_calls"] for r in all_results)
    total_wall = sum(r["wall_seconds"] for r in all_results)
    avg_ratio = sum(r["ratio"] for r in all_results) / n
    total_notifications = sum(r["notification_count"] for r in all_results)

    scores: dict[str, float] = {
        "task_completion": completed / n,
        "avg_steps": total_steps / n,
        "avg_input_tokens": total_input / n,
        "avg_ratio": avg_ratio,
        "avg_wall_seconds": total_wall / n,
        "total_tool_calls": float(total_tools),
        "efficiency_tokens": float(total_input),
        "notification_spam": float(total_notifications),
    }

    # Delegation efficiency (avg steps to first delegation, excluding missions
    # that don't delegate)
    delegation_vals = [r["delegation_steps"] for r in all_results if r.get("delegation_steps", -1) >= 0]
    if delegation_vals:
        scores["delegation_efficiency"] = sum(delegation_vals) / len(delegation_vals)

    # Memory recall (aggregate across memory sequences)
    if memory_results:
        recall_vals = [r["memory_recall"] for r in memory_results if "memory_recall" in r]
        if recall_vals:
            scores["memory_recall"] = sum(recall_vals) / len(recall_vals)

    # Answer quality (aggregate from per-mission LLM grading)
    quality_vals = [r["answer_quality"] for r in all_results if "answer_quality" in r]
    if quality_vals:
        scores["answer_quality"] = sum(quality_vals) / len(quality_vals)

    # Self-improvement score (future missions that actually completed)
    future_results = [r for r in results if r["prefix"].startswith("fut_")]
    if future_results:
        scores["self_improvement_score"] = (
            sum(1 for r in future_results if r["completed"]) / len(future_results)
        )

    # Per-mission scores
    for r in results:
        p = r["prefix"]
        scores[f"{p}_steps"] = float(r["steps"])
        scores[f"{p}_tokens"] = float(r["input_tokens"])
        scores[f"{p}_wall"] = round(r["wall_seconds"], 1)
        scores[f"{p}_tools"] = float(r["tool_calls"])
        scores[f"{p}_completed"] = 1.0 if r["completed"] else 0.0
        if "answer_quality" in r:
            scores[f"{p}_quality"] = r["answer_quality"]

    for r in memory_results:
        p = r["prefix"]
        scores[f"{p}_completed"] = 1.0 if r["completed"] else 0.0
        scores[f"{p}_recall"] = r.get("memory_recall", 0.0)
        scores[f"{p}_steps"] = float(r["steps"])
        scores[f"{p}_tokens"] = float(r["input_tokens"])
        scores[f"{p}_wall"] = round(r["wall_seconds"], 1)

    return scores


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main(task_name: str) -> None:
    """Run benchmark missions and output JSON scores.

    Supported modes:
      quick   - 3 baseline efficiency missions
      full    - 4 efficiency missions (quick + multi-step)
      daily   - full + 5 daily assistant missions
      memory  - 5 multi-turn memory & learning sequences
      future  - 5 aspirational self-improvement missions
      all     - full + daily + memory + future
    """
    # Build mission lists based on mode
    standard_missions: list[tuple[str, str, str]] = []
    run_memory = False

    if task_name == "quick":
        standard_missions = list(QUICK_MISSIONS)
    elif task_name == "full":
        standard_missions = list(FULL_MISSIONS)
    elif task_name == "daily":
        standard_missions = list(FULL_MISSIONS) + list(DAILY_MISSIONS)
    elif task_name == "memory":
        run_memory = True
    elif task_name == "future":
        standard_missions = list(FUTURE_MISSIONS)
    elif task_name == "all":
        standard_missions = (
            list(FULL_MISSIONS) + list(DAILY_MISSIONS) + list(FUTURE_MISSIONS)
        )
        run_memory = True
    else:
        print(
            f"Unknown mode: {task_name}. Use: quick|full|daily|memory|future|all",
            file=sys.stderr,
        )
        standard_missions = list(QUICK_MISSIONS)

    executor = AgentExecutor()
    results: list[dict] = []
    memory_results: list[dict] = []

    # Run standard (single-turn) missions
    for name, prefix, mission_text in standard_missions:
        r = await run_mission(name, prefix, mission_text, executor)
        results.append(r)
        print(
            f"  [{r['name']}] steps={r['steps']} in={r['input_tokens']:,} "
            f"tools={r['tool_calls']} notif={r['notification_count']} "
            f"wall={r['wall_seconds']:.1f}s ok={r['completed']}",
            file=sys.stderr,
        )

    # Run multi-turn memory sequences
    if run_memory:
        print("\n  --- Memory & Learning Sequences ---", file=sys.stderr)
        for seq in MEMORY_MISSIONS:
            seq_executor = AgentExecutor()  # Fresh executor per sequence for isolation
            r = await run_memory_sequence(seq, seq_executor)
            memory_results.append(r)
            recall_tag = "PASS" if r["memory_recall"] > 0 else "FAIL"
            print(
                f"  [{r['name']}] recall={recall_tag} steps={r['steps']} "
                f"tokens={r['input_tokens']:,} turns={r['sequence_turns']} "
                f"wall={r['wall_seconds']:.1f}s ok={r['completed']}",
                file=sys.stderr,
            )

    # Write trace file for proposer context
    write_trace(results + memory_results, task_name)

    # Grade answer quality for daily missions via LLM judge (BEFORE compute_scores
    # so that answer_quality values are available for scoring).
    daily_results = [r for r in results if r["prefix"] in {
        "tagesplan", "datei", "recherche", "reminder", "praeferenz",
    }]
    if daily_results:
        for r in daily_results:
            mission_prompt = ""
            for name, prefix, prompt in DAILY_MISSIONS:
                if prefix == r["prefix"]:
                    mission_prompt = prompt
                    break
            if r["final_answer"] and mission_prompt:
                r["answer_quality"] = await _llm_quality_grade(
                    r["final_answer"], mission_prompt
                )

    # Compute and output scores
    scores = compute_scores(results, memory_results)

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
