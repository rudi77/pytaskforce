"""Composite metric computation for autoresearch experiments.

Combines quality and efficiency scores into a single scalar for
keep/discard decisions.
"""

from evals.autoresearch.models import EvalScores


def compute_composite(
    scores: EvalScores,
    baseline_scores: EvalScores | None = None,
) -> float:
    """Compute weighted composite metric. Higher is better.

    Quality metrics are weighted heavily (90%). Efficiency is a small
    bonus (up to 10%), normalized relative to baseline.

    Args:
        scores: Current experiment scores.
        baseline_scores: Baseline scores for efficiency normalization.

    Returns:
        Composite score in range [0.0, ~1.1].
    """
    quality = (
        0.50 * scores.task_completion
        + 0.25 * scores.output_accuracy
        + 0.25 * scores.model_graded_qa
    )

    if baseline_scores is not None and baseline_scores.efficiency_steps > 0:
        step_ratio = baseline_scores.efficiency_steps / max(scores.efficiency_steps, 1)
        token_ratio = baseline_scores.efficiency_tokens / max(scores.efficiency_tokens, 1)
        # Cap ratios to avoid outsized bonus from extremely low usage
        efficiency_bonus = 0.05 * min(step_ratio, 2.0) + 0.05 * min(token_ratio, 2.0)
    else:
        efficiency_bonus = 0.1  # neutral when no baseline

    return quality + efficiency_bonus


def scores_from_means(
    task_completion_mean: float,
    output_accuracy_mean: float,
    model_graded_qa_mean: float,
    steps_mean: float,
    tokens_mean: float,
) -> EvalScores:
    """Convenience constructor from mean values across eval runs."""
    return EvalScores(
        task_completion=task_completion_mean,
        output_accuracy=output_accuracy_mean,
        model_graded_qa=model_graded_qa_mean,
        efficiency_steps=steps_mean,
        efficiency_tokens=tokens_mean,
    )
