"""PinchBench evaluation tasks for the Taskforce coding agent.

Runs pinchbench task definitions (cloned from https://github.com/pinchbench/skill)
against the Taskforce agent. Unlike the upstream pinchbench runner, this
integration does NOT depend on the ``openclaw`` CLI — pinchbench's
task markdowns supply the prompt, fixtures, and (where present) Python
``grade()`` functions, and we orchestrate execution + scoring ourselves
through Inspect AI.

Prerequisites:
    - ``uv sync --extra evals`` (Inspect AI)
    - git (used by ``loader.ensure_skill_checkout`` to fetch the
      pinchbench skill repo on first run)
    - LLM provider credentials for the chosen ``--model`` (Azure / OpenAI
      / OpenRouter / Anthropic — set in ``.env``)

Usage:
    # Smoke test — first 5 core tasks
    python evals/run_eval.py pinchbench_smoke

    # ~25 representative core tasks
    python evals/run_eval.py pinchbench_core

    # Single category
    python evals/run_eval.py pinchbench_coding
    python evals/run_eval.py pinchbench_productivity

    # Everything (~180 tasks, slow)
    python evals/run_eval.py pinchbench_full
"""

from __future__ import annotations

from inspect_ai import Task, task
from inspect_ai.dataset import Sample

from evals.bridge.azure_config import setup_azure_env
from evals.pinchbench.loader import PinchbenchTask, load_tasks
from evals.pinchbench.scorer import pinchbench_scorer
from evals.pinchbench.solver import pinchbench_solver

setup_azure_env()


def _sample_from_task(t: PinchbenchTask) -> Sample:
    """Lower a parsed task into an Inspect AI Sample.

    All grader inputs (rubric, automated grade source, grading type) ride
    along in ``metadata`` so the scorer can recover them without re-parsing
    the markdown.
    """
    return Sample(
        input=t.prompt,
        target=t.expected_behavior,
        id=t.id,
        metadata={
            "pinchbench_task_id": t.id,
            "pinchbench_category": t.category,
            "pinchbench_grading_type": t.grading_type,
            "pinchbench_timeout_seconds": t.timeout_seconds,
            "pinchbench_workspace_files": t.workspace_files,
            "pinchbench_prompt": t.prompt,
            "pinchbench_expected_behavior": t.expected_behavior,
            "pinchbench_grading_criteria": t.grading_criteria,
            "pinchbench_rubric": t.llm_judge_rubric,
            "pinchbench_grade_function": t.grade_function,
        },
    )


def _build_task(suite: str, *, limit: int | None = None) -> Task:
    tasks = load_tasks(suite, limit=limit)
    if not tasks:
        raise RuntimeError(
            f"No pinchbench tasks matched suite={suite!r}. "
            "Check evals/pinchbench/skill/tasks/ or pass a valid category."
        )
    samples = [_sample_from_task(t) for t in tasks]
    return Task(
        dataset=samples,
        solver=pinchbench_solver(),
        scorer=pinchbench_scorer(),
    )


@task
def pinchbench_smoke() -> Task:
    """Five core tasks for a quick smoke test."""
    return _build_task("core", limit=5)


@task
def pinchbench_core() -> Task:
    """Core suite — ~25 representative tasks across all categories."""
    return _build_task("core")


@task
def pinchbench_full() -> Task:
    """Full pinchbench benchmark (~180 tasks, slow)."""
    return _build_task("all")


# ----- Per-category convenience tasks (match upstream manifest categories) -----


@task
def pinchbench_productivity() -> Task:
    """Calendar, PDF conversion, todos, summaries."""
    return _build_task("productivity")


@task
def pinchbench_research() -> Task:
    """Market analysis, competitive intelligence, policy research."""
    return _build_task("research")


@task
def pinchbench_writing() -> Task:
    """Email, blog posts, documentation, commit messages."""
    return _build_task("writing")


@task
def pinchbench_coding() -> Task:
    """Debugging, refactoring, automation, code generation."""
    return _build_task("coding")


@task
def pinchbench_analysis() -> Task:
    """Summarization, anomaly detection, financial analysis."""
    return _build_task("analysis")


@task
def pinchbench_csv_analysis() -> Task:
    """CSV data trends, statistical analysis, rankings."""
    return _build_task("csv_analysis")


@task
def pinchbench_log_analysis() -> Task:
    """Server / SSH / HDFS / MapReduce / system log analysis."""
    return _build_task("log_analysis")


@task
def pinchbench_meeting_analysis() -> Task:
    """Meeting transcript summarization, vote extraction, follow-ups."""
    return _build_task("meeting_analysis")


@task
def pinchbench_memory() -> Task:
    """Knowledge retention operations across sessions."""
    return _build_task("memory")


@task
def pinchbench_skills() -> Task:
    """File operations, workflow, discovery."""
    return _build_task("skills")
