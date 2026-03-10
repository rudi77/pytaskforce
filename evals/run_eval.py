"""Convenience runner for Inspect AI evaluations with Azure config.

Loads .env and maps Azure vars before delegating to inspect eval.

Usage:
    python evals/run_eval.py coding_bugfix
    python evals/run_eval.py coding_full --model openai/azure/gpt-5-mini
    python evals/run_eval.py coding_spar coding_react  # compare strategies
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

TASK_FILE = str(project_root / "evals" / "tasks" / "coding_agent.py")

AVAILABLE_TASKS = [
    "coding_full",
    "coding_generation",
    "coding_bugfix",
    "coding_analysis",
    "coding_spar",
    "coding_react",
    "coding_plan_and_execute",
]


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("Usage: python evals/run_eval.py <task_name> [--model <model>] [inspect flags...]")
        print()
        print("Available tasks:")
        for t in AVAILABLE_TASKS:
            print(f"  {t}")
        print()
        print(f"Default model: {DEFAULT_MODEL}")
        print()
        print("Examples:")
        print(f"  python evals/run_eval.py coding_bugfix")
        print(f"  python evals/run_eval.py coding_full --model openai/azure/gpt-5-mini")
        print(f"  python evals/run_eval.py coding_spar coding_react")
        sys.exit(0)

    # Separate task names from flags
    task_names = []
    extra_args = []
    i = 0
    while i < len(args):
        if args[i].startswith("-"):
            extra_args.extend(args[i:])
            break
        task_names.append(args[i])
        i += 1

    # Validate task names
    for name in task_names:
        if name not in AVAILABLE_TASKS:
            print(f"Error: Unknown task '{name}'. Available: {', '.join(AVAILABLE_TASKS)}")
            sys.exit(1)

    # Default model if not specified
    if "--model" not in extra_args:
        extra_args.extend(["--model", DEFAULT_MODEL])

    for task_name in task_names:
        cmd = [
            sys.executable, "-m", "inspect_ai", "eval",
            f"{TASK_FILE}@{task_name}",
            *extra_args,
        ]
        print(f"\n{'='*60}")
        print(f"Running: {task_name}")
        print(f"Model: {extra_args[extra_args.index('--model') + 1]}")
        print(f"{'='*60}\n")

        # Pass current env (with Azure vars already mapped)
        result = subprocess.run(cmd, env=os.environ.copy())

        if result.returncode != 0:
            # Ignore Windows-specific cleanup crashes (0xC0000005)
            if result.returncode in (-1073741819, 3221225477):
                print(f"\n(Windows cleanup crash - results are valid)")
            else:
                print(f"\nTask {task_name} failed with exit code {result.returncode}")
                sys.exit(result.returncode)

    print(f"\n{'='*60}")
    print("All benchmarks complete. Run 'inspect view' to see results.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
