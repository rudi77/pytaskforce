"""
Analyze failing SWE-bench samples from a Taskforce eval log.

Usage:
    python evals/analyze_failures.py [eval_log_path] [sample_id ...]

Default eval log: logs/2026-03-10T14-17-49+00-00_swe-bench-verified-mini_3XzKWc65Yp4ucA9VxJF3oS.eval
Default samples:  12907 13236 14365
"""

import json
import sys
import textwrap
import zipfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_LOG = (
    "logs/2026-03-10T14-17-49+00-00_swe-bench-verified-mini_3XzKWc65Yp4ucA9VxJF3oS.eval"
)
DEFAULT_IDS = ["12907", "13236", "14365"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def truncate(text: str, max_len: int = 400) -> str:
    text = str(text).strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"  ...[+{len(text) - max_len} chars]"


def find_sample_path(zf: zipfile.ZipFile, sample_id: str) -> str | None:
    """Find the JSON path for a sample by its numeric ID."""
    for name in zf.namelist():
        if name.startswith("samples/") and name.endswith(".json"):
            if f"-{sample_id}_epoch_" in name or f"_{sample_id}_epoch_" in name:
                return name
    return None


def extract_issue_text(data: dict) -> str:
    """Pull the issue description from the input messages."""
    messages = data.get("messages", [])
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                # Content blocks
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        return block.get("text", "")
                return str(content[0])
            return str(content)
    return "(no user message found)"


def summarize_events(events: list) -> list[dict]:
    """Return a flat list of action summaries from the events array."""
    summaries = []
    for event in events:
        action = event.get("action", "")
        if not action:
            continue

        if action == "exec":
            cmd = event.get("cmd", "")
            result_code = event.get("result", "?")
            output = str(event.get("output", "")).strip()
            summaries.append(
                {
                    "type": "shell",
                    "cmd": cmd,
                    "exit_code": result_code,
                    "output_snippet": truncate(output, 200),
                }
            )
        elif action == "read_file":
            summaries.append(
                {
                    "type": "read_file",
                    "file": event.get("file", ""),
                }
            )
        elif action == "write_file":
            content = event.get("content", "")
            summaries.append(
                {
                    "type": "write_file",
                    "file": event.get("file", ""),
                    "content_len": len(content),
                    "content_snippet": truncate(content, 300),
                }
            )
        else:
            summaries.append({"type": action, "raw": truncate(str(event), 150)})

    return summaries


def parse_score(data: dict) -> tuple[float, str]:
    """Return (score_value, explanation_text)."""
    scores = data.get("scores", {})
    for scorer_name, scorer_data in scores.items():
        if isinstance(scorer_data, dict):
            value = scorer_data.get("value", "?")
            explanation = scorer_data.get("explanation", "")
            return float(value) if value != "?" else 0.0, explanation
    return 0.0, ""


def parse_fail_to_pass(explanation: str) -> list[str]:
    """Extract FAIL_TO_PASS test names from the scorer explanation."""
    if "FAIL_TO_PASS:" not in explanation:
        return []
    section = explanation.split("FAIL_TO_PASS:")[-1].strip()
    try:
        obj = json.loads(section)
        return [k for k, v in obj.items()]
    except Exception:
        return []


def parse_patch(metadata: dict) -> str:
    """Return the agent's generated patch (model_patch) from scorer metadata."""
    scores = metadata  # caller passes data["scores"] scorer value metadata
    return scores.get("model_patch", "")


def extract_model_patch(data: dict) -> str:
    """Extract the agent-generated patch from scorer metadata."""
    scores = data.get("scores", {})
    for scorer_data in scores.values():
        if isinstance(scorer_data, dict):
            meta = scorer_data.get("metadata", {})
            if isinstance(meta, dict):
                patch = meta.get("model_patch", "")
                if patch:
                    return patch
    return ""


def extract_ground_truth_patch(data: dict) -> str:
    """Extract the ground-truth patch from sample metadata."""
    meta = data.get("metadata", {})
    return meta.get("patch", "")


def diagnose_failure(
    score: float,
    issue_text: str,
    event_summaries: list[dict],
    model_patch: str,
    ground_truth_patch: str,
    explanation: str,
) -> str:
    """Produce a human-readable failure diagnosis."""
    lines = []

    if score > 0:
        lines.append("PARTIAL PASS - some tests passed but key tests still failed.")
    else:
        lines.append("FULL FAIL - no required tests passed.")

    # Check if any patch was produced
    if not model_patch.strip():
        lines.append("NO PATCH generated by agent - agent did not make any code changes.")
        return "\n".join(lines)

    # Grep commands
    shell_cmds = [e for e in event_summaries if e["type"] == "shell"]
    writes = [e for e in event_summaries if e["type"] == "write_file"]
    reads = [e for e in event_summaries if e["type"] == "read_file"]

    lines.append(f"Agent ran {len(shell_cmds)} shell commands, "
                 f"read {len(reads)} files, wrote {len(writes)} files.")

    # Identify files changed vs ground truth
    gt_files = set()
    for line in ground_truth_patch.splitlines():
        if line.startswith("--- a/") or line.startswith("+++ b/"):
            gt_files.add(line.split("/", 1)[-1])

    agent_files = set()
    for line in model_patch.splitlines():
        if line.startswith("--- a/") or line.startswith("+++ b/"):
            agent_files.add(line.split("/", 1)[-1])

    if gt_files and agent_files:
        missed = gt_files - agent_files
        extra = agent_files - gt_files
        if missed:
            lines.append(f"MISSED files (in ground truth but not agent patch): {missed}")
        if extra:
            lines.append(f"EXTRA files (agent changed but ground truth didn't): {extra}")
        if not missed and not extra:
            lines.append("Agent changed the SAME files as ground truth - fix logic may be wrong.")

    # Check for failed tests from explanation
    if "FAIL_TO_PASS" in explanation and "FAILED" in explanation:
        lines.append("Required FAIL_TO_PASS tests still FAILED after agent patch.")

    if "PASS_TO_PASS" in explanation and "FAILED" in explanation:
        lines.append("WARNING: Agent patch also BROKE previously-passing tests (regression).")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------


def analyze_sample(zf: zipfile.ZipFile, sample_id: str) -> None:
    """Analyze and print a single failing sample."""
    path = find_sample_path(zf, sample_id)
    if path is None:
        print(f"[ERROR] Sample {sample_id} not found in zip.")
        return

    with zf.open(path) as f:
        data = json.load(f)

    full_id = data.get("id", path.replace("samples/", "").replace("_epoch_1.json", ""))
    score, explanation = parse_score(data)
    model_patch = extract_model_patch(data)
    ground_truth_patch = extract_ground_truth_patch(data)
    issue_text = extract_issue_text(data)
    events = data.get("events", [])
    event_summaries = summarize_events(events)

    meta = data.get("metadata", {})
    token_usage = meta.get("taskforce_token_usage", {})
    steps = meta.get("taskforce_steps", "?")
    tool_calls_count = meta.get("taskforce_tool_calls", "?")

    # Pull FAIL_TO_PASS test results from explanation
    fail_to_pass_section = ""
    pass_to_pass_section = ""
    if "FAIL_TO_PASS:" in explanation:
        parts = explanation.split("FAIL_TO_PASS:")
        if len(parts) > 1:
            fail_to_pass_section = parts[1].strip()
    if "PASS_TO_PASS:" in explanation:
        parts = explanation.split("PASS_TO_PASS:")
        if len(parts) > 1:
            # Only up to FAIL_TO_PASS
            chunk = parts[1].split("FAIL_TO_PASS:")[0].strip()
            pass_to_pass_section = chunk

    sep = "=" * 80

    print(sep)
    print(f"SAMPLE: {full_id}")
    print(f"SCORE:  {score}")
    print(sep)

    print("\n--- ISSUE DESCRIPTION (first 800 chars) ---")
    print(textwrap.fill(issue_text[:800], width=90))

    print(f"\n--- AGENT ACTIVITY ({len(event_summaries)} actions, {steps} steps) ---")
    for i, s in enumerate(event_summaries):
        stype = s["type"]
        if stype == "shell":
            cmd_short = s["cmd"][:120].replace("\n", " ")
            exit_info = f" [exit={s['exit_code']}]"
            print(f"  [{i:02d}] SHELL{exit_info}: {cmd_short}")
            # Show output only if there was an error or it's short
            if s["exit_code"] not in (0, "0") and s["output_snippet"]:
                print(f"        OUTPUT: {s['output_snippet'][:150]}")
        elif stype == "read_file":
            print(f"  [{i:02d}] READ:  {s['file']}")
        elif stype == "write_file":
            print(f"  [{i:02d}] WRITE: {s['file']} ({s['content_len']} chars)")
        else:
            print(f"  [{i:02d}] {stype.upper()}: {s.get('raw', '')[:100]}")

    print("\n--- AGENT PATCH (model_patch) ---")
    if model_patch:
        # Show first 1500 chars of patch
        patch_display = model_patch[:1500]
        print(patch_display)
        if len(model_patch) > 1500:
            print(f"  ...[patch continues, total {len(model_patch)} chars]")
    else:
        print("  (no patch generated)")

    print("\n--- GROUND TRUTH PATCH (first 1000 chars) ---")
    if ground_truth_patch:
        print(ground_truth_patch[:1000])
        if len(ground_truth_patch) > 1000:
            print(f"  ...[continues, total {len(ground_truth_patch)} chars]")
    else:
        print("  (no ground truth patch)")

    print("\n--- TEST RESULTS ---")
    print("FAIL_TO_PASS (required tests that must go from fail->pass):")
    if fail_to_pass_section:
        try:
            obj = json.loads(fail_to_pass_section)
            for test, result in obj.items():
                marker = "OK " if result == "PASSED" else "FAIL"
                short_test = test.split("::")[-1]
                print(f"  [{marker}] {short_test}")
        except Exception:
            print(f"  {fail_to_pass_section[:300]}")

    print("\nPASS_TO_PASS (must not regress):")
    if pass_to_pass_section:
        try:
            obj = json.loads(pass_to_pass_section)
            failed_p2p = [(t, r) for t, r in obj.items() if r != "PASSED"]
            if failed_p2p:
                print(f"  REGRESSIONS ({len(failed_p2p)} tests now failing):")
                for test, result in failed_p2p[:10]:
                    print(f"    [FAIL] {test.split('::')[-1]}")
            else:
                print(f"  All {len(obj)} pass-to-pass tests still passing.")
        except Exception:
            print(f"  {pass_to_pass_section[:300]}")

    print("\n--- FAILURE DIAGNOSIS ---")
    diagnosis = diagnose_failure(
        score, issue_text, event_summaries,
        model_patch, ground_truth_patch, explanation
    )
    print(diagnosis)

    print()


def main() -> None:
    args = sys.argv[1:]

    if args and not args[0].startswith("-"):
        log_path = args[0]
        sample_ids = args[1:] if len(args) > 1 else DEFAULT_IDS
    else:
        log_path = DEFAULT_LOG
        sample_ids = args if args else DEFAULT_IDS

    print(f"Opening eval log: {log_path}")
    print(f"Analyzing samples: {sample_ids}\n")

    with zipfile.ZipFile(log_path) as zf:
        for sid in sample_ids:
            analyze_sample(zf, sid)


if __name__ == "__main__":
    main()
