"""Base mutator with shared logic for path validation and preflight checks."""

import logging
import subprocess
import sys
from pathlib import Path

from autooptim.errors import MutationError, PreflightError
from autooptim.models import MutatorConfig

logger = logging.getLogger(__name__)


class BaseMutator:
    """Base class for mutators with config-driven path validation and preflight.

    Subclasses implement the actual file modification logic.
    """

    def __init__(self, project_root: Path, config: MutatorConfig) -> None:
        self.project_root = project_root
        self.config = config

    def validate_path(self, path: str) -> bool:
        """Check if a file path is allowed for modification.

        Uses allowed_paths and blocked_paths from config.
        """
        # Check blocked paths first
        for blocked in self.config.blocked_paths:
            if path.startswith(blocked):
                return False

        # If allowed_paths is specified, path must match at least one
        if self.config.allowed_paths:
            return any(path.startswith(a) for a in self.config.allowed_paths)

        # No restrictions if no allowed_paths specified
        return True

    def _check_path(self, path: str) -> None:
        """Validate path and raise if not allowed."""
        if not self.validate_path(path):
            raise MutationError(
                f"File '{path}' is not allowed for modification. "
                f"Allowed: {self.config.allowed_paths}, "
                f"Blocked: {self.config.blocked_paths}"
            )

    def read_file(self, path: str) -> str:
        """Read a file and return its content."""
        full_path = self.project_root / path
        if not full_path.exists():
            return f"# File not found: {path}"
        return full_path.read_text()

    def run_preflight(self, modified_files: list[str]) -> None:
        """Run configured preflight commands.

        Commands can use {files} placeholder for modified file paths
        and {project_root} for the project root.

        Args:
            modified_files: List of modified file paths (relative).

        Raises:
            PreflightError: If any command fails.
        """
        if not self.config.preflight_commands:
            return

        abs_files = [str(self.project_root / f) for f in modified_files]
        files_str = " ".join(abs_files)

        for cmd_template in self.config.preflight_commands:
            cmd = cmd_template.replace("{files}", files_str).replace(
                "{project_root}", str(self.project_root)
            )
            logger.info("Pre-flight: %s", cmd)

            result = subprocess.run(
                cmd,
                shell=True,
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=60,
                env={"PATH": subprocess.os.environ.get("PATH", ""), "PYTHONPATH": str(self.project_root / "src")},
            )

            if result.returncode != 0:
                raise PreflightError(
                    f"Pre-flight command failed: {cmd}\n"
                    f"stdout: {result.stdout[:500]}\n"
                    f"stderr: {result.stderr[:500]}"
                )

        logger.info("Pre-flight: all checks passed")
