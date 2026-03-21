"""Text/prompt file mutator.

Modifies text files (prompts, markdown, etc.) with full content replacement.
Validates Python syntax for .py files.
"""

import logging
from pathlib import Path

from autooptim.errors import MutationError
from autooptim.models import ExperimentPlan, MutatorConfig
from autooptim.mutators.base import BaseMutator

logger = logging.getLogger(__name__)


class TextMutator(BaseMutator):
    """Modifies text files with full content replacement.

    Suitable for prompt files, markdown, configuration templates, etc.
    Validates Python syntax if the file ends with .py.
    """

    def __init__(self, project_root: Path, config: MutatorConfig) -> None:
        super().__init__(project_root, config)

    def apply(self, plan: ExperimentPlan) -> list[str]:
        """Apply text changes from the experiment plan.

        Args:
            plan: Experiment plan with file changes (content = full new content).

        Returns:
            List of modified file paths.

        Raises:
            MutationError: If file is outside allowed directories or content is empty.
        """
        modified: list[str] = []

        for change in plan.files:
            self._check_path(change.path)

            full_path = self.project_root / change.path
            if not full_path.exists() and change.action != "create":
                raise MutationError(f"File not found: {change.path}")

            if not change.content.strip():
                raise MutationError("File content cannot be empty")

            # Validate Python syntax for .py files
            if change.path.endswith(".py"):
                try:
                    compile(change.content, change.path, "exec")
                except SyntaxError as e:
                    raise MutationError(f"Syntax error in {change.path}: {e}")

            if change.action == "create":
                full_path.parent.mkdir(parents=True, exist_ok=True)

            full_path.write_text(change.content, encoding="utf-8")
            modified.append(change.path)
            logger.info("Modified text: %s", change.path)

        return modified
