"""Script-based evaluator.

Runs an inline Python script that prints JSON scores to stdout.
Useful for custom evaluation logic without needing a separate file.
"""

import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path

from autooptim.errors import EvaluatorError
from autooptim.metric import ConfigurableMetric
from autooptim.models import EvaluatorConfig, Scores

logger = logging.getLogger(__name__)


class ScriptEvaluator:
    """Evaluator that runs an inline Python script.

    The script is provided in the config YAML and should print
    a JSON object with score names as keys to stdout.
    """

    def __init__(
        self,
        config: EvaluatorConfig,
        project_root: Path,
        metric: ConfigurableMetric,
    ) -> None:
        self.config = config
        self.project_root = project_root
        self.metric = metric

    def evaluate(
        self,
        task_name: str,
        num_runs: int = 1,
        baseline_scores: Scores | None = None,
    ) -> tuple[Scores, float, float]:
        """Run the evaluation script and return results.

        Args:
            task_name: Passed as TASK_NAME env var to the script.
            num_runs: Number of runs to average.
            baseline_scores: Baseline for composite computation.

        Returns:
            Tuple of (averaged_scores, composite_score, estimated_cost).
        """
        all_scores: list[Scores] = []
        total_cost = 0.0

        for run_idx in range(num_runs):
            logger.info("Eval run %d/%d", run_idx + 1, num_runs)
            scores, cost = self._run_single(task_name)
            all_scores.append(scores)
            total_cost += cost

        if not all_scores:
            return Scores(), 0.0, 0.0

        avg = self._average_scores(all_scores)
        composite = self.metric.compute(avg, baseline_scores)

        return avg, composite, total_cost

    def _run_single(self, task_name: str) -> tuple[Scores, float]:
        """Run a single evaluation."""
        if not self.config.script.strip():
            raise EvaluatorError("No evaluation script provided in config")

        # Write script to temp file and execute
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir=str(self.project_root)
        ) as f:
            f.write(self.config.script)
            script_path = f.name

        try:
            import os

            env = os.environ.copy()
            env["TASK_NAME"] = task_name

            result = subprocess.run(
                [sys.executable, script_path],
                cwd=str(self.project_root),
                env=env,
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
            )
        except subprocess.TimeoutExpired:
            logger.error("Eval script timed out after %ds", self.config.timeout)
            return Scores(), 0.0
        finally:
            Path(script_path).unlink(missing_ok=True)

        if result.returncode != 0:
            logger.error(
                "Eval script failed (exit %d): %s",
                result.returncode,
                result.stderr[-1000:],
            )
            return Scores(), 0.0

        # Parse JSON from stdout
        try:
            # Find last JSON object in output
            text = result.stdout.strip()
            last_brace = text.rfind("}")
            first_brace = text.rfind("{", 0, last_brace + 1) if last_brace >= 0 else -1

            if first_brace < 0 or last_brace < 0:
                raise EvaluatorError(f"No JSON in script output:\n{text[:500]}")

            data = json.loads(text[first_brace : last_brace + 1])
            scores = Scores(values={k: float(v) for k, v in data.items()})
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to parse script output: %s", e)
            return Scores(), 0.0

        cost = scores.get("cost_usd", 0.0)
        return scores, cost

    def _average_scores(self, all_scores: list[Scores]) -> Scores:
        """Compute the average of multiple Scores objects."""
        if not all_scores:
            return Scores()

        n = len(all_scores)
        all_keys: set[str] = set()
        for s in all_scores:
            all_keys.update(s.values.keys())

        avg_values: dict[str, float] = {}
        for key in all_keys:
            avg_values[key] = sum(s.get(key) for s in all_scores) / n

        return Scores(values=avg_values)
