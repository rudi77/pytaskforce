"""GAIA benchmark evaluation tasks for Taskforce agents.

Tests general AI assistant capabilities: multi-step reasoning, web browsing,
file reading, code execution — the core skills of a Butler-style coordinator.

Uses the Butler profile by default, which has access to web search, file read,
gmail, calendar, and can delegate to sub-agents (pc-agent, research_agent).

Dataset: gaia-benchmark/GAIA on HuggingFace (gated, requires HF_TOKEN).
466 questions total: 166 dev (answers public), 300 test (leaderboard).

Prerequisites:
    - uv sync --extra evals
    - HF_TOKEN environment variable set (for gated dataset access)
    - Docker running (GAIA uses sandbox for code execution)

Usage:
    # Quick test: 10 Level-1 questions
    python evals/run_eval.py gaia_quick

    # Full Level 1 (easiest, <5 steps)
    python evals/run_eval.py gaia_level1

    # Full Level 2 (5-10 steps, multi-tool)
    python evals/run_eval.py gaia_level2

    # All levels (dev set, 166 questions)
    python evals/run_eval.py gaia_dev
"""

from inspect_ai import Task, task
from inspect_evals.gaia import gaia as _gaia

from evals.bridge.azure_config import setup_azure_env
from evals.bridge.taskforce_bridge import taskforce_solver

setup_azure_env()


def _butler_solver():
    """Create a Taskforce Butler solver for GAIA tasks.

    The Butler profile has web_search, file_read, python, and delegation
    to sub-agents — matching GAIA's expected tool set.
    """
    return taskforce_solver(profile="butler")


@task
def gaia_quick():
    """GAIA Quick — first 10 Level-1 questions for smoke testing."""
    return _gaia(
        solver=_butler_solver(),
        subset="2023_level1",
        split="validation",
        sandbox=None,  # Butler uses own tools, no Docker needed
    )


@task
def gaia_level1():
    """GAIA Level 1 — simple tasks, fewer than 5 steps."""
    return _gaia(
        solver=_butler_solver(),
        subset="2023_level1",
        split="validation",
        sandbox=None,
    )


@task
def gaia_level2():
    """GAIA Level 2 — multi-tool coordination, 5-10 steps."""
    return _gaia(
        solver=_butler_solver(),
        subset="2023_level2",
        split="validation",
        sandbox=None,
    )


@task
def gaia_level3():
    """GAIA Level 3 — complex, up to ~50 steps, long-term planning."""
    return _gaia(
        solver=_butler_solver(),
        subset="2023_level3",
        split="validation",
        sandbox=None,
    )


@task
def gaia_dev():
    """GAIA Dev Set — all 166 validation questions across all levels."""
    return _gaia(
        solver=_butler_solver(),
        subset="2023_all",
        split="validation",
        sandbox=None,
    )
