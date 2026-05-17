"""Inspect AI scorer applying pinchbench's hybrid grading model.

Per-task ``grading_type`` decides the scoring path:

  * ``automated``  → run the ``def grade(transcript, workspace_path)`` function
    embedded in the task's markdown inside a subprocess; aggregate the
    returned criterion scores by mean.
  * ``llm_judge``  → call a Taskforce-spawned LLM judge with the task's
    rubric and the rendered transcript.
  * ``hybrid``     → run both; the final score is the mean of the
    automated mean and the judge score (matching pinchbench's intent
    that both signals must agree for full credit).
"""

from __future__ import annotations

import logging
from pathlib import Path

from inspect_ai.scorer import (
    Score,
    Scorer,
    Target,
    mean,
    scorer,
    stderr,
)
from inspect_ai.solver import TaskState

from evals.pinchbench.grading import (
    aggregate_scores,
    run_automated_check,
    run_llm_judge,
)

logger = logging.getLogger(__name__)


@scorer(metrics=[mean(), stderr()])
def pinchbench_scorer() -> Scorer:
    """Score a pinchbench sample using the hybrid grading policy."""

    async def score(state: TaskState, target: Target) -> Score:  # noqa: ARG001
        meta = state.metadata or {}
        transcript = meta.get("pinchbench_transcript") or []
        workspace_path = Path(meta.get("pinchbench_workspace") or ".")
        grading_type = str(meta.get("pinchbench_grading_type") or "llm_judge").lower()
        grade_source = str(meta.get("pinchbench_grade_function") or "")
        rubric = str(meta.get("pinchbench_rubric") or "")
        expected = str(meta.get("pinchbench_expected_behavior") or "")
        criteria = str(meta.get("pinchbench_grading_criteria") or "")
        prompt = str(meta.get("pinchbench_prompt") or state.input_text or "")
        task_id = str(meta.get("pinchbench_task_id") or "")

        if meta.get("pinchbench_status") == "error":
            return Score(
                value=0.0,
                answer="",
                explanation=f"agent execution failed: {meta.get('pinchbench_error', '')}",
                metadata={"pinchbench_task_id": task_id, "phase": "agent"},
            )

        components: dict[str, float] = {}
        details: dict[str, object] = {"task_id": task_id, "grading_type": grading_type}

        if grading_type in {"automated", "hybrid"} and grade_source:
            auto = run_automated_check(grade_source, transcript, workspace_path)
            if auto.get("ok"):
                scores = auto.get("scores") or {}
                components["automated"] = aggregate_scores(scores)
                details["automated_scores"] = scores
            else:
                details["automated_error"] = auto.get("error", "unknown")
                # Hybrid: don't outright fail; fall through to judge.
                if grading_type == "automated":
                    return Score(
                        value=0.0,
                        answer="",
                        explanation=f"automated check failed: {auto.get('error', '')}",
                        metadata=details,
                    )

        if grading_type in {"llm_judge", "hybrid"}:
            judge = await run_llm_judge(
                prompt=prompt,
                transcript=transcript,
                rubric=rubric,
                expected_behavior=expected,
                grading_criteria=criteria,
            )
            if judge.get("ok"):
                components["judge"] = float(judge.get("score", 0.0))
                details["judge_reasoning"] = judge.get("reasoning", "")
            else:
                details["judge_error"] = judge.get("error", "unknown")

        if not components:
            return Score(
                value=0.0,
                answer="",
                explanation=f"no usable grader for task {task_id}: {details}",
                metadata=details,
            )

        final = sum(components.values()) / len(components)
        details["components"] = components

        return Score(
            value=final,
            answer=state.output.completion if state.output else "",
            explanation=(
                f"{task_id} [{grading_type}] score={final:.3f} "
                f"components={components}"
            ),
            metadata=details,
        )

    return score
