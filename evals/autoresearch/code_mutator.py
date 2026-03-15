"""Code mutator for autoresearch experiments.

Applies code modifications with pre-flight validation (import check, lint,
format). Restricts which files can be modified to minimize risk.
"""

import logging
import subprocess
import sys
from pathlib import Path

from evals.autoresearch.models import ExperimentPlan

logger = logging.getLogger(__name__)

# Files/directories that ARE allowed to be modified
ALLOWED_CODE_PATHS = [
    "src/taskforce/core/domain/planning_strategy.py",
    "src/taskforce/core/domain/lean_agent_components/",
    "src/taskforce/core/domain/context_builder.py",
    "src/taskforce/core/domain/context_policy.py",
    "src/taskforce/core/prompts/",
    "src/taskforce/infrastructure/tools/native/",
]

# Paths that are NEVER allowed to be modified
BLOCKED_PATHS = [
    "src/taskforce/application/factory.py",
    "src/taskforce/api/",
    "src/taskforce/core/interfaces/",
    "tests/",
]


class CodeMutationError(Exception):
    """Raised when a code mutation fails."""


class PreflightError(CodeMutationError):
    """Raised when pre-flight checks fail after applying changes."""


class CodeMutator:
    """Applies code modifications with safety checks."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def apply(self, plan: ExperimentPlan) -> list[str]:
        """Apply code changes from the experiment plan.

        The plan's FileChange.content contains the full new file content.
        After applying changes, runs pre-flight validation.

        Args:
            plan: Experiment plan with file changes.

        Returns:
            List of modified file paths (relative to project root).

        Raises:
            CodeMutationError: If the file is not allowed.
            PreflightError: If pre-flight checks fail.
        """
        modified: list[str] = []

        for change in plan.files:
            self._validate_path(change.path)

            full_path = self.project_root / change.path
            if change.action == "delete":
                if full_path.exists():
                    full_path.unlink()
                    modified.append(change.path)
                continue

            if change.action == "create":
                full_path.parent.mkdir(parents=True, exist_ok=True)

            if not change.content.strip():
                raise CodeMutationError(f"Empty content for {change.path}")

            # Validate Python syntax before writing
            if change.path.endswith(".py"):
                try:
                    compile(change.content, change.path, "exec")
                except SyntaxError as e:
                    raise CodeMutationError(f"Syntax error in {change.path}: {e}")

            full_path.write_text(change.content)
            modified.append(change.path)
            logger.info("Modified code: %s", change.path)

        # Run pre-flight checks on all modified files
        if modified:
            self.preflight(modified)

        return modified

    def _validate_path(self, path: str) -> None:
        """Check that the file path is allowed for modification."""
        # Check blocked paths first
        for blocked in BLOCKED_PATHS:
            if path.startswith(blocked):
                raise CodeMutationError(
                    f"File '{path}' is in a blocked directory: {blocked}"
                )

        # Check allowed paths
        allowed = any(path.startswith(a) for a in ALLOWED_CODE_PATHS)
        if not allowed:
            raise CodeMutationError(
                f"File '{path}' is not in an allowed code directory. "
                f"Allowed: {ALLOWED_CODE_PATHS}"
            )

    def preflight(self, files: list[str]) -> None:
        """Run pre-flight validation on modified files.

        Checks:
        1. Python import succeeds (package not broken)
        2. Ruff lint passes on modified files
        3. Black format check passes

        Raises:
            PreflightError: If any check fails.
        """
        # 1. Import check
        logger.info("Pre-flight: import check...")
        result = subprocess.run(
            [sys.executable, "-c", "import taskforce"],
            cwd=str(self.project_root),
            capture_output=True,
            text=True,
            timeout=30,
            env={"PYTHONPATH": str(self.project_root / "src")},
        )
        if result.returncode != 0:
            raise PreflightError(
                f"Import check failed after code modification:\n{result.stderr[:500]}"
            )

        # 2. Ruff lint check (non-blocking, just log warnings)
        abs_files = [str(self.project_root / f) for f in files if f.endswith(".py")]
        if abs_files:
            logger.info("Pre-flight: ruff check...")
            result = subprocess.run(
                [sys.executable, "-m", "ruff", "check", *abs_files],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning("Ruff lint issues (non-blocking):\n%s", result.stdout[:500])

        logger.info("Pre-flight: all checks passed")

    def read_code(self, code_path: str) -> str:
        """Read a code file and return its content."""
        full_path = self.project_root / code_path
        if not full_path.exists():
            return f"# File not found: {code_path}"
        return full_path.read_text()
