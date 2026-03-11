"""SWE-bench evaluation tasks for the Taskforce coding agent.

Tests the agent's ability to resolve real-world GitHub issues
in Docker-sandboxed repository environments.

Uses ``taskforce_swebench_solver`` which replaces the agent's normal
host tools with sandbox-aware wrappers so that shell commands, file
reads/writes, grep, glob, and git all execute *inside* the Docker
container where the target repository lives.

Prerequisites:
    - Docker must be running
    - Linux/WSL required for SWE-bench scoring (uses ``resource`` module)
    - install: uv pip install "inspect-evals[swe_bench]"

Usage:
    # Run SWE-bench Verified Mini (20 instances)
    python evals/run_eval.py swe_bench_verified_mini --model openai/azure/gpt-4.1

    # Run SWE-bench Lite (300 instances)
    python evals/run_eval.py swe_bench_lite --model openai/azure/gpt-4.1

Environment:
    Requires AZURE_API_KEY, AZURE_API_BASE, AZURE_API_VERSION in .env
"""

from inspect_ai import Task, task
from inspect_evals.swe_bench import swe_bench as _swe_bench

from evals.bridge.azure_config import setup_azure_env
from evals.bridge.taskforce_bridge import taskforce_swebench_solver

setup_azure_env()


@task
def swe_bench_verified_mini():
    """SWE-bench Verified Mini - first 20 instances for quick testing.

    Uses the Taskforce coding agent with sandbox tools so the agent
    can execute commands and modify files inside the Docker container.
    """
    base_task = _swe_bench(
        dataset="princeton-nlp/SWE-bench_Verified",
        split="test[:20]",
    )
    base_task.solver = taskforce_swebench_solver(
        profile="coding_agent",
        max_steps=60,
        planning_strategy="spar",
    )
    return base_task


@task
def swe_bench_lite():
    """SWE-bench Lite - 300 curated GitHub issues.

    Full SWE-bench Lite evaluation with the Taskforce coding agent.
    """
    base_task = _swe_bench(
        dataset="princeton-nlp/SWE-bench_Lite",
        split="test",
    )
    base_task.solver = taskforce_swebench_solver(
        profile="coding_agent",
        max_steps=60,
        planning_strategy="spar",
    )
    return base_task


@task
def swe_bench_verified():
    """SWE-bench Verified - human-validated subset (~500 instances)."""
    base_task = _swe_bench(
        dataset="princeton-nlp/SWE-bench_Verified",
        split="test",
    )
    base_task.solver = taskforce_swebench_solver(
        profile="coding_agent",
        max_steps=60,
        planning_strategy="spar",
    )
    return base_task
