"""Git operations for the autoresearch experiment loop.

Manages branching, committing experiments, and discarding failed ones.
All operations are local -- never pushes to remote.
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class GitError(Exception):
    """Raised when a git operation fails."""


class GitManager:
    """Manages git operations for autoresearch experiments."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run a git command in the repo root."""
        cmd = ["git", "-C", str(self.repo_root), *args]
        logger.debug("git %s", " ".join(args))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if check and result.returncode != 0:
            raise GitError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result

    def create_branch(self, name: str) -> None:
        """Create and checkout a new branch from current HEAD."""
        self._run("checkout", "-b", name)
        logger.info("Created branch: %s", name)

    def current_branch(self) -> str:
        """Return the name of the current branch."""
        result = self._run("branch", "--show-current")
        return result.stdout.strip()

    def get_current_sha(self) -> str:
        """Return the current HEAD SHA (short form)."""
        result = self._run("rev-parse", "--short", "HEAD")
        return result.stdout.strip()

    def has_uncommitted_changes(self) -> bool:
        """Check if there are uncommitted changes in the working tree."""
        result = self._run("status", "--porcelain", check=False)
        return bool(result.stdout.strip())

    def commit_experiment(
        self, experiment_id: int, description: str, files: list[str]
    ) -> str:
        """Stage and commit experiment files. Return the new commit SHA."""
        for f in files:
            self._run("add", f)
        msg = f"autoresearch experiment #{experiment_id}: {description}"
        self._run("commit", "-m", msg)
        return self.get_current_sha()

    def discard_last_commit(self) -> None:
        """Hard-reset the last commit (discards changes)."""
        self._run("reset", "--hard", "HEAD~1")
        logger.info("Discarded last commit")

    def reset_to_sha(self, sha: str) -> None:
        """Hard-reset to a specific SHA."""
        self._run("reset", "--hard", sha)
        logger.info("Reset to %s", sha)

    def stash_save(self, message: str = "autoresearch-stash") -> bool:
        """Stash current changes. Returns True if something was stashed."""
        result = self._run("stash", "push", "-m", message, check=False)
        return "No local changes" not in result.stdout

    def stash_pop(self) -> None:
        """Pop the most recent stash."""
        self._run("stash", "pop", check=False)

    def clean_working_tree(self) -> None:
        """Reset any uncommitted changes to match HEAD."""
        self._run("checkout", ".")
        # Also remove untracked files in src/ to be safe
        self._run("clean", "-fd", "src/", check=False)
