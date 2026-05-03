"""Tests for the ``taskforce serve`` CLI command."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _import_cli_app():
    """Import the unified CLI lazily so tests don't fail before install."""
    pytest.importorskip("taskforce_cli")
    from taskforce_cli.main import app

    return app


def test_serve_help_lists_options(runner):
    cli_app = _import_cli_app()
    result = runner.invoke(cli_app, ["serve", "--help"])
    assert result.exit_code == 0
    out = result.stdout
    assert "--host" in out
    assert "--port" in out
    assert "--reload" in out
    assert "--workers" in out
    assert "--log-level" in out


def test_serve_invokes_uvicorn_with_defaults(runner):
    cli_app = _import_cli_app()
    with patch("uvicorn.run") as mock_run:
        result = runner.invoke(cli_app, ["serve"])

    assert result.exit_code == 0, result.stdout
    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert args[0] == "taskforce.api.server:app"
    # Default binds to localhost — host apps must opt in to 0.0.0.0.
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 8070
    assert kwargs["reload"] is False
    assert kwargs["workers"] == 1
    assert kwargs["log_level"] == "info"


def test_serve_passes_overrides_to_uvicorn(runner):
    cli_app = _import_cli_app()
    with patch("uvicorn.run") as mock_run:
        result = runner.invoke(
            cli_app,
            [
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                "9001",
                "--workers",
                "4",
                "--log-level",
                "debug",
            ],
        )

    assert result.exit_code == 0, result.stdout
    _, kwargs = mock_run.call_args
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 9001
    assert kwargs["workers"] == 4
    assert kwargs["log_level"] == "debug"


def test_serve_reload_forces_single_worker(runner):
    """``--reload`` and multiple workers are mutually exclusive in uvicorn."""
    cli_app = _import_cli_app()
    with patch("uvicorn.run") as mock_run:
        result = runner.invoke(cli_app, ["serve", "--reload", "--workers", "8"])

    assert result.exit_code == 0, result.stdout
    _, kwargs = mock_run.call_args
    assert kwargs["reload"] is True
    assert kwargs["workers"] == 1


def test_serve_custom_app_path(runner):
    cli_app = _import_cli_app()
    with patch("uvicorn.run") as mock_run:
        result = runner.invoke(cli_app, ["serve", "--app", "myapp.main:app"])

    assert result.exit_code == 0, result.stdout
    args, _ = mock_run.call_args
    assert args[0] == "myapp.main:app"
