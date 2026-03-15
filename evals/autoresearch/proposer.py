"""LLM-based experiment proposer for autoresearch.

Uses LiteLLM directly (not through Taskforce agent) to generate
experiment proposals. This avoids circular dependencies since the
autoresearch loop modifies the Taskforce system itself.
"""

import json
import logging
import random
from pathlib import Path

import litellm

from evals.autoresearch.config_mutator import ConfigMutator
from evals.autoresearch.code_mutator import CodeMutator
from evals.autoresearch.experiment_log import ExperimentLog
from evals.autoresearch.models import (
    EvalScores,
    ExperimentCategory,
    ExperimentPlan,
    FileChange,
    RunConfig,
)
from evals.autoresearch.prompt_mutator import PromptMutator

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

# Files to include as context for each category
CATEGORY_CONTEXT_FILES: dict[ExperimentCategory, list[str]] = {
    ExperimentCategory.CONFIG: [
        "src/taskforce/configs/dev.yaml",
        "src/taskforce/configs/coding_agent.yaml",
    ],
    ExperimentCategory.PROMPT: [
        "src/taskforce/core/prompts/autonomous_prompts.py",
        "src/taskforce/core/prompts/prompt_builder.py",
    ],
    ExperimentCategory.CODE: [
        "src/taskforce/core/domain/planning_strategy.py",
        "src/taskforce/core/domain/context_policy.py",
        "src/taskforce/core/domain/context_builder.py",
    ],
}


class ProposerError(Exception):
    """Raised when the proposer fails to generate a valid plan."""


class ExperimentProposer:
    """Generates experiment proposals using an LLM."""

    def __init__(
        self,
        project_root: Path,
        config: RunConfig,
        experiment_log: ExperimentLog,
    ) -> None:
        self.project_root = project_root
        self.config = config
        self.log = experiment_log
        self.config_mutator = ConfigMutator(project_root)
        self.prompt_mutator = PromptMutator(project_root)
        self.code_mutator = CodeMutator(project_root)

    def select_category(self) -> ExperimentCategory:
        """Select experiment category using weighted random selection."""
        categories = self.config.categories
        weights = [self.config.category_weights.get(c, 0.0) for c in categories]
        total = sum(weights)
        if total == 0:
            return random.choice(categories)
        return random.choices(categories, weights=weights, k=1)[0]

    def _read_file(self, path: str) -> str:
        """Read a file from the project root."""
        full_path = self.project_root / path
        if not full_path.exists():
            return f"# File not found: {path}"
        content = full_path.read_text()
        # Truncate very large files
        if len(content) > 8000:
            content = content[:8000] + "\n\n... (truncated) ..."
        return content

    def _build_context(
        self,
        category: ExperimentCategory,
        baseline_scores: EvalScores,
    ) -> tuple[str, str]:
        """Build system and user prompts for the proposer LLM.

        Returns:
            Tuple of (system_prompt, user_prompt).
        """
        system_prompt = (PROMPTS_DIR / "proposer_system.md").read_text()
        user_template = (PROMPTS_DIR / "proposer_user.md").read_text()

        # Build current file state
        context_files = CATEGORY_CONTEXT_FILES.get(category, [])
        file_sections: list[str] = []
        for fp in context_files:
            content = self._read_file(fp)
            file_sections.append(f"### {fp}\n```\n{content}\n```")
        current_files = "\n\n".join(file_sections) if file_sections else "No files to show."

        # Build experiment history
        experiment_history = self.log.summary_text()

        user_prompt = user_template.format(
            category=category.value,
            experiment_history=experiment_history,
            baseline_composite=baseline_scores.task_completion * 0.5
            + baseline_scores.output_accuracy * 0.25
            + baseline_scores.model_graded_qa * 0.25
            + 0.1,
            baseline_task_completion=baseline_scores.task_completion,
            baseline_output_accuracy=baseline_scores.output_accuracy,
            baseline_model_graded_qa=baseline_scores.model_graded_qa,
            baseline_steps=baseline_scores.efficiency_steps,
            baseline_tokens=baseline_scores.efficiency_tokens,
            current_files=current_files,
        )

        return system_prompt, user_prompt

    def propose(
        self,
        baseline_scores: EvalScores,
        category: ExperimentCategory | None = None,
    ) -> ExperimentPlan:
        """Generate an experiment proposal.

        Args:
            baseline_scores: Current baseline scores.
            category: Force a specific category (or None for weighted random).

        Returns:
            ExperimentPlan with proposed changes.

        Raises:
            ProposerError: If the LLM fails to generate a valid plan.
        """
        if category is None:
            category = self.select_category()

        system_prompt, user_prompt = self._build_context(category, baseline_scores)

        logger.info("Proposing %s experiment via %s", category.value, self.config.proposer_model)

        try:
            response = litellm.completion(
                model=self.config.proposer_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=4000,
            )
        except Exception as e:
            raise ProposerError(f"LLM call failed: {e}")

        content = response.choices[0].message.content
        if not content:
            raise ProposerError("Empty response from proposer LLM")

        return self._parse_response(content, category)

    def _parse_response(self, content: str, expected_category: ExperimentCategory) -> ExperimentPlan:
        """Parse the LLM response into an ExperimentPlan."""
        # Strip markdown code fences if present
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first and last lines (fences)
            lines = [l for l in lines if not l.strip().startswith("```")]
            content = "\n".join(lines)

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            # Try to extract JSON from the response
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(content[start:end])
                except json.JSONDecodeError:
                    raise ProposerError(f"Could not parse JSON from response: {e}")
            else:
                raise ProposerError(f"No JSON found in response: {e}")

        # Validate and convert
        category_str = data.get("category", expected_category.value)
        try:
            category = ExperimentCategory(category_str)
        except ValueError:
            category = expected_category

        files = []
        for f in data.get("files", []):
            files.append(FileChange(
                path=f.get("path", ""),
                action=f.get("action", "modify"),
                content=f.get("content", ""),
            ))

        if not files:
            raise ProposerError("Experiment plan has no file changes")

        return ExperimentPlan(
            category=category,
            hypothesis=data.get("hypothesis", ""),
            description=data.get("description", ""),
            files=files,
            risk=data.get("risk", "low"),
            expected_impact=data.get("expected_impact", ""),
        )
