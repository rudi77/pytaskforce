"""Trace-Diagnostics-Extraktor für /evolve Step 3 (Trace-driven Proposer).

Liest das Markdown-Trace-File, das `eval_butler.py::write_trace` schreibt
(typischerweise `.autooptim/last_eval_trace.md`), und emittiert auf stdout
eine objective-spezifische Diagnose, die der /evolve-Proposer als
konkreten Anker statt generischer Hypothesen verwendet.

Pro Objective:
  - Top-N "schlechteste" Missions nach der zum Objective passenden Metrik
  - Pro Mission: Failure-Modes, wiederholte Tool-Calls, ERRORS,
    Tool-Histogramm, Antwort-Snippet
  - Cross-Mission-Pattern: häufigste Tool-Failures, Auth-Issues, Hot-Tools

Stdlib only. Keine externen Abhängigkeiten.

CLI:
    uv run python tests/benchmarks/autooptim/extract_trace_diagnostics.py \
        --objective token_efficiency --top-n 3

Input-Format (siehe `write_trace`):
    # Last Eval Trace (mode: <mode>, N missions)
    ## <Mission Name> [OK|FAILED]
    Steps: S | Tokens: T | Wall: Ws | Tools: K | Notifications: N
    Memory Recall: PASS|FAIL | Turns: M           (optional)
    Delegation after K tool calls                  (optional)
    ERRORS: ...                                    (optional)
    WARNING: ...                                   (optional)
    Tool trace:
      --- <Phase> ---
      -> tool(args)
      <- OK|FAIL tool: preview
      ...
    Answer: ...
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


@dataclass
class ToolCall:
    tool: str
    args: str
    success: bool | None = None  # None until result line is parsed
    result_preview: str = ""
    phase: str = ""


@dataclass
class MissionTrace:
    name: str
    status: str  # "OK" | "FAILED"
    steps: int = 0
    tokens: int = 0
    wall: float = 0.0
    tools: int = 0
    notifications: int = 0
    memory_recall: str | None = None  # "PASS" | "FAIL" | None
    sequence_turns: int | None = None
    delegation_after: int | None = None
    errors: list[str] = field(default_factory=list)
    warning: str | None = None
    tool_trace: list[ToolCall] = field(default_factory=list)
    answer: str = ""

    @property
    def has_answer(self) -> bool:
        return bool(self.answer.strip()) and "did not produce" not in self.answer

    @property
    def answer_length(self) -> int:
        return len(self.answer)


_HEADER_RE = re.compile(r"^##\s+(?P<name>.+?)\s+\[(?P<status>OK|FAILED)\]\s*$")
_METRICS_RE = re.compile(
    r"^Steps:\s*(?P<steps>\d+)\s*\|\s*"
    r"Tokens:\s*(?P<tokens>[\d,]+)\s*\|\s*"
    r"Wall:\s*(?P<wall>[\d.]+)s\s*\|\s*"
    r"Tools:\s*(?P<tools>\d+)\s*\|\s*"
    r"Notifications:\s*(?P<notif>\d+)\s*$"
)
_MEMORY_RE = re.compile(
    r"^Memory Recall:\s*(?P<recall>PASS|FAIL)(?:\s*\|\s*Turns:\s*(?P<turns>\d+|\?))?\s*$"
)
_DELEGATION_RE = re.compile(r"^Delegation after\s+(?P<n>\d+)\s+tool calls\s*$")
_CALL_RE = re.compile(r"^\s*->\s*(?P<tool>\w+)\((?P<args>.*)\)\s*$")
_RESULT_RE = re.compile(
    r"^\s*<-\s*(?P<tag>OK|FAIL)\s+(?P<tool>\w+):\s*(?P<preview>.*)$"
)
_PHASE_RE = re.compile(r"^\s+---\s+(?P<phase>.+?)\s+---\s*$")


def parse_trace(content: str) -> list[MissionTrace]:
    """Parse a trace markdown produced by `eval_butler.py::write_trace`."""
    missions: list[MissionTrace] = []
    current: MissionTrace | None = None
    in_tool_trace = False
    in_answer = False
    answer_lines: list[str] = []
    current_phase = ""

    for raw_line in content.splitlines():
        line = raw_line  # keep leading whitespace for indented matches

        # Section boundary → finalise previous mission
        header_match = _HEADER_RE.match(line)
        if header_match:
            if current is not None:
                current.answer = "\n".join(answer_lines).strip()
                missions.append(current)
            current = MissionTrace(
                name=header_match.group("name"),
                status=header_match.group("status"),
            )
            in_tool_trace = False
            in_answer = False
            answer_lines = []
            current_phase = ""
            continue

        if current is None:
            continue

        # Answer accumulation
        if in_answer:
            answer_lines.append(raw_line)
            continue

        stripped = line.strip()

        # Metrics
        m = _METRICS_RE.match(stripped)
        if m:
            current.steps = int(m.group("steps"))
            current.tokens = int(m.group("tokens").replace(",", ""))
            current.wall = float(m.group("wall"))
            current.tools = int(m.group("tools"))
            current.notifications = int(m.group("notif"))
            continue

        m = _MEMORY_RE.match(stripped)
        if m:
            current.memory_recall = m.group("recall")
            turns = m.group("turns")
            if turns and turns != "?":
                current.sequence_turns = int(turns)
            continue

        m = _DELEGATION_RE.match(stripped)
        if m:
            current.delegation_after = int(m.group("n"))
            continue

        if stripped.startswith("ERRORS:"):
            current.errors.append(stripped[len("ERRORS:"):].strip())
            continue

        if stripped.startswith("WARNING:"):
            current.warning = stripped[len("WARNING:"):].strip()
            continue

        if stripped == "Tool trace:":
            in_tool_trace = True
            continue

        if stripped.startswith("Answer:"):
            in_tool_trace = False
            in_answer = True
            answer_lines = [stripped[len("Answer:"):].lstrip()]
            continue

        if in_tool_trace:
            phase_match = _PHASE_RE.match(line)
            if phase_match:
                current_phase = phase_match.group("phase")
                continue
            call_match = _CALL_RE.match(line)
            if call_match:
                current.tool_trace.append(
                    ToolCall(
                        tool=call_match.group("tool"),
                        args=call_match.group("args"),
                        phase=current_phase,
                    )
                )
                continue
            result_match = _RESULT_RE.match(line)
            if result_match:
                tag = result_match.group("tag")
                tool = result_match.group("tool")
                preview = result_match.group("preview")
                # Match against the last unresolved call for this tool
                for tc in reversed(current.tool_trace):
                    if tc.tool == tool and tc.success is None:
                        tc.success = tag == "OK"
                        tc.result_preview = preview
                        break
                continue

    if current is not None:
        current.answer = "\n".join(answer_lines).strip()
        missions.append(current)

    return missions


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


def rank(missions: list[MissionTrace], objective: str) -> list[MissionTrace]:
    """Return missions sorted worst-first for the given objective."""
    if objective == "token_efficiency":
        return sorted(missions, key=lambda m: m.tokens, reverse=True)
    if objective == "step_reduction":
        return sorted(missions, key=lambda m: m.steps, reverse=True)
    if objective == "wall_time":
        return sorted(missions, key=lambda m: m.wall, reverse=True)
    if objective == "memory_recall":
        # Failures first, then by steps desc
        return sorted(
            missions,
            key=lambda m: (m.memory_recall != "FAIL", -m.steps),
        )
    if objective == "answer_quality":
        # Failed status first, then no-answer, then shortest answers
        return sorted(
            missions,
            key=lambda m: (m.status == "OK", m.has_answer, m.answer_length),
        )
    raise ValueError(f"Unknown objective: {objective}")


def primary_metric_label(objective: str) -> str:
    return {
        "token_efficiency": "tokens",
        "step_reduction": "steps",
        "wall_time": "wall_seconds",
        "memory_recall": "memory_recall",
        "answer_quality": "completion+answer",
    }[objective]


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


_AUTH_MARKERS = ("invalid_grant", "Token has been expired", "401", "Unauthorized")


def diagnose_mission(m: MissionTrace, max_calls: int) -> list[str]:
    """Produce a per-mission diagnostic block as markdown lines."""
    lines: list[str] = []
    lines.append(
        f"- metrics: steps={m.steps}, tokens={m.tokens:,}, wall={m.wall:.1f}s, "
        f"tools={m.tools}, notifications={m.notifications}"
    )
    if m.memory_recall is not None:
        lines.append(
            f"- memory_recall: {m.memory_recall}"
            + (f" (sequence_turns={m.sequence_turns})" if m.sequence_turns else "")
        )
    if m.delegation_after is not None:
        lines.append(f"- delegation_after_tool_calls: {m.delegation_after}")
    if m.errors:
        lines.append(f"- errors: {' | '.join(m.errors)}")
    if m.warning:
        lines.append(f"- warning: {m.warning}")

    # Tool histogram + failure breakdown
    tool_counts: Counter[str] = Counter()
    failure_pairs: list[tuple[str, str]] = []
    auth_failures: Counter[str] = Counter()
    for tc in m.tool_trace:
        tool_counts[tc.tool] += 1
        if tc.success is False:
            failure_pairs.append((tc.tool, tc.result_preview[:80]))
            if any(marker in tc.result_preview for marker in _AUTH_MARKERS):
                auth_failures[tc.tool] += 1

    if tool_counts:
        top = ", ".join(f"{t}×{c}" for t, c in tool_counts.most_common(5))
        lines.append(f"- tool_histogram: {top}")

    if auth_failures:
        auth = ", ".join(f"{t}×{c}" for t, c in auth_failures.most_common())
        lines.append(
            f"- auth_failures (likely infra, not agent): {auth}"
        )

    non_auth_failures = [
        (t, p)
        for t, p in failure_pairs
        if not any(marker in p for marker in _AUTH_MARKERS)
    ]
    if non_auth_failures:
        lines.append("- failures (agent-relevant):")
        for t, p in non_auth_failures[:5]:
            lines.append(f"    - {t}: {p}")

    # Repeated calls — same tool + similar args in a row
    repeats = _detect_repeats(m.tool_trace)
    if repeats:
        lines.append("- repeated_call_loops:")
        for tool, count, sample_args in repeats:
            lines.append(f"    - {tool} ×{count} (sample: `{sample_args[:60]}`)")

    # First N tool calls compressed
    if m.tool_trace:
        lines.append(f"- first_{min(max_calls, len(m.tool_trace))}_calls:")
        for tc in m.tool_trace[:max_calls]:
            tag = "OK" if tc.success else ("FAIL" if tc.success is False else "??")
            phase = f"[{tc.phase}] " if tc.phase else ""
            lines.append(f"    - {phase}{tag} {tc.tool}({tc.args[:60]})")

    # Answer snippet
    if m.has_answer:
        snippet = m.answer.strip().replace("\n", " ")[:200]
        lines.append(f"- answer_snippet: {snippet}")
    else:
        lines.append("- answer: (none — mission produced no final answer)")

    return lines


def _detect_repeats(trace: list[ToolCall]) -> list[tuple[str, int, str]]:
    """Detect sequences where the same tool is called repeatedly back-to-back.

    Returns list of (tool, count, sample_args) for runs of length >= 3.
    """
    if not trace:
        return []
    runs: list[tuple[str, int, str]] = []
    cur_tool = trace[0].tool
    cur_count = 1
    cur_args = trace[0].args
    for tc in trace[1:]:
        if tc.tool == cur_tool:
            cur_count += 1
        else:
            if cur_count >= 3:
                runs.append((cur_tool, cur_count, cur_args))
            cur_tool = tc.tool
            cur_count = 1
            cur_args = tc.args
    if cur_count >= 3:
        runs.append((cur_tool, cur_count, cur_args))
    return runs


def cross_mission_patterns(missions: list[MissionTrace]) -> list[str]:
    """Compute patterns that span multiple missions."""
    lines: list[str] = []

    failed_count = sum(1 for m in missions if m.status == "FAILED")
    no_answer_count = sum(1 for m in missions if not m.has_answer)
    memory_fail_count = sum(1 for m in missions if m.memory_recall == "FAIL")

    lines.append(
        f"- mission_outcomes: {len(missions)} total, "
        f"{failed_count} failed, {no_answer_count} without final answer, "
        f"{memory_fail_count} memory-recall FAIL"
    )

    # Tools that fail most often across the whole run
    fail_counter: Counter[str] = Counter()
    auth_counter: Counter[str] = Counter()
    for m in missions:
        for tc in m.tool_trace:
            if tc.success is False:
                fail_counter[tc.tool] += 1
                if any(marker in tc.result_preview for marker in _AUTH_MARKERS):
                    auth_counter[tc.tool] += 1

    if fail_counter:
        top_fail = ", ".join(f"{t}×{c}" for t, c in fail_counter.most_common(5))
        lines.append(f"- most_failing_tools: {top_fail}")
    if auth_counter:
        top_auth = ", ".join(f"{t}×{c}" for t, c in auth_counter.most_common(5))
        lines.append(
            f"- auth_token_issues (treat as infra, not agent target): {top_auth}"
        )

    # Hot tools — total call counts
    total_counter: Counter[str] = Counter()
    for m in missions:
        for tc in m.tool_trace:
            total_counter[tc.tool] += 1
    if total_counter:
        hot = ", ".join(f"{t}×{c}" for t, c in total_counter.most_common(5))
        lines.append(f"- hot_tools: {hot}")

    # Delegation summary
    delegating = [m for m in missions if m.delegation_after is not None]
    if delegating:
        early = sum(1 for m in delegating if (m.delegation_after or 0) <= 1)
        late = len(delegating) - early
        lines.append(
            f"- delegation_pattern: {early} early (<=1 tool call before), "
            f"{late} late (>1 tool call before)"
        )

    return lines


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def render_report(
    missions: list[MissionTrace],
    objective: str,
    top_n: int,
    max_calls: int,
    source: Path,
) -> str:
    ranked = rank(missions, objective)
    top = ranked[:top_n]

    lines: list[str] = []
    lines.append(f"# Trace Diagnostics — objective: {objective}")
    lines.append("")
    lines.append(f"- source: `{source}`")
    lines.append(f"- total_missions: {len(missions)}")
    lines.append(f"- primary_metric: {primary_metric_label(objective)}")
    lines.append("")

    lines.append("## Cross-mission patterns")
    lines.extend(cross_mission_patterns(missions))
    lines.append("")

    lines.append(f"## Top {len(top)} worst missions (worst first)")
    lines.append("")
    for idx, m in enumerate(top, start=1):
        lines.append(f"### #{idx} — {m.name} [{m.status}]")
        lines.extend(diagnose_mission(m, max_calls))
        lines.append("")

    lines.append("## How to use this report")
    lines.append("")
    lines.append(
        "Each mutation variant in /evolve Step 3 MUST cite at least one diagnostic"
    )
    lines.append(
        "anchor from this report — a specific failure mode, repeated-call loop,"
    )
    lines.append(
        "auth issue, or answer-quality finding. Generic mutations (\"shorten prompt\","
    )
    lines.append(
        "\"try harder\") are rejected. Auth-related failures are infrastructure,"
    )
    lines.append("not agent-target — do NOT propose agent-side mutations against them.")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


_VALID_OBJECTIVES = (
    "token_efficiency",
    "step_reduction",
    "memory_recall",
    "answer_quality",
    "wall_time",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract objective-specific diagnostics from an eval trace.",
    )
    parser.add_argument(
        "--objective",
        required=True,
        choices=_VALID_OBJECTIVES,
        help="Which evolve objective to diagnose for.",
    )
    parser.add_argument(
        "--trace",
        type=Path,
        default=Path(".autooptim/last_eval_trace.md"),
        help="Path to the trace markdown (default: .autooptim/last_eval_trace.md).",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=3,
        help="How many worst-case missions to diagnose (default: 3).",
    )
    parser.add_argument(
        "--max-tool-calls",
        type=int,
        default=12,
        help="Max tool calls to list per mission (default: 12).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write report to this path instead of stdout.",
    )
    args = parser.parse_args(argv)

    if not args.trace.exists():
        print(f"error: trace file not found: {args.trace}", file=sys.stderr)
        return 2

    content = args.trace.read_text(encoding="utf-8")
    missions = parse_trace(content)
    if not missions:
        print(f"error: no missions parsed from {args.trace}", file=sys.stderr)
        return 3

    report = render_report(
        missions,
        objective=args.objective,
        top_n=args.top_n,
        max_calls=args.max_tool_calls,
        source=args.trace,
    )

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
    else:
        sys.stdout.write(report)
        if not report.endswith("\n"):
            sys.stdout.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
