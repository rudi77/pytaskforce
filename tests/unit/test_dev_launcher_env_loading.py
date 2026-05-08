"""Regression tests for dev launcher environment loading."""

from __future__ import annotations

from pathlib import Path


def test_dev_launcher_imports_dotenv_before_starting_processes() -> None:
    script = (Path(__file__).resolve().parents[2] / "dev.ps1").read_text(encoding="utf-8")

    main_index = script.index("# ---------------------------------------------------------------- main")
    main_body = script[main_index:]

    assert "function Import-DotEnv" in script
    assert 'Set-Item -Path "env:$key" -Value $value' in script
    assert main_body.index("Test-Venv") < main_body.index("Import-DotEnv")
    assert main_body.index("Import-DotEnv") < main_body.index("Invoke-SyncPlugins")
