"""
Ralph Learnings Tool

Manages progress tracking and learnings persistence.
Appends lessons learned to progress.txt and updates AGENTS.md with guardrails.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol


class RalphLearningsTool(ToolProtocol):
    """
    Tool for managing learnings and progress tracking.

    Supports:
    - Appending lessons learned to progress.txt
    - Updating AGENTS.md with guardrails/signs to prevent regression
    - Creating files if they don't exist
    """

    def __init__(
        self,
        progress_path: str = "progress.txt",
        agents_path: str = "AGENTS.md",
    ):
        """
        Initialize RalphLearningsTool.

        Args:
            progress_path: Path to progress.txt file (default: "progress.txt")
            agents_path: Path to AGENTS.md file (default: "AGENTS.md")
        """
        self.progress_path = Path(progress_path)
        self.agents_path = Path(agents_path)

    @property
    def name(self) -> str:
        """Return tool name."""
        return "ralph_learnings"

    @property
    def description(self) -> str:
        """Return tool description."""
        return (
            "Manage learnings and progress tracking. Appends lessons learned to "
            "progress.txt and updates AGENTS.md (Self-Maintaining Documentation) with "
            "guardrails or signs to prevent regression. Creates files if they don't exist."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """Return OpenAI function calling compatible parameter schema."""
        return {
            "type": "object",
            "properties": {
                "lesson": {
                    "type": "string",
                    "description": "The lesson learned to append to progress.txt",
                },
                "guardrail": {
                    "type": "string",
                    "description": "Optional guardrail or sign to add to AGENTS.md (e.g., 'Always check X before Y')",
                },
            },
            "required": ["lesson"],
        }

    @property
    def requires_approval(self) -> bool:
        """Writing learnings modifies documentation, requires approval."""
        return True

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        """Medium risk - modifies documentation files."""
        return ApprovalRiskLevel.MEDIUM

    @property
    def supports_parallelism(self) -> bool:
        """File writes should be serialized to avoid conflicts."""
        return False

    def get_approval_preview(self, **kwargs: Any) -> str:
        """Generate human-readable preview of operation."""
        lesson = kwargs.get("lesson", "")
        guardrail = kwargs.get("guardrail")
        preview = (
            f"Tool: {self.name}\n"
            f"Operation: Append lesson to progress.txt and update AGENTS.md\n"
            f"Lesson: {lesson[:100]}...\n" if len(lesson) > 100 else f"Lesson: {lesson}\n"
        )
        if guardrail:
            preview += (
                f"Guardrail: {guardrail[:100]}...\n" if len(guardrail) > 100 else f"Guardrail: {guardrail}\n"
            )
        return preview

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "lesson" not in kwargs:
            return False, "lesson is required"
        if not isinstance(kwargs["lesson"], str) or not kwargs["lesson"].strip():
            return False, "lesson must be a non-empty string"
        if "guardrail" in kwargs and not isinstance(kwargs["guardrail"], str):
            return False, "guardrail must be a string if provided"
        return True, None

    async def execute(self, lesson: str, guardrail: str | None = None, **kwargs: Any) -> dict[str, Any]:
        """
        Execute learnings tool: append lesson and update AGENTS.md.

        Args:
            lesson: The lesson learned to append to progress.txt
            guardrail: Optional guardrail to add to AGENTS.md

        Returns:
            Dictionary with success status and result data
        """
        try:
            # Append to progress.txt
            await self._append_progress(lesson)

            # Update AGENTS.md if guardrail provided
            if guardrail:
                await self._update_agents_md(guardrail)

            output = f"Lesson appended to {self.progress_path}"
            if guardrail:
                output += f" and guardrail added to {self.agents_path}"

            return {
                "success": True,
                "output": output,
                "progress_file": str(self.progress_path),
                "agents_file": str(self.agents_path),
            }
        except Exception as e:
            return {"success": False, "error": str(e), "error_type": type(e).__name__}

    async def _append_progress(self, lesson: str) -> None:
        """Append lesson to progress.txt, creating file if it doesn't exist."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"\n[{timestamp}] {lesson}\n"

        # Create file if it doesn't exist
        if not self.progress_path.exists():
            self.progress_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.progress_path, "w", encoding="utf-8") as f:
                f.write("# Progress Log\n")
                f.write("# Lessons Learned\n\n")

        # Append to file
        with open(self.progress_path, "a", encoding="utf-8") as f:
            f.write(entry)

    async def _update_agents_md(self, guardrail: str) -> None:
        """
        Update AGENTS.md with guardrail/sign.

        Adds guardrail to a "Guardrails" or "Signs" section, or creates one if missing.
        """
        # Read existing content or create new
        if self.agents_path.exists():
            content = self.agents_path.read_text(encoding="utf-8")
        else:
            # Create initial AGENTS.md structure
            content = "# Self-Maintaining Documentation\n\n"
            content += "This file should be updated automatically when project-specific patterns, "
            content += "conventions, or important information are discovered during work sessions.\n\n"

        # Check if Guardrails section exists
        guardrails_pattern = r"(?i)^##\s+(Guardrails|Signs|Guardrails and Signs)"
        guardrails_match = re.search(guardrails_pattern, content, re.MULTILINE)

        timestamp = datetime.now().strftime("%Y-%m-%d")
        guardrail_entry = f"- **{timestamp}**: {guardrail}\n"

        if guardrails_match:
            # Insert guardrail at the beginning of the section (after the heading)
            # Find first newline after heading to insert after it
            section_start = guardrails_match.end()
            first_newline = content.find("\n", section_start)
            if first_newline != -1:
                insert_pos = first_newline + 1
            else:
                # No newline found, insert right after heading
                insert_pos = section_start

            # Insert guardrail
            content = content[:insert_pos] + guardrail_entry + content[insert_pos:]
        else:
            # Add Guardrails section at the end
            if not content.endswith("\n"):
                content += "\n"
            content += "## Guardrails\n\n"
            content += guardrail_entry

        # Write back
        self.agents_path.parent.mkdir(parents=True, exist_ok=True)
        self.agents_path.write_text(content, encoding="utf-8")
