"""Custom score parser for Inspect AI evaluation logs.

Parses .eval JSON files produced by Inspect AI to extract
Taskforce-specific scores.
"""

import json
import logging
from pathlib import Path
from typing import Any

from autooptim.errors import EvaluatorError
from autooptim.models import Scores

logger = logging.getLogger(__name__)

# Inspect AI default log directory
INSPECT_LOG_DIR = Path.home() / ".inspect" / "logs"


class InspectAIParser:
    """Parses Inspect AI .eval log files into AutoOptim Scores.

    Instead of parsing stdout, this parser finds the latest .eval log file
    and extracts scorer metrics from its JSON structure.
    """

    def __init__(self, before_ts: float | None = None) -> None:
        self.before_ts = before_ts

    def parse(self, raw_output: str | dict) -> Scores:
        """Parse the latest Inspect AI log file.

        The raw_output parameter is ignored — we find the .eval file directly.
        """
        log_path = self._find_latest_eval_log()
        if log_path is None:
            logger.warning("Could not find eval log file")
            return Scores()

        logger.info("Parsing eval log: %s", log_path)
        return self._parse_eval_log(log_path)

    def set_before_ts(self, ts: float) -> None:
        """Set the timestamp filter for finding log files."""
        self.before_ts = ts

    def _find_latest_eval_log(self) -> Path | None:
        """Find the most recent .eval log file from Inspect AI."""
        log_dirs = [INSPECT_LOG_DIR]

        local_logs = Path.cwd() / "logs"
        if local_logs.exists():
            log_dirs.append(local_logs)

        candidates: list[Path] = []
        for log_dir in log_dirs:
            if not log_dir.exists():
                continue
            for p in log_dir.rglob("*.eval"):
                if self.before_ts is not None and p.stat().st_mtime < self.before_ts:
                    continue
                candidates.append(p)

        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_mtime)

    def _parse_eval_log(self, log_path: Path) -> Scores:
        """Parse an Inspect AI .eval log file and extract scores."""
        with open(log_path) as f:
            data = json.load(f)

        results = data.get("results", {})
        scores_list = results.get("scores", [])

        values: dict[str, float] = {}

        for scorer_result in scores_list:
            name = scorer_result.get("name", "")
            metrics = scorer_result.get("metrics", {})

            if name == "task_completion":
                values["task_completion"] = metrics.get("accuracy", {}).get("value", 0.0)
            elif name == "output_contains_target":
                values["output_accuracy"] = metrics.get("accuracy", {}).get("value", 0.0)
            elif name == "model_graded_qa":
                values["model_graded_qa"] = metrics.get("accuracy", {}).get("value", 0.0)
            elif name == "efficiency":
                values["efficiency_steps"] = metrics.get("steps", {}).get("value", 0.0)
                values["efficiency_tokens"] = metrics.get("total_tokens", {}).get("value", 0.0)

        return Scores(values=values)
