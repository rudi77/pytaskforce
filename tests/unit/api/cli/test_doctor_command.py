"""Tests for the taskforce doctor health check command."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from taskforce.api.cli.commands.doctor import (
    CHECK,
    CROSS,
    WARN,
    _check_env_file,
    _check_llm_config,
    _check_package_version,
    _check_profile,
    _check_python_version,
    _check_workspace,
)


class TestCheckPythonVersion:
    """Tests for Python version check."""

    def test_passes_on_311_plus(self) -> None:
        status, msg = _check_python_version()
        # We're running on 3.11+, so this should pass
        assert CHECK in status
        assert "Python" in msg

    def test_format_includes_version(self) -> None:
        _, msg = _check_python_version()
        major, minor = sys.version_info[:2]
        assert f"{major}.{minor}" in msg


class TestCheckPackageVersion:
    """Tests for package version check."""

    def test_package_is_importable(self) -> None:
        status, msg = _check_package_version()
        assert CHECK in status
        assert "Taskforce" in msg


class TestCheckWorkspace:
    """Tests for workspace directory check."""

    def test_missing_workspace(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        status, msg = _check_workspace()
        assert CROSS in status
        assert "not found" in msg

    def test_existing_workspace(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".taskforce").mkdir()
        status, msg = _check_workspace()
        assert CHECK in status


class TestCheckEnvFile:
    """Tests for .env file check."""

    def test_missing_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        status, msg = _check_env_file()
        assert WARN in status

    def test_empty_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("# Only comments\n")
        status, msg = _check_env_file()
        assert WARN in status
        assert "no active variables" in msg

    def test_configured_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-test\n")
        status, msg = _check_env_file()
        assert CHECK in status
        assert "1 variable" in msg


class TestCheckLlmConfig:
    """Tests for LLM config check."""

    def test_missing_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        status, msg = _check_llm_config()
        assert WARN in status

    def test_local_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / ".taskforce" / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "llm_config.yaml").write_text("default_model: main\n")
        status, msg = _check_llm_config()
        assert CHECK in status


class TestCheckProfile:
    """Tests for profile validation."""

    def test_local_profile_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / ".taskforce" / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "profile.yaml").write_text("profile: dev\n")
        status, msg = _check_profile("dev")
        assert CHECK in status
        assert "local override" in msg

    def test_source_tree_profile(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / "src" / "taskforce" / "configs"
        config_dir.mkdir(parents=True)
        (config_dir / "dev.yaml").write_text("profile: dev\n")
        status, msg = _check_profile("dev")
        assert CHECK in status

    def test_missing_profile(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        status, msg = _check_profile("nonexistent_profile_xyz")
        assert CROSS in status
        assert "not found" in msg
