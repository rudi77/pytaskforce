"""
Ralph Learnings Tool

Manages progress tracking and learnings persistence.
Appends lessons learned to progress.txt and updates AGENTS.md with guardrails.

V3 Enhancements:
- Rolling log: Keeps only the last MAX_PROGRESS_ENTRIES entries in progress.txt
- Guardrail limit: Keeps only the last MAX_GUARDRAILS guardrails in AGENTS.md
- Archives old entries to prevent context bloat
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol

# V3 Configuration for context control
MAX_PROGRESS_ENTRIES = 10  # Keep last 10 lessons in progress.txt
MAX_GUARDRAILS = 20  # Keep last 20 guardrails in AGENTS.md


class RalphLearningsTool(ToolProtocol):
    """
    Tool for managing learnings and progress tracking.

    Supports:
    - Appending lessons learned to progress.txt (rolling log, max 10 entries)
    - Updating AGENTS.md with guardrails/signs (max 20 guardrails)
    - Creating files if they don't exist
    - V3: Automatic archiving of old entries to AGENTS_ARCHIVE.md
    """

    def __init__(
        self,
        progress_path: str = "progress.txt",
        agents_path: str = "AGENTS.md",
        archive_path: str = "AGENTS_ARCHIVE.md",
        max_progress_entries: int = MAX_PROGRESS_ENTRIES,
        max_guardrails: int = MAX_GUARDRAILS,
    ):
        """
        Initialize RalphLearningsTool.

        Args:
            progress_path: Path to progress.txt file (default: "progress.txt")
            agents_path: Path to AGENTS.md file (default: "AGENTS.md")
            archive_path: Path to archive file for old guardrails (default: "AGENTS_ARCHIVE.md")
            max_progress_entries: Maximum entries to keep in progress.txt (default: 10)
            max_guardrails: Maximum guardrails to keep in AGENTS.md (default: 20)
        """
        self.progress_path = Path(progress_path)
        self.agents_path = Path(agents_path)
        self.archive_path = Path(archive_path)
        self.max_progress_entries = max_progress_entries
        self.max_guardrails = max_guardrails

    @property
    def name(self) -> str:
        """Return tool name."""
        return "ralph_learnings"

    @property
    def description(self) -> str:
        """Return tool description."""
        return (
            "Manage learnings and progress tracking. Appends lessons learned to "
            "progress.txt (rolling log, max 10 entries) and updates AGENTS.md with "
            "guardrails (max 20, older entries archived). Creates files if missing."
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

        lesson_display = f"{lesson[:100]}..." if len(lesson) > 100 else lesson
        preview = (
            f"Tool: {self.name}\n"
            f"Operation: Append lesson to progress.txt and update AGENTS.md\n"
            f"Lesson: {lesson_display}\n"
        )
        if guardrail:
            guardrail_display = f"{guardrail[:100]}..." if len(guardrail) > 100 else guardrail
            preview += f"Guardrail: {guardrail_display}\n"
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
        """
        Append lesson to progress.txt with rolling log behavior.

        V3: Keeps only the last max_progress_entries entries to prevent context bloat.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_entry = f"[{timestamp}] {lesson}"

        # Read existing entries
        entries = []
        header_lines = ["# Progress Log", "# Lessons Learned", ""]

        if self.progress_path.exists():
            content = self.progress_path.read_text(encoding="utf-8")
            lines = content.strip().split("\n")

            # Separate header from entries
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("[") and "]" in stripped:
                    entries.append(stripped)
                elif stripped and not stripped.startswith("#"):
                    # Non-header, non-entry line - might be old format
                    pass

        # Add new entry
        entries.append(new_entry)

        # Keep only the last max_progress_entries
        if len(entries) > self.max_progress_entries:
            entries = entries[-self.max_progress_entries:]

        # Write back with header
        self.progress_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.progress_path, "w", encoding="utf-8") as f:
            for header in header_lines:
                f.write(header + "\n")
            for entry in entries:
                f.write(entry + "\n")

    async def _update_agents_md(self, guardrail: str) -> None:
        """
        Update AGENTS.md with guardrail/sign.

        V3: Limits guardrails to max_guardrails entries. Archives old guardrails
        to AGENTS_ARCHIVE.md when the limit is exceeded.
        """
        # Read existing content or create new
        if self.agents_path.exists():
            content = self.agents_path.read_text(encoding="utf-8")
        else:
            # Create initial AGENTS.md structure
            content = "# Self-Maintaining Documentation\n\n"
            content += "This file should be updated automatically when project-specific patterns, "
            content += "conventions, or important information are discovered during work sessions.\n\n"

        timestamp = datetime.now().strftime("%Y-%m-%d")
        guardrail_entry = f"- **{timestamp}**: {guardrail}"

        # Extract existing guardrails
        guardrail_pattern = r"^- \*\*[\d-]+\*\*: .+$"
        existing_guardrails = re.findall(guardrail_pattern, content, re.MULTILINE)

        # Add new guardrail at the beginning
        all_guardrails = [guardrail_entry] + existing_guardrails

        # Check if we need to archive old guardrails
        if len(all_guardrails) > self.max_guardrails:
            # Archive the oldest entries
            guardrails_to_archive = all_guardrails[self.max_guardrails:]
            all_guardrails = all_guardrails[: self.max_guardrails]

            # Write to archive
            await self._archive_guardrails(guardrails_to_archive)

        # Rebuild AGENTS.md content
        # Remove old guardrails section
        guardrails_section_pattern = r"(?i)^##\s+(Guardrails|Signs|Guardrails and Signs)\s*\n(?:- \*\*[\d-]+\*\*: .+\n?)+"
        content = re.sub(guardrails_section_pattern, "", content, flags=re.MULTILINE)

        # Remove any stray guardrail lines (in case of format variations)
        content = re.sub(guardrail_pattern + r"\n?", "", content, flags=re.MULTILINE)

        # Ensure content ends with newline
        content = content.rstrip() + "\n\n"

        # Add guardrails section
        content += "## Guardrails\n\n"
        for g in all_guardrails:
            content += g + "\n"

        # Write back
        self.agents_path.parent.mkdir(parents=True, exist_ok=True)
        self.agents_path.write_text(content, encoding="utf-8")

    async def _archive_guardrails(self, guardrails: list[str]) -> None:
        """
        Archive old guardrails to AGENTS_ARCHIVE.md.

        Args:
            guardrails: List of guardrail entries to archive
        """
        if not guardrails:
            return

        # Read existing archive or create new
        if self.archive_path.exists():
            content = self.archive_path.read_text(encoding="utf-8")
        else:
            content = "# Archived Guardrails\n\n"
            content += "Old guardrails moved from AGENTS.md to prevent context bloat.\n\n"

        # Add timestamp for this archive batch
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        content += f"\n## Archived on {timestamp}\n\n"

        for g in guardrails:
            content += g + "\n"

        # Write archive
        self.archive_path.parent.mkdir(parents=True, exist_ok=True)
        self.archive_path.write_text(content, encoding="utf-8")
