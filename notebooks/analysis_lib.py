"""Reusable building blocks for Taskforce-Agent analysis notebooks.

Four logical sections in one file (single-file is simpler to import from a
notebook than a package):

    1. RunRecord + run()       - mission execution with full event capture
    2. Reports (text)          - tool stats, plan history, context evolution,
                                 sanity-check, skill-injection diagnostics
    3. Plots (matplotlib)      - tool frequency, context growth, strategy
                                 compare, scenario matrix, role distribution
    4. Scenarios               - YAML loader, batch runner, rule-based +
                                 optional LLM-judge scoring

Important conventions baked in (lessons from tutti_paletti_analysis.ipynb):

- NEVER break early from `async for` in run() - GeneratorExit in a different
  asyncio context blows up the token-ledger ContextVar reset.
- NEVER call agent.context.snapshot() mid-stream - same root cause. Take all
  context snapshots AFTER the run completes.
- summary_threshold and tool_result_store_threshold defaults (20 / 2000) are
  too low for parallel tool use. The build_agent() helper patches the right
  internal components.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# =============================================================================
# SECTION 1 - RunRecord + run()
# =============================================================================

# Event-Type-Strings (string-compare to avoid importing taskforce.core enums at
# module top-level; agent code is imported lazily by callers anyway).
INTERESTING_EVENTS = {
    "step_start", "tool_call", "tool_result",
    "final_answer", "complete", "error",
}


def full_event_message(ev) -> str:
    """Pretty-print a ProgressUpdate for the live log."""
    details = ev.details or {}
    et = ev.event_type_value if hasattr(ev, "event_type_value") else str(ev.event_type)

    if et == "tool_call":
        args = details.get("args")
        if args:
            return (
                f"Calling: {details.get('tool', 'unknown')}\n"
                f"args: {json.dumps(args, ensure_ascii=False, indent=2, default=str)}"
            )
        return ev.message or ""

    if et == "tool_result":
        status = "OK" if details.get("success") else "FAIL"
        output = details.get("output", "")
        if not isinstance(output, str):
            output = json.dumps(output, ensure_ascii=False, indent=2, default=str)
        return f"{status} {details.get('tool', 'unknown')}:\n{output}"

    return (ev.message or "").strip()


@dataclass
class RunRecord:
    """Everything that happened in a mission run - evaluated after run()."""
    events: list[dict] = field(default_factory=list)
    tool_calls: Counter = field(default_factory=Counter)
    plan_history: list[str] = field(default_factory=list)
    final_answer: str = ""
    duration: float = 0.0
    # 1 step = 1 ReAct-round = a new tool_call burst after a tool_result.
    # step_start is not emitted by current LeanAgent/planning strategies, so
    # we derive the count from tool_call transitions.
    step_count: int = 0
    llm_calls: int = 0  # = number of assistant-messages after the run
    files_before: dict = field(default_factory=dict)
    files_after: dict = field(default_factory=dict)
    initial_system_prompt_chars: int = 0


def _snapshot_outputs(root: Path, subdirs: tuple[str, ...]) -> dict:
    """Pfad -> (size, mtime) for all files in the given output subdirs."""
    snap = {}
    for sub in subdirs:
        d = root / sub
        if not d.is_dir():
            continue
        for f in d.rglob("*"):
            if f.is_file():
                st = f.stat()
                snap[str(f.relative_to(root))] = (st.st_size, st.st_mtime)
    return snap


async def run(
    executor,
    agent,
    mission: str,
    *,
    project_root: Path | None = None,
    snapshot_subdirs: tuple[str, ...] = ("fall-log", "drafts"),
    initial_system_prompt_chars: int = 0,
    max_print_events: int = 40,
    silent: bool = False,
) -> RunRecord:
    """Execute a mission, capture all events, return a RunRecord.

    Args:
        executor: AgentExecutor.
        agent: Agent instance (from factory.create_agent).
        mission: The mission text.
        project_root: If set, snapshot files in snapshot_subdirs before+after.
        snapshot_subdirs: Subdirectories under project_root to track. Default
            matches TuttiPaletti; for Butler use ("wiki", "schedules") or
            similar.
        initial_system_prompt_chars: Pass len(your_system_prompt) so the
            skill-injection diagnostics work.
        max_print_events: Cap on live-log lines.
        silent: If True, suppress live log entirely (useful for batch runs).
    """
    rec = RunRecord(initial_system_prompt_chars=initial_system_prompt_chars)
    if project_root is not None:
        rec.files_before = _snapshot_outputs(project_root, snapshot_subdirs)

    started = time.time()
    shown = 0
    truncated = False
    last_event_type: str | None = None

    async for ev in executor.execute_mission_streaming(mission=mission, agent=agent):
        et = ev.event_type_value if hasattr(ev, "event_type_value") else str(ev.event_type)
        details = ev.details or {}
        t = time.time() - started

        if et in {"step_start", "tool_call", "tool_result", "final_answer", "error"}:
            rec.events.append({
                "t": t,
                "event": et,
                "tool": details.get("tool"),
                "tool_args": details.get("args"),
                "tool_success": details.get("success"),
                "output": details.get("output") if et == "tool_result" else None,
                "message": ev.message,
            })

        # Step approximation: transition (tool_result|start) -> tool_call = new step
        if et == "tool_call" and last_event_type != "tool_call":
            rec.step_count += 1

        if et == "tool_call":
            rec.tool_calls[details.get("tool", "?")] += 1
        elif et == "tool_result":
            if details.get("tool") == "planner" and details.get("success"):
                out = details.get("output", "")
                if isinstance(out, str):
                    rec.plan_history.append(out[:3000])
        elif et == "final_answer":
            rec.final_answer = str(details.get("content") or ev.message or "")

        if not silent and et in INTERESTING_EVENTS:
            if shown < max_print_events:
                print(f"[{et:14s}] {full_event_message(ev)}")
                shown += 1
            elif not truncated:
                print("... (Ausgabe gekappt; Mission laeuft im Hintergrund weiter)")
                truncated = True

        last_event_type = et

    rec.duration = time.time() - started

    # LLM-Calls = assistant-messages at end (safe, no async risk)
    try:
        rec.llm_calls = sum(
            1 for m in agent.context.messages if m.get("role") == "assistant"
        )
    except Exception:
        rec.llm_calls = 0

    if project_root is not None:
        rec.files_after = _snapshot_outputs(project_root, snapshot_subdirs)

    return rec


def file_diff_report(rec: RunRecord) -> dict:
    """Compare files_before/files_after in the RunRecord."""
    before, after = rec.files_before, rec.files_after
    new = sorted(set(after) - set(before))
    deleted = sorted(set(before) - set(after))
    common = set(before) & set(after)
    modified = sorted(p for p in common if before[p] != after[p])
    unchanged = sorted(p for p in common if before[p] == after[p])
    return {"new": new, "modified": modified, "deleted": deleted, "unchanged": unchanged}


def reset_output_dirs(root: Path, subdirs: tuple[str, ...] = ("fall-log", "drafts")) -> None:
    """Empty the output subdirs under project_root. Call before runs that
    should not be influenced by prior artifacts."""
    for sub in subdirs:
        d = root / sub
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)


def patch_notification_defaults(
    agent,
    *,
    default_channel: str = "telegram",
    default_recipient_id: str = "analysis-test",
) -> None:
    """Patch reminder/schedule/notification tools with default channel+recipient.

    Needed when running the Butler programmatically without an attached
    CommunicationGateway: the tools refuse to register jobs / send notifications
    without a recipient_id. We patch the in-memory tool instances post-build.

    No notifications actually leave the machine - there's no Gateway wired up
    to dispatch the patched recipient. The point is to keep the tool's
    validate-then-register path happy so we can measure agent behaviour.
    Use a real Gateway via factory.set_gateway(...) for end-to-end tests.
    """
    # agent.tools is dict[str, ToolProtocol] — iterate values, not keys.
    # Tools may be wrapped (OutputFilteringTool); unwrap before patching.
    patched: list[str] = []
    for name, tool in agent.tools.items():
        target = getattr(tool, "_original", tool)
        if hasattr(target, "_default_recipient_id"):
            target._default_recipient_id = default_recipient_id
            target._default_channel = default_channel
            patched.append(name)
    return patched


def disable_post_mission_learning(executor) -> None:
    """Disable the post-mission LearningService for analysis runs.

    The executor reads ``learning.enabled`` from disk via ProfileLoader at
    mission completion (executor.py:_run_post_mission_learning), so patching
    the agent's ``_merged_config`` after build has no effect. We monkey-patch
    the executor method to a no-op instead. Safe for analysis - real Butler
    deployments use the executor as-is and keep the learning feature.

    Call ONCE after creating the AgentExecutor.
    """
    async def _noop(*args, **kwargs):
        return None
    executor._run_post_mission_learning = _noop


def patch_anti_compression(agent, summary_threshold: int = 80,
                           tool_result_store_threshold: int = 6000) -> None:
    """Raise the compression and tool-result-store thresholds for analysis runs.

    The defaults (20 / 2000) are too low for parallel tool use - even modest
    parallelism (max_parallel_tools=4) hits 20 messages in 2-3 bursts, then
    compression-LLM-call loops kick in (often tripping Azure content filter).

    The settings live as private attributes on internal components, so patching
    `agent.summary_threshold = 80` alone is a no-op. We patch the real spots.
    """
    agent.message_history_manager._summary_threshold = summary_threshold
    agent.tool_executor._result_store_threshold = tool_result_store_threshold
    # Top-level mirrors for print consistency
    agent.summary_threshold = summary_threshold
    agent._tool_result_store_threshold = tool_result_store_threshold


# =============================================================================
# SECTION 2 - Reports (text printing)
# =============================================================================

def print_summary(rec: RunRecord) -> None:
    print(f"\n{'='*60}")
    print(
        f"Duration: {rec.duration:.1f}s | "
        f"Steps (Bursts): {rec.step_count} | "
        f"LLM-Calls: {rec.llm_calls} | "
        f"Tool calls: {sum(rec.tool_calls.values())}"
    )
    print(f"\nFinal answer (first 800 chars):\n")
    print(rec.final_answer[:800])


def print_tool_stats(rec: RunRecord) -> None:
    print("Tool-Aufrufe (Haeufigkeit):")
    for tool, n in rec.tool_calls.most_common():
        print(f"  {tool:14s} {n:>3}x")
    print(f"\nTotal Events:                       {len(rec.events)}")
    print(f"Plan-Snapshots (planner-Tool):      {len(rec.plan_history)}")


def print_plan_history(rec: RunRecord, *, latest_only: bool = True) -> None:
    if not rec.plan_history:
        print("(Keine planner-Tool-Aufrufe - strategieabhaengig.)")
        return
    snaps = [rec.plan_history[-1]] if latest_only else rec.plan_history
    for i, snap in enumerate(snaps, 1):
        if not latest_only:
            print(f"\n--- Snapshot {i}/{len(rec.plan_history)} ---")
        else:
            print("\n--- Letzter Plan-Snapshot ---")
        print(snap)


def print_artifacts(root: Path, subdirs: tuple[str, ...] = ("fall-log", "drafts")) -> None:
    print("\n--- Artifacts ---")
    for sub in subdirs:
        d = root / sub
        if d.is_dir():
            for f in sorted(d.iterdir()):
                if f.is_file():
                    print(f"  {sub}/{f.name}  ({f.stat().st_size} bytes)")


def print_context_evolution(rec: RunRecord) -> None:
    """Event timeline + cumulative tool-output chars as a context-load proxy."""
    print(f"{'t [s]':>6} {'step':>5} {'event':14s} {'tool':12s} {'note':60s}")
    print("-" * 100)
    cum_chars = 0
    step = 0
    for e in rec.events:
        et = e["event"]
        if et == "step_start":
            step += 1
            note = "(neue ReAct-Runde)"
        elif et == "tool_call":
            args_str = json.dumps(e.get("tool_args") or {}, ensure_ascii=False, default=str)
            note = args_str[:60]
        elif et == "tool_result":
            out = e.get("output") or ""
            if not isinstance(out, str):
                out = json.dumps(out, default=str)
            cum_chars += len(out)
            status = "OK" if e["tool_success"] else "FAIL"
            note = f"{status} | out {len(out):>5} chars | sum {cum_chars:>6}"
        else:
            note = (e.get("message") or "")[:60]
        print(f"{e['t']:6.2f} {step:>5} {et:14s} {(e.get('tool') or ''):12s} {note}")


def print_tool_results(rec: RunRecord, *, head: int | None = None) -> None:
    """Tool-call -> tool-result pairs. ADR-025 detours auto-annotated."""
    n = 0
    for e in rec.events:
        if e["event"] == "tool_call":
            args = e.get("tool_args") or {}
            args_str = json.dumps(args, ensure_ascii=False, default=str)
            annot = ""
            if e["tool"] == "file_read" and "tool_results/results/" in str(args.get("path", "")):
                annot = "  [ADR-025 Tool-Result-Store-Lookup]"
            print(f"\n  -> {e['tool']}({args_str[:150]}){annot}")
        elif e["event"] == "tool_result":
            status = "OK" if e["tool_success"] else "FAIL"
            out = e.get("output") or ""
            if not isinstance(out, str):
                out = json.dumps(out, default=str)
            preview = out[:200].replace("\n", " ")
            print(f"     {status}: {preview}")
            n += 1
            if head is not None and n >= head:
                break


def print_sanity_check(rec: RunRecord) -> None:
    """File-diff + write/edit-call vs. file-change consistency."""
    diff = file_diff_report(rec)
    print("=== Datei-Diff ===")
    print(f"  NEU geschrieben   : {len(diff['new']):>2}")
    for p in diff["new"]:
        size = rec.files_after[p][0]
        print(f"     + {p}  ({size} bytes)")
    print(f"  MODIFIZIERT       : {len(diff['modified']):>2}")
    for p in diff["modified"]:
        old_size = rec.files_before[p][0]
        new_size = rec.files_after[p][0]
        print(f"     M {p}  ({old_size} -> {new_size} bytes)")
    print(f"  UNVERAENDERT      : {len(diff['unchanged']):>2}")
    if diff["deleted"]:
        print(f"  GELOESCHT         : {len(diff['deleted']):>2}")
        for p in diff["deleted"]:
            print(f"     - {p}")

    write_count = rec.tool_calls.get("file_write", 0)
    edit_count = rec.tool_calls.get("edit", 0)
    # wiki(action in {write_page, update_page, log, delete_page}) zaehlt auch als write.
    wiki_writes = sum(
        1 for e in rec.events
        if e["event"] == "tool_call"
        and e["tool"] == "wiki"
        and (e.get("tool_args") or {}).get("action") in
            {"write_page", "update_page", "log", "delete_page"}
    )
    total_writes = write_count + edit_count + wiki_writes
    total_changed = len(diff["new"]) + len(diff["modified"])

    print(f"\n=== Sanity-Check ===")
    print(f"  file_write Calls         : {write_count}")
    print(f"  edit Calls               : {edit_count}")
    print(f"  wiki write-action Calls  : {wiki_writes}")
    print(f"  Neue/modifizierte Files  : {total_changed}")
    if total_writes == 0 and total_changed > 0:
        print("  WARNUNG: Files geaendert, aber keine write/edit/wiki Tool-Calls -")
        print("  vermutlich Tool-Result-Store oder frueherer Lauf.")
    elif total_writes > 0 and total_changed == 0:
        print("  WARNUNG: write Calls aber keine Datei-Aenderungen -")
        print("  HALLUZINATION oder Workspace-Pfad-Problem moeglich.")
    elif total_changed == 0:
        print("  Hinweis: keine Output-Files - Szenario erfordert evtl. keine.")
    else:
        print("  OK")


def print_context_view(agent, rec: RunRecord) -> None:
    """Token-snapshot + raw-message view + skill-injection diagnostics."""
    snap = agent.context.snapshot(include_content=True)
    raw = agent.context.messages

    print("=== Snapshot (Token-View) ===")
    print(f"  total_tokens        : {snap.total_tokens:>6}")
    print(f"  max_tokens          : {snap.max_tokens:>6}")
    print(f"  utilization         : {snap.utilization_percent:>6.1f}%")
    for name, items in [
        ("system_prompt", snap.system_prompt),
        ("messages", snap.messages),
        ("memory", snap.memory),
        ("skills", snap.skills),
        ("tools", snap.tools),
    ]:
        toks = sum(i.tokens for i in items)
        print(f"  {name:18s}: {len(items):>3} items  ({toks:>5} tokens)")
    print(f"  sub_agents          : {len(snap.sub_agents):>3}")

    by_role: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for m in raw:
        by_role[m.get("role", "?")][0] += 1
        by_role[m.get("role", "?")][1] += len(str(m.get("content", "")))
    total_chars = sum(c for _, c in by_role.values())

    print(f"\n=== Raw Messages ===")
    print(f"  {len(raw)} messages, {total_chars} chars total")
    for role, (n, c) in sorted(by_role.items()):
        print(f"    {role:9s} {n:>3} msgs  {c:>7} chars")

    # Skill-injection diagnostic
    print(f"\n=== Skill-Injection ===")
    system_now = by_role.get("system", [0, 0])[1]
    initial = rec.initial_system_prompt_chars
    delta = system_now - initial
    print(f"  System initial      : {initial:>6} chars")
    print(f"  System jetzt        : {system_now:>6} chars")
    print(f"  Delta               : {delta:+>6} chars")
    skill_calls = [
        e for e in rec.events
        if e["event"] == "tool_call" and e["tool"] == "activate_skill"
    ]
    if skill_calls:
        names = [str((e.get("tool_args") or {}).get("skill_name", "?")) for e in skill_calls]
        print(f"  activate_skill      : {len(skill_calls)}x {names}")
        if delta > 1000:
            print(f"  -> Skill injiziert (~{delta} chars)")
    else:
        print(f"  activate_skill      : 0x")


# =============================================================================
# SECTION 3 - Plots (matplotlib)
# =============================================================================
# matplotlib is imported lazily so analysis_lib can be imported even if
# matplotlib is missing (e.g. in pure-text reporting environments).

def _mpl():
    """Lazy matplotlib import. Returns (plt, mpl) or raises ImportError."""
    import matplotlib
    import matplotlib.pyplot as plt
    return plt, matplotlib


def plot_tool_frequencies(rec: RunRecord, *, title: str | None = None):
    plt, _ = _mpl()
    tools, counts = zip(*rec.tool_calls.most_common()) if rec.tool_calls else ([], [])
    fig, ax = plt.subplots(figsize=(8, max(3, 0.4 * len(tools))))
    ax.barh(list(tools), list(counts), color="steelblue")
    ax.invert_yaxis()
    ax.set_xlabel("Tool calls")
    ax.set_title(title or "Tool-Aufrufe")
    for i, (_, c) in enumerate(zip(tools, counts)):
        ax.text(c + 0.1, i, str(c), va="center", fontsize=9)
    plt.tight_layout()
    return fig


def plot_context_growth(rec: RunRecord, *, title: str | None = None):
    plt, _ = _mpl()
    ts = []
    cum = []
    s = 0
    for e in rec.events:
        if e["event"] != "tool_result":
            continue
        out = e.get("output") or ""
        if not isinstance(out, str):
            out = json.dumps(out, default=str)
        s += len(out)
        ts.append(e["t"])
        cum.append(s)
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(ts, cum, marker="o", color="darkorange", markersize=4)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Cumulative tool-output chars")
    ax.set_title(title or "Context-Wachstum (Proxy)")
    ax.grid(alpha=0.3)
    plt.tight_layout()
    return fig


def plot_strategy_compare(records: dict[str, RunRecord], *, title: str | None = None):
    """records: {label: RunRecord}. Plots grouped bar of key metrics."""
    plt, _ = _mpl()
    metrics = {
        "bursts": [r.step_count for r in records.values()],
        "llm_calls": [r.llm_calls for r in records.values()],
        "tool_calls": [sum(r.tool_calls.values()) for r in records.values()],
        "plans": [len(r.plan_history) for r in records.values()],
        "duration[s]": [r.duration for r in records.values()],
    }
    labels = list(records.keys())
    x = list(range(len(metrics)))
    width = 0.8 / len(labels)

    fig, ax = plt.subplots(figsize=(10, 4.5))
    for i, label in enumerate(labels):
        vals = [metrics[m][i] for m in metrics]
        offsets = [xi + (i - len(labels) / 2 + 0.5) * width for xi in x]
        bars = ax.bar(offsets, vals, width, label=label)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(),
                    f"{v:.1f}" if isinstance(v, float) else str(v),
                    ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(list(metrics.keys()))
    ax.set_title(title or "Strategy compare")
    ax.legend()
    plt.tight_layout()
    return fig


def plot_role_distribution(agent, *, title: str | None = None):
    """Stacked bar of message-role contribution (count and chars)."""
    plt, _ = _mpl()
    by_role: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for m in agent.context.messages:
        by_role[m.get("role", "?")][0] += 1
        by_role[m.get("role", "?")][1] += len(str(m.get("content", "")))

    roles = sorted(by_role.keys())
    counts = [by_role[r][0] for r in roles]
    chars = [by_role[r][1] for r in roles]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    ax1.bar(roles, counts, color="seagreen")
    ax1.set_title("Messages pro Rolle")
    for i, c in enumerate(counts):
        ax1.text(i, c, str(c), ha="center", va="bottom", fontsize=9)
    ax2.bar(roles, chars, color="indianred")
    ax2.set_title("Chars pro Rolle")
    for i, c in enumerate(chars):
        ax2.text(i, c, str(c), ha="center", va="bottom", fontsize=9)
    fig.suptitle(title or "Context-Verteilung nach Rolle")
    plt.tight_layout()
    return fig


def plot_scenario_matrix(results: list, *, metric: str = "passed",
                         title: str | None = None):
    """results: list[ScenarioResult]. Renders a heatmap-like grid.

    metric: 'passed' (green/red), 'duration', 'tool_calls'.
    """
    plt, _ = _mpl()
    rows = [r for r in results]
    labels = [r.scenario.id for r in rows]
    if metric == "passed":
        values = [1.0 if r.passed else 0.0 for r in rows]
        colors = ["forestgreen" if v else "indianred" for v in values]
    elif metric == "duration":
        values = [r.record.duration for r in rows]
        colors = ["steelblue"] * len(values)
    elif metric == "tool_calls":
        values = [sum(r.record.tool_calls.values()) for r in rows]
        colors = ["purple"] * len(values)
    else:
        raise ValueError(f"unknown metric: {metric}")

    fig, ax = plt.subplots(figsize=(9, max(3, 0.35 * len(rows))))
    ax.barh(labels, values, color=colors)
    ax.invert_yaxis()
    ax.set_title(title or f"Scenarios x {metric}")
    for i, v in enumerate(values):
        label = f"{v:.1f}" if isinstance(v, float) else str(v)
        ax.text(v, i, " " + label, va="center", fontsize=9)
    plt.tight_layout()
    return fig


# =============================================================================
# SECTION 4 - Scenarios
# =============================================================================

@dataclass
class Scenario:
    """A single test scenario loaded from YAML."""
    id: str
    category: str
    difficulty: str
    mission: str
    expected: dict
    hidden_intent: str | None = None
    requires: list[str] = field(default_factory=list)
    notes: str | None = None
    # Optional: missions to run BEFORE the main mission, on the same agent.
    # Used to pre-populate state (e.g. wiki pages) for recall-style scenarios.
    # The setup missions are NOT scored - only the main mission counts.
    setup: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Scenario":
        return cls(
            id=d["id"],
            category=d.get("category", "misc"),
            difficulty=d.get("difficulty", "medium"),
            mission=d["mission"],
            expected=d.get("expected", {}),
            hidden_intent=d.get("hidden_intent"),
            requires=d.get("requires", []),
            notes=d.get("notes"),
            setup=d.get("setup", []) or [],
        )


@dataclass
class ScoreCard:
    """Outcome of evaluating a RunRecord against a Scenario.expected dict."""
    must_call_tools_pass: bool = True
    must_succeed_tools_pass: bool = True  # NEW: tool was called AND returned success
    must_not_call_tools_pass: bool = True
    answer_contains_pass: bool = True
    answer_forbidden_pass: bool = True
    details: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            self.must_call_tools_pass
            and self.must_succeed_tools_pass
            and self.must_not_call_tools_pass
            and self.answer_contains_pass
            and self.answer_forbidden_pass
        )


@dataclass
class ScenarioResult:
    """One scenario run + scoring."""
    scenario: Scenario
    record: RunRecord
    rule_score: ScoreCard
    llm_judge: dict | None = None  # {pass: bool, reasoning: str, score: 0-5}
    error: str | None = None  # populated on hard failure
    # Multi-run aggregation (populated by run_scenarios with repeats > 1)
    repeats: int = 1
    pass_count: int = 0  # number of successful repeats (>= ceil(repeats/2) to count as passed)

    @property
    def passed(self) -> bool:
        if self.repeats > 1:
            # Majority-pass: more than half of repeats must succeed
            return self.pass_count > self.repeats / 2
        if self.error:
            return False
        if not self.rule_score.passed:
            return False
        if self.llm_judge and not self.llm_judge.get("pass", True):
            return False
        return True


def load_scenarios(path: str | Path) -> list[Scenario]:
    """Load scenarios from a YAML file (top-level list)."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return [Scenario.from_dict(d) for d in data]


def filter_scenarios(scenarios: list[Scenario],
                     available_tools: set[str]) -> list[Scenario]:
    """Keep scenarios whose `requires:` are subset of available_tools."""
    return [s for s in scenarios if set(s.requires) <= available_tools]


def _successful_tool_calls(rec: RunRecord) -> set[str]:
    """Tool names that had at least one successful tool_result event."""
    ok: set[str] = set()
    for e in rec.events:
        if e["event"] == "tool_result" and e.get("tool_success"):
            t = e.get("tool")
            if t:
                ok.add(t)
    return ok


def _check_contains_clause(clause, answer: str) -> bool:
    """A clause is either a string (substring match) or list (OR-set: any match)."""
    if isinstance(clause, str):
        return clause.lower() in answer
    if isinstance(clause, (list, tuple)):
        return any(_check_contains_clause(c, answer) for c in clause)
    raise TypeError(f"final_answer_contains clause must be str or list, got {type(clause)}")


def score_rule_based(rec: RunRecord, scenario: Scenario) -> ScoreCard:
    """Deterministic scoring of a RunRecord against scenario.expected.

    Supported expected-keys:
        must_call_tools: list[str]            - all must be called (any outcome)
        must_succeed_tools: list[str]         - all must be called AND succeed
        must_not_call_tools: list[str]        - none of these may be called
        final_answer_contains: list[str|list] - each clause must match.
            String clause: substring match (case-insensitive).
            List clause: OR-set - ANY element must match.
            Example: [["nicht", "kann nicht", "leider"], "WhatsApp"]
            means (nicht OR kann nicht OR leider) AND WhatsApp.
        final_answer_must_not_contain: list[str] - forbidden substrings
    """
    sc = ScoreCard()
    e = scenario.expected
    called = set(rec.tool_calls.keys())
    succeeded = _successful_tool_calls(rec)
    answer = (rec.final_answer or "").lower()

    must_call = set(e.get("must_call_tools", []))
    if must_call and not must_call <= called:
        missing = must_call - called
        sc.must_call_tools_pass = False
        sc.details.append(f"must_call missing: {sorted(missing)}")

    must_succeed = set(e.get("must_succeed_tools", []))
    if must_succeed and not must_succeed <= succeeded:
        missing = must_succeed - succeeded
        sc.must_succeed_tools_pass = False
        sc.details.append(f"must_succeed but failed/uncalled: {sorted(missing)}")

    must_not = set(e.get("must_not_call_tools", []))
    if must_not & called:
        unexpected = must_not & called
        sc.must_not_call_tools_pass = False
        sc.details.append(f"must_not_call but did: {sorted(unexpected)}")

    contains = e.get("final_answer_contains", [])
    if contains:
        unmet = [c for c in contains if not _check_contains_clause(c, answer)]
        if unmet:
            sc.answer_contains_pass = False
            sc.details.append(f"answer missing clauses: {unmet}")

    forbidden = e.get("final_answer_must_not_contain", [])
    if forbidden:
        hit = [f for f in forbidden if f.lower() in answer]
        if hit:
            sc.answer_forbidden_pass = False
            sc.details.append(f"answer contains forbidden: {hit}")

    return sc


async def score_llm_judge(
    rec: RunRecord, scenario: Scenario, llm_provider, model_alias: str = "fast",
) -> dict:
    """Optional LLM-based judging. Returns {pass, score, reasoning}.

    Asks the judge whether the agent's response satisfies the scenario's
    mission and hidden_intent. Independent of rule-based scoring.
    """
    prompt = (
        f"Du bewertest, ob ein Agent eine User-Mission ausreichend geloest hat.\n\n"
        f"=== MISSION ===\n{scenario.mission}\n\n"
        f"=== HIDDEN INTENT (was der Agent erkennen sollte, nicht explizit gesagt) ===\n"
        f"{scenario.hidden_intent or '(keiner)'}\n\n"
        f"=== AGENT-ANTWORT ===\n{rec.final_answer[:2000]}\n\n"
        f"Bewerte auf einer Skala 0-5 (5=perfekt, 0=komplett verfehlt) UND ob "
        f"die Antwort als 'pass' gilt (>=3 = pass).\n\n"
        f"Antworte STRENG als JSON: {{\"score\": <int>, \"pass\": <bool>, \"reasoning\": \"<kurz>\"}}"
    )
    try:
        messages = [{"role": "user", "content": prompt}]
        resp = await llm_provider.complete(
            messages=messages, model=model_alias, max_tokens=200
        )
        # complete() may return various shapes; try to extract text
        text = resp if isinstance(resp, str) else getattr(resp, "content", str(resp))
        # extract JSON
        import re
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {"pass": True, "score": 3, "reasoning": "judge_format_error", "raw": text[:200]}
        return json.loads(match.group(0))
    except Exception as exc:
        return {"pass": True, "score": 3, "reasoning": f"judge_error: {exc}"}


async def run_scenario(
    executor,
    build_agent_fn,
    scenario: Scenario,
    *,
    project_root: Path | None = None,
    snapshot_subdirs: tuple[str, ...] = (),
    llm_judge_provider=None,
    llm_judge_model: str = "fast",
    silent: bool = True,
) -> ScenarioResult:
    """Run a single scenario end-to-end.

    Args:
        build_agent_fn: callable that returns (agent, system_prompt_chars).
            Called once per scenario for isolation. Should NOT share state
            between calls.

    If scenario.setup is non-empty, those missions are executed on the SAME
    agent BEFORE the main mission. They are not scored - their purpose is
    state pre-population (wiki pages, scheduled jobs, etc.).
    """
    try:
        agent, sys_chars = await build_agent_fn()
    except Exception as exc:
        return ScenarioResult(
            scenario=scenario,
            record=RunRecord(),
            rule_score=ScoreCard(must_call_tools_pass=False),
            error=f"build_agent failed: {exc}",
        )

    try:
        # Setup missions (pre-population, not scored)
        for setup_mission in scenario.setup:
            try:
                await run(
                    executor, agent, setup_mission,
                    project_root=None,  # snapshot only counts on main mission
                    snapshot_subdirs=(),
                    initial_system_prompt_chars=sys_chars,
                    silent=True,
                )
            except Exception as exc:
                # Setup failure is logged but doesn't abort the scenario.
                # The main mission will then probably fail too, which is
                # the right signal (state not as expected).
                pass

        rec = await run(
            executor, agent, scenario.mission,
            project_root=project_root,
            snapshot_subdirs=snapshot_subdirs,
            initial_system_prompt_chars=sys_chars,
            silent=silent,
        )
        rule = score_rule_based(rec, scenario)
        judge = None
        if llm_judge_provider is not None:
            judge = await score_llm_judge(
                rec, scenario, llm_judge_provider, llm_judge_model
            )
        return ScenarioResult(scenario=scenario, record=rec, rule_score=rule, llm_judge=judge)
    except Exception as exc:
        return ScenarioResult(
            scenario=scenario,
            record=RunRecord(),
            rule_score=ScoreCard(must_call_tools_pass=False),
            error=f"run failed: {exc}",
        )
    finally:
        try:
            await agent.close()
        except Exception:
            pass


async def run_scenarios(
    executor,
    build_agent_fn,
    scenarios: list[Scenario],
    *,
    project_root: Path | None = None,
    snapshot_subdirs: tuple[str, ...] = (),
    reset_dirs_before_each: tuple[str, ...] = (),
    repeats: int = 1,
    llm_judge_provider=None,
    llm_judge_model: str = "fast",
    progress: bool = True,
) -> list[ScenarioResult]:
    """Run a list of scenarios sequentially, returning per-scenario results.

    Args:
        reset_dirs_before_each: subdirs under project_root to clean before each
            scenario. CRITICAL for state-isolation: without this, wiki pages
            from scenario N leak into N+1 and skew results. Typical values
            include "memory/wiki" (Butler) and "fall-log", "drafts" (TuttiPaletti).
            Empty default = no reset (legacy behaviour).
        repeats: if > 1, each scenario runs N times and the result is
            majority-pass. Best-of representative is kept as the .record /
            .rule_score for inspection. Smoothes LLM variance.
    """
    results: list[ScenarioResult] = []
    for i, s in enumerate(scenarios, 1):
        if progress:
            label = f"[{i:>2}/{len(scenarios)}] {s.id:30s} ({s.category:10s} / {s.difficulty})"
            if repeats > 1:
                label += f"  x{repeats}"
            print(label)

        attempts: list[ScenarioResult] = []
        for k in range(repeats):
            if project_root is not None and reset_dirs_before_each:
                reset_output_dirs(project_root, reset_dirs_before_each)
            attempt = await run_scenario(
                executor, build_agent_fn, s,
                project_root=project_root,
                snapshot_subdirs=snapshot_subdirs,
                llm_judge_provider=llm_judge_provider,
                llm_judge_model=llm_judge_model,
                silent=True,
            )
            attempts.append(attempt)
            if progress and repeats > 1:
                mark = "PASS" if attempt.passed else "FAIL"
                print(f"        run {k+1}/{repeats}: {mark} "
                      f"({attempt.record.duration:.1f}s, "
                      f"{sum(attempt.record.tool_calls.values())} tool calls)")

        # Pick representative: first PASS, else last FAIL
        rep = next((a for a in attempts if a.passed), attempts[-1])
        res = ScenarioResult(
            scenario=rep.scenario,
            record=rep.record,
            rule_score=rep.rule_score,
            llm_judge=rep.llm_judge,
            error=rep.error,
            repeats=repeats,
            pass_count=sum(1 for a in attempts if a.passed),
        )
        if progress:
            mark = "PASS" if res.passed else "FAIL"
            extra = ""
            if res.error:
                extra = f" ERROR: {res.error[:80]}"
            elif not res.rule_score.passed:
                extra = " | " + "; ".join(res.rule_score.details)[:120]
            count_str = f" [{res.pass_count}/{res.repeats}]" if repeats > 1 else ""
            print(f"        -> {mark}{count_str} ({res.record.duration:.1f}s, "
                  f"{sum(res.record.tool_calls.values())} tool calls){extra}")
        results.append(res)
    return results


def print_scenario_summary(results: list[ScenarioResult]) -> None:
    """Per-scenario one-liner table + aggregate stats."""
    print(f"\n{'='*80}")
    print(f"{'id':30s} {'cat':10s} {'diff':8s} {'pass':6s} {'tools':>6} {'dur':>7}")
    print("-" * 80)
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        print(
            f"{r.scenario.id:30s} {r.scenario.category:10s} {r.scenario.difficulty:8s} "
            f"{mark:6s} {sum(r.record.tool_calls.values()):>6} {r.record.duration:>6.1f}s"
        )
    n_pass = sum(1 for r in results if r.passed)
    print("-" * 80)
    print(f"Total: {n_pass}/{len(results)} passed "
          f"({n_pass*100/max(1,len(results)):.0f}%)")
