"""InstructEval-style benchmarks via inspect-evals.

Tests the base model capabilities that underpin the Taskforce agent:
- MMLU: Knowledge and reasoning across 57 academic domains
- HumanEval: Python code generation (164 problems)
- GPQA: Graduate-level science Q&A
- ARC: Science reasoning

These benchmarks test the MODEL (not the agent framework), serving as
a baseline to validate that the chosen LLM is capable enough for
agent tasks.

Usage:
    python evals/run_eval.py mmlu_5shot --model openai/azure/gpt-4.1
    python evals/run_eval.py humaneval --model openai/azure/gpt-5-mini
    python evals/run_eval.py gpqa --model openai/azure/gpt-5.2

Environment:
    Requires AZURE_API_KEY, AZURE_API_BASE, AZURE_API_VERSION in .env
"""

from inspect_ai import Task, task
from inspect_evals.arc import arc_challenge
from inspect_evals.gpqa import gpqa_diamond
from inspect_evals.humaneval import humaneval as _humaneval
from inspect_evals.mmlu import mmlu_0_shot, mmlu_5_shot

from evals.bridge.azure_config import setup_azure_env

setup_azure_env()


# --- MMLU (Massive Multitask Language Understanding) ---


@task
def mmlu_0shot():
    """MMLU 0-shot: 57 academic subjects, no examples.

    Tests raw knowledge without in-context learning.
    ~14,000 questions.
    """
    return mmlu_0_shot()


@task
def mmlu_5shot():
    """MMLU 5-shot: 57 academic subjects with 5 examples each.

    Standard MMLU benchmark configuration.
    ~14,000 questions.
    """
    return mmlu_5_shot()


# --- HumanEval (Code Generation) ---


@task
def humaneval():
    """HumanEval: 164 Python coding problems, 0-shot.

    Measures pass@1 code generation accuracy.
    Tests function-level code completion.
    """
    return _humaneval()


# --- GPQA (Graduate-level Q&A) ---


@task
def gpqa():
    """GPQA Diamond: Expert-level science questions.

    Graduate-level physics, chemistry, and biology questions
    validated by domain experts. ~198 questions.
    """
    return gpqa_diamond()


# --- ARC (AI2 Reasoning Challenge) ---


@task
def arc():
    """ARC Challenge: Grade-school science reasoning.

    Multiple-choice science questions requiring reasoning.
    ~1,172 questions in the challenge set.
    """
    return arc_challenge()
