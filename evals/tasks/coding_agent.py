"""Coding Agent benchmark tasks for Inspect AI.

Evaluates the Taskforce coding agent across multiple dimensions:
- Code generation quality
- Bug fixing ability
- Refactoring skill
- Test writing
- Code analysis

Usage (Azure GPT models):
    # Run all coding benchmarks (uses Azure deployment from .env)
    inspect eval evals/tasks/coding_agent.py --model openai/azure/gpt-5.2

    # Run a specific task
    inspect eval evals/tasks/coding_agent.py@coding_generation --model openai/azure/gpt-4.1

    # Compare planning strategies
    inspect eval evals/tasks/coding_agent.py@coding_spar --model openai/azure/gpt-5-mini
    inspect eval evals/tasks/coding_agent.py@coding_react --model openai/azure/gpt-5-mini

Environment:
    Requires AZURE_API_KEY, AZURE_API_BASE, AZURE_API_VERSION in .env
    (auto-mapped to Inspect AI's AZUREAI_OPENAI_* convention).
"""

from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset
from inspect_ai.scorer import model_graded_qa

from evals.bridge.azure_config import setup_azure_env
from evals.bridge.taskforce_bridge import taskforce_solver
from evals.scorers.taskforce_scorers import (
    efficiency,
    output_contains_target,
    task_completion,
)

# Auto-configure Azure env vars for Inspect AI on import
setup_azure_env()

DATASET_PATH = str(Path(__file__).resolve().parents[1] / "datasets" / "coding_tasks.jsonl")

# Grading template designed for AI coding agent output.
# The agent returns a mix of explanation text and code - the judge must
# evaluate the ENTIRE response (not just isolated code blocks).
CODING_QUALITY_TEMPLATE = """You are an expert code reviewer evaluating an AI coding agent's response.

The agent was given a coding task and produced the response below. The response
may contain a mix of explanation, code snippets, file paths, and reasoning.
Your job is to assess whether the agent SOLVED the task correctly.

[BEGIN TASK]
{question}
[END TASK]

[BEGIN AGENT RESPONSE]
{answer}
[END AGENT RESPONSE]

[EVALUATION CRITERIA]
The response should demonstrate: {criterion}

Grade the response on these dimensions:
1. **Correctness**: Does the solution solve the stated task? Would the code work if executed?
2. **Completeness**: Are all requirements addressed? Nothing important missing?
3. **Quality**: Is the code well-structured with proper naming, type hints, docstrings?
4. **Understanding**: Does the agent show understanding of the problem domain?

IMPORTANT: The agent is an autonomous coding agent that uses tools (file read/write,
shell commands, etc.) to accomplish tasks. Its response is a SUMMARY of what it did,
not necessarily raw code. Evaluate based on whether the task was accomplished correctly,
even if the response includes tool usage logs or explanatory text alongside code.

Assign exactly ONE grade:
- GRADE: C  — Correct: Task solved correctly with good code quality
- GRADE: P  — Partial: Task partially solved, or solved with quality issues
- GRADE: I  — Incorrect: Task not solved, or fundamentally flawed approach

You MUST end your evaluation with exactly one of these lines:
GRADE: C
GRADE: P
GRADE: I
"""


def _default_scorers():
    """Build the standard scorer list for coding tasks."""
    return [
        task_completion(),
        output_contains_target(),
        model_graded_qa(
            template=CODING_QUALITY_TEMPLATE,
            grade_pattern=r"GRADE:\s*(C|P|I)",
        ),
        efficiency(),
    ]


@task
def coding_full():
    """Full coding agent benchmark - all task categories."""
    return Task(
        dataset=json_dataset(DATASET_PATH, FieldSpec(input="input", target="target")),
        solver=taskforce_solver(profile="coding_agent"),
        scorer=_default_scorers(),
    )


@task
def coding_generation():
    """Benchmark: code generation tasks only."""
    dataset = json_dataset(DATASET_PATH, FieldSpec(input="input", target="target"))
    filtered = dataset.filter(lambda s: s.metadata.get("category") == "code_generation")
    return Task(
        dataset=filtered,
        solver=taskforce_solver(profile="coding_agent"),
        scorer=_default_scorers(),
    )


@task
def coding_bugfix():
    """Benchmark: bug fixing tasks only."""
    dataset = json_dataset(DATASET_PATH, FieldSpec(input="input", target="target"))
    filtered = dataset.filter(lambda s: s.metadata.get("category") == "bug_fix")
    return Task(
        dataset=filtered,
        solver=taskforce_solver(profile="coding_agent"),
        scorer=_default_scorers(),
    )


@task
def coding_analysis():
    """Benchmark: code analysis and review tasks."""
    dataset = json_dataset(DATASET_PATH, FieldSpec(input="input", target="target"))
    filtered = dataset.filter(
        lambda s: s.metadata.get("category") in ("analysis", "testing")
    )
    return Task(
        dataset=filtered,
        solver=taskforce_solver(profile="coding_agent"),
        scorer=_default_scorers(),
    )


# --- Planning Strategy Comparison ---


@task
def coding_spar():
    """Benchmark with SPAR planning strategy (default for coding_agent)."""
    return Task(
        dataset=json_dataset(DATASET_PATH, FieldSpec(input="input", target="target")),
        solver=taskforce_solver(profile="coding_agent", planning_strategy="spar"),
        scorer=_default_scorers(),
    )


@task
def coding_react():
    """Benchmark with native ReAct planning strategy."""
    return Task(
        dataset=json_dataset(DATASET_PATH, FieldSpec(input="input", target="target")),
        solver=taskforce_solver(
            profile="coding_agent", planning_strategy="native_react"
        ),
        scorer=_default_scorers(),
    )


@task
def coding_plan_and_execute():
    """Benchmark with Plan-and-Execute planning strategy."""
    return Task(
        dataset=json_dataset(DATASET_PATH, FieldSpec(input="input", target="target")),
        solver=taskforce_solver(
            profile="coding_agent", planning_strategy="plan_and_execute"
        ),
        scorer=_default_scorers(),
    )
