"""Code file mutator.

Applies code modifications with pre-flight validation.
Allowed/blocked paths and preflight commands come from config.
"""

import logging
from pathlib import Path

from autooptim.errors import MutationError
from autooptim.models import ExperimentPlan, MutatorConfig
from autooptim.mutators.base import BaseMutator

logger = logging.getLogger(__name__)


class CodeMutator(BaseMutator):
    """Applies code modifications with safety checks.

    Validates paths against config-driven allowed/blocked lists,
    checks syntax before writing, and runs configurable preflight commands.
    """

    def __init__(self, project_root: Path, config: MutatorConfig) -> None:
        super().__init__(project_root, config)

    def apply(self, plan: ExperimentPlan) -> list[str]:
        """Apply code changes from the experiment plan.

        Args:
            plan: Experiment plan with file changes (content = full file content).

        Returns:
            List of modified file paths.

        Raises:
            MutationError: If file path is not allowed or content is invalid.
            PreflightError: If pre-flight checks fail.
        """
        modified: list[str] = []

        for change in plan.files:
            self._check_path(change.path)

            full_path = self.project_root / change.path

            if change.action == "delete":
                if full_path.exists():
                    full_path.unlink()
                    modified.append(change.path)
                continue

            if change.action == "create":
                full_path.parent.mkdir(parents=True, exist_ok=True)

            if not change.content.strip():
                raise MutationError(f"Empty content for {change.path}")

            # Validate Python syntax before writing
            if change.path.endswith(".py"):
                try:
                    compile(change.content, change.path, "exec")
                except SyntaxError as e:
                    raise MutationError(f"Syntax error in {change.path}: {e}")

            full_path.write_text(change.content)
            modified.append(change.path)
            logger.info("Modified code: %s", change.path)

        # Run pre-flight checks on all modified files
        if modified:
            self.run_preflight(modified)

        return modified
