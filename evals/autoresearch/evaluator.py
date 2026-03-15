"""Eval wrapper for the autoresearch loop.

Invokes `evals/run_eval.py` as a subprocess and parses Inspect AI
result files to extract per-scorer metrics.
"""

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from evals.autoresearch.metric import compute_composite, scores_from_means
from evals.autoresearch.models import EvalScores

logger = logging.getLogger(__name__)

# Inspect AI default log directory
INSPECT_LOG_DIR = Path.home() / ".inspect" / "logs"


def _find_latest_eval_log(before_ts: float | None = None) -> Path | None:
    """Find the most recent .eval log file from Inspect AI.

    Args:
        before_ts: If set, only consider files created after this timestamp.

    Returns:
        Path to the latest .eval log file, or None if not found.
    """
    log_dirs = [INSPECT_LOG_DIR]

    # Also check local logs/ directory
    local_logs = Path.cwd() / "logs"
    if local_logs.exists():
        log_dirs.append(local_logs)

    candidates: list[Path] = []
    for log_dir in log_dirs:
        if not log_dir.exists():
            continue
        for p in log_dir.rglob("*.eval"):
            if before_ts is not None and p.stat().st_mtime < before_ts:
                continue
            candidates.append(p)

    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _parse_eval_log(log_path: Path) -> EvalScores:
    """Parse an Inspect AI .eval log file and extract scores.

    The .eval file is a JSON file with the evaluation results.
    """
    with open(log_path) as f:
        data = json.load(f)

    results = data.get("results", {})
    scores_dict = results.get("scores", [])

    task_completion = 0.0
    output_accuracy = 0.0
    model_graded_qa = 0.0
    efficiency_steps = 0.0
    efficiency_tokens = 0.0

    for scorer_result in scores_dict:
        name = scorer_result.get("name", "")
        metrics = scorer_result.get("metrics", {})

        if name == "task_completion":
            task_completion = metrics.get("accuracy", {}).get("value", 0.0)
        elif name == "output_contains_target":
            output_accuracy = metrics.get("accuracy", {}).get("value", 0.0)
        elif name == "model_graded_qa":
            # model_graded_qa uses C=1.0, P=0.5, I=0.0
            task_completion_val = metrics.get("accuracy", {}).get("value", 0.0)
            model_graded_qa = task_completion_val
        elif name == "efficiency":
            efficiency_steps = metrics.get("steps", {}).get("value", 0.0)
            efficiency_tokens = metrics.get("total_tokens", {}).get("value", 0.0)

    return EvalScores(
        task_completion=task_completion,
        output_accuracy=output_accuracy,
        model_graded_qa=model_graded_qa,
        efficiency_steps=efficiency_steps,
        efficiency_tokens=efficiency_tokens,
    )


def run_eval(
    task_name: str = "coding_full",
    project_root: Path | None = None,
    extra_args: list[str] | None = None,
) -> tuple[EvalScores, float]:
    """Run a single Inspect AI evaluation and return scores + estimated cost.

    Args:
        task_name: Registered task name (e.g. "coding_full", "coding_generation").
        project_root: Project root directory.
        extra_args: Additional CLI arguments to pass to run_eval.py.

    Returns:
        Tuple of (EvalScores, estimated_cost_usd).
    """
    if project_root is None:
        project_root = Path(__file__).resolve().parents[2]

    run_eval_script = project_root / "evals" / "run_eval.py"
    if not run_eval_script.exists():
        raise FileNotFoundError(f"run_eval.py not found at {run_eval_script}")

    before_ts = time.time()

    cmd = [sys.executable, str(run_eval_script), task_name]
    if extra_args:
        cmd.extend(extra_args)

    logger.info("Running eval: %s", " ".join(cmd))
    env = os.environ.copy()
    result = subprocess.run(
        cmd,
        cwd=str(project_root),
        env=env,
        capture_output=True,
        text=True,
        timeout=600,  # 10 minute timeout per eval run
    )

    if result.returncode != 0:
        logger.error("Eval failed (exit %d): %s", result.returncode, result.stderr[-1000:])
        # Return zero scores on failure
        return EvalScores(), 0.0

    # Parse the result log
    log_path = _find_latest_eval_log(before_ts=before_ts)
    if log_path is None:
        logger.warning("Could not find eval log file after run")
        return EvalScores(), 0.0

    logger.info("Parsing eval log: %s", log_path)
    scores = _parse_eval_log(log_path)

    # Estimate cost from token usage (rough: $0.01 per 1K tokens for GPT-4 class)
    estimated_cost = scores.efficiency_tokens * 0.00001

    return scores, estimated_cost


def run_eval_averaged(
    task_name: str = "coding_full",
    num_runs: int = 2,
    project_root: Path | None = None,
    extra_args: list[str] | None = None,
    baseline_scores: EvalScores | None = None,
) -> tuple[EvalScores, float, float]:
    """Run eval multiple times and return averaged scores.

    Args:
        task_name: Registered task name.
        num_runs: Number of eval runs to average.
        project_root: Project root directory.
        extra_args: Additional CLI arguments.
        baseline_scores: Baseline scores for composite computation.

    Returns:
        Tuple of (averaged_scores, composite_score, total_cost).
    """
    all_scores: list[EvalScores] = []
    total_cost = 0.0

    for run_idx in range(num_runs):
        logger.info("Eval run %d/%d for task %s", run_idx + 1, num_runs, task_name)
        scores, cost = run_eval(task_name, project_root, extra_args)
        all_scores.append(scores)
        total_cost += cost

    if not all_scores:
        return EvalScores(), 0.0, 0.0

    # Average scores across runs
    n = len(all_scores)
    avg = scores_from_means(
        task_completion_mean=sum(s.task_completion for s in all_scores) / n,
        output_accuracy_mean=sum(s.output_accuracy for s in all_scores) / n,
        model_graded_qa_mean=sum(s.model_graded_qa for s in all_scores) / n,
        steps_mean=sum(s.efficiency_steps for s in all_scores) / n,
        tokens_mean=sum(s.efficiency_tokens for s in all_scores) / n,
    )

    composite = compute_composite(avg, baseline_scores)
    return avg, composite, total_cost
