"""TSV-based experiment log for the optimization loop.

Writes experiment results to a TSV file outside the git-managed area
so that git resets (on discarded experiments) do not lose the log.

Adapts dynamically to whatever score names are present in the Scores object.
"""

import csv
import json
from datetime import datetime
from pathlib import Path

from autooptim.models import ExperimentResult, ExperimentStatus, Scores

# Fixed columns that are always present
FIXED_COLUMNS = [
    "experiment_id",
    "timestamp",
    "category",
    "description",
    "hypothesis",
    "git_sha",
    "status",
    "composite_score",
    "baseline_composite",
    "delta",
    "eval_runs",
    "eval_cost_usd",
    "files_modified",
    "duration_seconds",
    "scores_json",
]


class ExperimentLog:
    """Read/write experiment results as TSV with dynamic score columns."""

    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _ensure_header(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists() or self.log_path.stat().st_size == 0:
            with open(self.log_path, "w", newline="") as f:
                writer = csv.writer(f, delimiter="\t")
                writer.writerow(FIXED_COLUMNS)

    def append(self, result: ExperimentResult) -> None:
        """Append a single experiment result to the log."""
        self._ensure_header()
        with open(self.log_path, "a", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow([
                result.experiment_id,
                result.timestamp.isoformat(),
                result.category,
                result.description,
                result.hypothesis,
                result.git_sha,
                result.status.value,
                f"{result.composite_score:.4f}",
                f"{result.baseline_composite:.4f}",
                f"{result.composite_score - result.baseline_composite:.4f}",
                result.eval_runs,
                f"{result.eval_cost_usd:.4f}",
                ";".join(result.files_modified),
                f"{result.duration_seconds:.1f}",
                json.dumps(result.scores.values),
            ])

    def read_all(self) -> list[ExperimentResult]:
        """Read all experiment results from the log."""
        if not self.log_path.exists():
            return []

        results: list[ExperimentResult] = []
        with open(self.log_path, newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                scores_json = row.get("scores_json", "{}")
                try:
                    scores_values = json.loads(scores_json)
                except (json.JSONDecodeError, TypeError):
                    scores_values = {}

                result = ExperimentResult(
                    experiment_id=int(row["experiment_id"]),
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    category=row["category"],
                    description=row["description"],
                    hypothesis=row["hypothesis"],
                    git_sha=row["git_sha"],
                    status=ExperimentStatus(row["status"]),
                    scores=Scores(values=scores_values),
                    composite_score=float(row["composite_score"]),
                    baseline_composite=float(row["baseline_composite"]),
                    eval_runs=int(row["eval_runs"]),
                    eval_cost_usd=float(row["eval_cost_usd"]),
                    files_modified=(
                        row["files_modified"].split(";") if row["files_modified"] else []
                    ),
                    duration_seconds=float(row["duration_seconds"]),
                )
                results.append(result)
        return results

    def next_experiment_id(self) -> int:
        """Return the next experiment ID based on existing log entries."""
        results = self.read_all()
        if not results:
            return 0
        return max(r.experiment_id for r in results) + 1

    def total_cost(self) -> float:
        """Return total eval cost accumulated so far."""
        return sum(r.eval_cost_usd for r in self.read_all())

    def summary_text(self, score_names: list[str] | None = None) -> str:
        """Return a text summary of the experiment log for the proposer LLM.

        Args:
            score_names: Optional list of score names to include in the summary.
                        If None, includes all scores from each result.
        """
        results = self.read_all()
        if not results:
            return "No experiments have been run yet."

        lines = ["# Experiment History", ""]
        for r in results:
            delta = r.composite_score - r.baseline_composite
            sign = "+" if delta >= 0 else ""

            # Format scores
            if score_names:
                score_parts = [
                    f"{name}={r.scores.get(name):.4f}" for name in score_names
                ]
            else:
                score_parts = [f"{k}={v:.4f}" for k, v in r.scores.values.items()]
            scores_str = ", ".join(score_parts) if score_parts else "no scores"

            lines.append(
                f"- Exp #{r.experiment_id} [{r.category}] {r.status.value}: "
                f"{r.description} | composite={r.composite_score:.4f} "
                f"({sign}{delta:.4f}) | {scores_str} | "
                f"files: {', '.join(r.files_modified)}"
            )
        return "\n".join(lines)
