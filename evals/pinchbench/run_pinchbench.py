"""Convenience runner for the PinchBench benchmark.

PinchBench (https://github.com/pinchbench/skill) evaluates LLM models as
OpenClaw coding agents on ~180 real-world tasks (productivity, research,
writing, coding, analysis, CSV / log / meeting parsing, memory, skills,
integrations).

Unlike SWE-bench (Inspect AI based, plugs the Taskforce solver into the
existing benchmark), PinchBench is a self-contained Python runner that
shells out to the ``openclaw`` CLI for every task. This wrapper therefore
does not feed pinchbench through Inspect AI — it clones the upstream
``pinchbench/skill`` repository, prepares the environment, and forwards
arguments to ``scripts/benchmark.py``.

Prerequisites:
    - ``uv`` on PATH (used by the upstream ``./scripts/run.sh``)
    - ``openclaw`` CLI on PATH (the agent runtime PinchBench drives via
      subprocess; without it tasks cannot execute)
    - API key for the chosen model provider, e.g. ``OPENROUTER_API_KEY``,
      ``ANTHROPIC_API_KEY``, ``OPENAI_API_KEY``

Usage:
    # ~25 representative core tasks against an OpenRouter model
    python evals/pinchbench/run_pinchbench.py \
        --model openrouter/anthropic/claude-sonnet-4 \
        --suite core

    # Single category against an Azure-fronted model
    python evals/pinchbench/run_pinchbench.py \
        --model openai/azure/gpt-5.4-mini --suite coding

    # Full benchmark (slow, ~180 tasks)
    python evals/pinchbench/run_pinchbench.py \
        --model openrouter/anthropic/claude-sonnet-4 --suite all

The pinchbench checkout, results, and judge cache live under
``evals/pinchbench/skill/`` (gitignored).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

EVAL_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EVAL_DIR.parents[1]
SKILL_DIR = EVAL_DIR / "skill"
RESULTS_DIR = EVAL_DIR / "results"

UPSTREAM_REPO = "https://github.com/pinchbench/skill.git"

DEFAULT_MODEL = "openrouter/anthropic/claude-sonnet-4"

# Suites declared in the upstream tasks/manifest.yaml. ``all`` and ``core``
# are pinchbench keywords; the rest are category names handled by
# scripts/benchmark.py's --suite argument.
SUITES = {
    "core": "~25 representative tasks across all categories (quick smoke test)",
    "all": "Full benchmark (~180 tasks, slow)",
    "automated-only": "Tasks with deterministic graders (no LLM judge required)",
    "productivity": "Calendar, todos, PDF conversion, summaries",
    "research": "Market analysis, competitive intelligence",
    "writing": "Email, blog posts, documentation, commit messages",
    "coding": "Debugging, refactoring, automation, code generation",
    "analysis": "Summarization, anomaly detection, financial analysis",
    "csv_analysis": "Data trends, statistical analysis, rankings",
    "log_analysis": "Server, SSH, HDFS, MapReduce, system logs",
    "meeting_analysis": "Vote extraction, summarization, follow-ups",
    "memory": "Knowledge retention operations",
    "skills": "File operations, workflow, discovery",
    "integrations": "Google Workspace integrations",
}


def _print_help() -> None:
    print(__doc__)
    print("Available --suite values:")
    for name, desc in SUITES.items():
        print(f"  {name:20s} {desc}")


def _ensure_uv() -> str:
    uv = shutil.which("uv")
    if uv:
        return uv
    sys.exit(
        "ERROR: `uv` is not on PATH. Install it from https://docs.astral.sh/uv/ "
        "before running PinchBench (the upstream runner relies on `uv run`)."
    )


def _warn_if_openclaw_missing() -> None:
    """Warn — don't abort — if openclaw is not on PATH.

    Some users may run the wrapper just to clone/update the skill repo or
    inspect the task definitions, so a missing CLI shouldn't be fatal.
    Once an actual benchmark starts pinchbench itself will fail loudly.
    """
    if shutil.which("openclaw") is None:
        print(
            "WARNING: `openclaw` CLI not found on PATH. PinchBench drives the "
            "agent via `openclaw agent --agent <id> --message <prompt>` for "
            "every task — without it the benchmark will fail at the first "
            "task. Install OpenClaw before running real evaluations.",
            file=sys.stderr,
        )


def _ensure_skill_checkout(update: bool) -> Path:
    """Clone or update the pinchbench/skill repository in-place."""
    if not SKILL_DIR.exists():
        print(f"Cloning {UPSTREAM_REPO} into {SKILL_DIR} ...")
        subprocess.run(
            ["git", "clone", "--depth", "1", UPSTREAM_REPO, str(SKILL_DIR)],
            check=True,
        )
    elif update:
        print(f"Updating pinchbench checkout at {SKILL_DIR} ...")
        subprocess.run(["git", "fetch", "--depth", "1", "origin"], cwd=SKILL_DIR, check=True)
        subprocess.run(["git", "reset", "--hard", "origin/HEAD"], cwd=SKILL_DIR, check=True)
    return SKILL_DIR


def _prepare_env(model: str) -> dict[str, str]:
    """Copy the current env and ensure the model's provider key is set."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    env = os.environ.copy()

    provider = model.split("/", 1)[0].lower()
    required = {
        "openrouter": "OPENROUTER_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
    }.get(provider)

    if required and not env.get(required):
        # Azure-fronted OpenAI deployments can still satisfy --base-url /
        # --api-key, so we warn rather than abort.
        print(
            f"WARNING: model `{model}` looks like a `{provider}/` model but "
            f"{required} is not set. Either export the key or pass "
            f"--base-url / --api-key for a custom OpenAI-compatible endpoint.",
            file=sys.stderr,
        )

    return env


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run PinchBench against a chosen model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(f"  {k:20s} {v}" for k, v in SUITES.items()),
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Model identifier with provider prefix (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--suite",
        default="core",
        help="Task suite or category (see epilog). Default: core",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of runs per task for averaging (default: 1)",
    )
    parser.add_argument(
        "--thinking",
        default=None,
        choices=["off", "minimal", "low", "medium", "high", "xhigh", "adaptive"],
        help="Reasoning depth (passed through to pinchbench --thinking)",
    )
    parser.add_argument(
        "--timeout-multiplier",
        type=float,
        default=1.0,
        help="Scale all task timeouts (useful for slow models)",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Pull latest upstream changes into the local skill checkout",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        default=True,
        help="Skip uploading results to the public leaderboard (default: on)",
    )
    parser.add_argument(
        "--upload",
        dest="no_upload",
        action="store_false",
        help="Allow upload to the public leaderboard "
        "(requires --register / PINCHBENCH_OFFICIAL_KEY)",
    )
    parser.add_argument(
        "extra",
        nargs=argparse.REMAINDER,
        help="Additional arguments forwarded verbatim to scripts/benchmark.py "
        "(prefix with --, e.g. `-- --verbose --judge openrouter/openai/gpt-4o`)",
    )

    args = parser.parse_args()

    if args.suite not in SUITES:
        # Pinchbench also accepts comma-separated task IDs, so accept anything
        # but warn about unknown suite names.
        print(
            f"NOTE: `{args.suite}` is not a known suite name; forwarding as-is "
            f"(pinchbench accepts task IDs and category names).",
            file=sys.stderr,
        )

    _ensure_uv()
    _warn_if_openclaw_missing()
    skill_dir = _ensure_skill_checkout(update=args.update)
    env = _prepare_env(args.model)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    cmd: list[str] = [
        "uv",
        "run",
        "scripts/benchmark.py",
        "--model",
        args.model,
        "--suite",
        args.suite,
        "--runs",
        str(args.runs),
        "--timeout-multiplier",
        str(args.timeout_multiplier),
        "--output-dir",
        str(RESULTS_DIR),
    ]
    if args.thinking:
        cmd.extend(["--thinking", args.thinking])
    if args.no_upload:
        cmd.append("--no-upload")

    # Drop the leading `--` separator argparse leaves in REMAINDER, then
    # forward the rest verbatim.
    extras = list(args.extra)
    if extras and extras[0] == "--":
        extras = extras[1:]
    cmd.extend(extras)

    print("=" * 60)
    print("  PinchBench")
    print(f"  Model:        {args.model}")
    print(f"  Suite:        {args.suite}")
    print(f"  Runs/task:    {args.runs}")
    print(f"  Skill repo:   {skill_dir}")
    print(f"  Results dir:  {RESULTS_DIR}")
    print(f"  Command:      {' '.join(cmd)}")
    print("=" * 60)

    result = subprocess.run(cmd, cwd=skill_dir, env=env)
    sys.exit(result.returncode)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        _print_help()
        sys.exit(0)
    main()
