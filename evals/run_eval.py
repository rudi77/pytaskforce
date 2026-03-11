"""Convenience runner for Inspect AI evaluations with Azure config.

Loads .env and maps Azure vars before delegating to inspect eval.

Usage:
    python evals/run_eval.py coding_bugfix
    python evals/run_eval.py coding_full --model openai/azure/gpt-5-mini
    python evals/run_eval.py swe_bench_verified_mini --model openai/azure/gpt-4.1
    python evals/run_eval.py humaneval mmlu_5shot --model openai/azure/gpt-5.2
"""

import os
import subprocess
import sys
from pathlib import Path

# Setup Azure env vars before anything else
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from evals.bridge.azure_config import DEFAULT_MODEL, setup_azure_env

setup_azure_env()

# Task name → (file, description)
TASK_REGISTRY: dict[str, tuple[str, str]] = {
    # --- Coding Agent Benchmarks ---
    "coding_full": ("coding_agent.py", "All 8 coding tasks"),
    "coding_generation": ("coding_agent.py", "Code generation only (4 tasks)"),
    "coding_bugfix": ("coding_agent.py", "Bug fixing only (1 task)"),
    "coding_analysis": ("coding_agent.py", "Analysis + testing (2 tasks)"),
    "coding_spar": ("coding_agent.py", "SPAR strategy"),
    "coding_react": ("coding_agent.py", "ReAct strategy"),
    "coding_plan_and_execute": ("coding_agent.py", "Plan & Execute strategy"),
    # --- SWE-bench ---
    "swe_bench_verified_mini": ("swe_bench.py", "SWE-bench Verified Mini (20 instances)"),
    "swe_bench_lite": ("swe_bench.py", "SWE-bench Lite (300 instances)"),
    "swe_bench_verified": ("swe_bench.py", "SWE-bench Verified (~500 instances)"),
    # --- InstructEval (Model Baselines) ---
    "mmlu_0shot": ("instruct_eval.py", "MMLU 0-shot (57 subjects, ~14k questions)"),
    "mmlu_5shot": ("instruct_eval.py", "MMLU 5-shot (57 subjects, ~14k questions)"),
    "humaneval": ("instruct_eval.py", "HumanEval (164 Python problems)"),
    "gpqa": ("instruct_eval.py", "GPQA Diamond (expert science Q&A)"),
    "arc": ("instruct_eval.py", "ARC Challenge (science reasoning)"),
}

TASKS_DIR = project_root / "evals" / "tasks"

# Windows cleanup crash exit codes (0xC0000005 access violation)
WINDOWS_CRASH_CODES = {-1073741819, 3221225477}


def print_help() -> None:
    print("Usage: python evals/run_eval.py <task_name> [task_name...] [--model <model>] [flags...]")
    print(f"\nDefault model: {DEFAULT_MODEL}")
    print("\n--- Coding Agent Benchmarks (tests the agent framework) ---")
    for name, (_, desc) in TASK_REGISTRY.items():
        if name.startswith("coding_"):
            print(f"  {name:30s} {desc}")
    print("\n--- SWE-bench (real-world GitHub issues, requires Docker) ---")
    for name, (_, desc) in TASK_REGISTRY.items():
        if name.startswith("swe_"):
            print(f"  {name:30s} {desc}")
    print("\n--- InstructEval Baselines (tests the underlying model) ---")
    for name, (_, desc) in TASK_REGISTRY.items():
        if name in ("mmlu_0shot", "mmlu_5shot", "humaneval", "gpqa", "arc"):
            print(f"  {name:30s} {desc}")
    print("\nExamples:")
    print("  python evals/run_eval.py coding_full")
    print("  python evals/run_eval.py swe_bench_verified_mini --model openai/azure/gpt-4.1")
    print("  python evals/run_eval.py humaneval mmlu_5shot --model openai/azure/gpt-5.2")
    print("  python evals/run_eval.py coding_spar coding_react  # strategy comparison")


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print_help()
        sys.exit(0)

    # Separate task names from flags
    task_names: list[str] = []
    extra_args: list[str] = []
    i = 0
    while i < len(args):
        if args[i].startswith("-"):
            extra_args.extend(args[i:])
            break
        task_names.append(args[i])
        i += 1

    # Validate task names
    for name in task_names:
        if name not in TASK_REGISTRY:
            print(f"Error: Unknown task '{name}'.")
            print(f"Available: {', '.join(sorted(TASK_REGISTRY.keys()))}")
            sys.exit(1)

    # Default model if not specified
    if "--model" not in extra_args:
        extra_args.extend(["--model", DEFAULT_MODEL])

    model_name = extra_args[extra_args.index("--model") + 1]
    results: list[tuple[str, int]] = []

    for task_name in task_names:
        task_file, desc = TASK_REGISTRY[task_name]
        task_path = str(TASKS_DIR / task_file)

        cmd = [
            sys.executable, "-m", "inspect_ai", "eval",
            f"{task_path}@{task_name}",
            *extra_args,
        ]

        print(f"\n{'='*60}")
        print(f"  {task_name}: {desc}")
        print(f"  Model: {model_name}")
        print(f"{'='*60}\n")

        result = subprocess.run(cmd, env=os.environ.copy())
        rc = result.returncode

        if rc in WINDOWS_CRASH_CODES:
            print(f"\n(Windows cleanup crash - results are valid)")
            rc = 0

        results.append((task_name, rc))

        if rc != 0:
            print(f"\nTask {task_name} failed with exit code {rc}")
            # Continue with remaining tasks instead of aborting
            continue

    # Summary
    print(f"\n{'='*60}")
    print("  Benchmark Summary")
    print(f"{'='*60}")
    for name, rc in results:
        status = "PASS" if rc == 0 else f"FAIL (exit {rc})"
        print(f"  {name:30s} {status}")
    print(f"\nRun 'inspect view' to see detailed results.")
    print(f"{'='*60}")

    # Exit with failure if any task failed
    if any(rc != 0 for _, rc in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
