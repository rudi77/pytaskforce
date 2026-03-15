"""Prompt mutator for autoresearch experiments.

Modifies system prompt files in `src/taskforce/core/prompts/`.
Receives full new content from the proposer LLM.
"""

import logging
from pathlib import Path

from evals.autoresearch.models import ExperimentPlan

logger = logging.getLogger(__name__)

# Directories where prompt files may be modified
ALLOWED_PROMPT_DIRS = [
    "src/taskforce/core/prompts/",
]


class PromptMutationError(Exception):
    """Raised when a prompt mutation is invalid."""


class PromptMutator:
    """Modifies system prompt files."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def apply(self, plan: ExperimentPlan) -> list[str]:
        """Apply prompt changes from the experiment plan.

        The plan's FileChange.content contains the full new file content.

        Args:
            plan: Experiment plan with file changes.

        Returns:
            List of modified file paths (relative to project root).

        Raises:
            PromptMutationError: If the target file is outside allowed directories.
        """
        modified: list[str] = []

        for change in plan.files:
            # Validate path is in allowed directories
            if not any(change.path.startswith(d) for d in ALLOWED_PROMPT_DIRS):
                raise PromptMutationError(
                    f"File '{change.path}' is not in an allowed prompt directory. "
                    f"Allowed: {ALLOWED_PROMPT_DIRS}"
                )

            full_path = self.project_root / change.path
            if not full_path.exists():
                raise PromptMutationError(f"Prompt file not found: {change.path}")

            if not change.content.strip():
                raise PromptMutationError("Prompt content cannot be empty")

            # Validate the new content is valid Python if it's a .py file
            if change.path.endswith(".py"):
                self._validate_python(change.content, change.path)

            # Write the new content
            full_path.write_text(change.content)
            modified.append(change.path)
            logger.info("Modified prompt: %s", change.path)

        return modified

    def _validate_python(self, content: str, path: str) -> None:
        """Check that the content is valid Python syntax."""
        try:
            compile(content, path, "exec")
        except SyntaxError as e:
            raise PromptMutationError(f"Syntax error in prompt file {path}: {e}")

    def read_prompt(self, prompt_path: str) -> str:
        """Read a prompt file and return its content."""
        full_path = self.project_root / prompt_path
        if not full_path.exists():
            return f"# File not found: {prompt_path}"
        return full_path.read_text()
