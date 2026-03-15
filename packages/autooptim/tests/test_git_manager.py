"""Tests for the git manager."""

import subprocess
from pathlib import Path

import pytest

from autooptim.errors import GitError
from autooptim.git_manager import GitManager


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository."""
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@test.com"],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
        capture_output=True,
        check=True,
    )
    # Create initial commit
    (tmp_path / "README.md").write_text("# Test")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-m", "Initial"],
        capture_output=True,
        check=True,
    )
    return tmp_path


def test_get_current_sha(git_repo: Path):
    git = GitManager(git_repo)
    sha = git.get_current_sha()
    assert len(sha) >= 7  # short SHA


def test_has_uncommitted_changes(git_repo: Path):
    git = GitManager(git_repo)
    assert not git.has_uncommitted_changes()

    (git_repo / "new_file.txt").write_text("hello")
    assert git.has_uncommitted_changes()


def test_commit_experiment(git_repo: Path):
    git = GitManager(git_repo)
    (git_repo / "change.txt").write_text("experiment data")
    sha = git.commit_experiment(1, "Test experiment", ["change.txt"])
    assert len(sha) >= 7
    assert not git.has_uncommitted_changes()


def test_discard_last_commit(git_repo: Path):
    git = GitManager(git_repo)
    (git_repo / "temp.txt").write_text("temporary")
    git.commit_experiment(1, "To be discarded", ["temp.txt"])
    assert (git_repo / "temp.txt").exists()

    git.discard_last_commit()
    assert not (git_repo / "temp.txt").exists()


def test_create_branch(git_repo: Path):
    git = GitManager(git_repo)
    git.create_branch("test-branch")
    assert git.current_branch() == "test-branch"


def test_clean_working_tree(git_repo: Path):
    git = GitManager(git_repo)
    (git_repo / "README.md").write_text("modified")
    assert git.has_uncommitted_changes()

    git.clean_working_tree()
    assert not git.has_uncommitted_changes()
