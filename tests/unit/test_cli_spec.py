"""Spec-coverage tests for the unified ``taskforce`` CLI.

Drives the real Typer apps with ``CliRunner`` and exercises the
agent-discovery / profile-resolution wiring directly.

Spec: docs/spec/cli.md — tests tagged @pytest.mark.spec("cli.*").
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("taskforce_cli")
pytest.importorskip("typer")

import typer
from typer.testing import CliRunner

from taskforce_cli.main import app as unified_app

runner = CliRunner()


# A hidden probe command on the real app — lets tests observe the
# ``ctx.obj`` the top-level callback resolved (profile, debug) without
# running a real subcommand. Hidden so it never shows up in --help.
@unified_app.command("_spec_probe", hidden=True)
def _spec_probe(ctx: typer.Context) -> None:  # pragma: no cover - exercised via CliRunner
    typer.echo("PROBE:" + json.dumps(ctx.obj))


def _probe(args: list[str], env: dict[str, str] | None = None) -> dict:
    """Invoke the probe command and return the resolved ctx.obj."""
    result = runner.invoke(unified_app, [*args, "_spec_probe"], env=env)
    assert result.exit_code == 0, result.output
    line = next(ln for ln in result.output.splitlines() if ln.startswith("PROBE:"))
    return json.loads(line[len("PROBE:") :])


# ---------------------------------------------------------------------------
# Command surface
# ---------------------------------------------------------------------------


@pytest.mark.spec("cli.taskforce_script_works_after_install")
def test_taskforce_script_works_after_install() -> None:
    """``taskforce --help`` runs and lists the core framework subcommands."""
    result = runner.invoke(unified_app, ["--help"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    for command in ("run", "chat", "tools", "skills"):
        assert command in result.output


@pytest.mark.spec("cli.framework_only_fallback_always_defaults_to_dev")
def test_framework_only_fallback_defaults_to_dev() -> None:
    """The framework-only fallback CLI hard-defaults its --profile to ``dev``."""
    from taskforce.api.cli.main import app as fallback_app

    result = runner.invoke(fallback_app, ["--help"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    # Typer renders the option default in the help table.
    normalised = " ".join(result.output.split())
    assert "--profile" in normalised
    assert "dev" in normalised


# ---------------------------------------------------------------------------
# Profile resolution
# ---------------------------------------------------------------------------


@pytest.mark.spec("cli.global_profile_flag_accepted_on_every_subcommand")
def test_global_profile_flag_accepted() -> None:
    """The top-level ``--profile`` flag is accepted before any subcommand."""
    obj = _probe(["--profile", "custom-profile"])
    assert obj["profile"] == "custom-profile"
    # The short form is equivalent.
    assert _probe(["-p", "short-profile"])["profile"] == "short-profile"


@pytest.mark.spec("cli.env_taskforce_profile_used_when_no_flag")
def test_env_taskforce_profile_used_when_no_flag() -> None:
    """With no ``--profile`` flag, ``TASKFORCE_PROFILE`` supplies the profile."""
    obj = _probe([], env={"TASKFORCE_PROFILE": "env-profile"})
    assert obj["profile"] == "env-profile"


@pytest.mark.spec("cli.subcommand_profile_flag_overrides_global")
def test_subcommand_profile_flag_overrides_global(monkeypatch) -> None:
    """A per-subcommand ``--profile`` overrides the global value."""
    import taskforce.api.cli.commands.run as run_mod

    captured: dict[str, str] = {}

    def _fake_execute(**kwargs: object) -> None:
        captured["profile"] = str(kwargs["profile"])

    monkeypatch.setattr(run_mod, "_execute_standard_mission", _fake_execute)

    # Global says 'global-prof'; the subcommand flag says 'sub-prof' → sub wins.
    runner.invoke(
        unified_app,
        ["--profile", "global-prof", "run", "mission", "hi", "--profile", "sub-prof"],
    )
    assert captured["profile"] == "sub-prof"

    # Without the subcommand flag, the global value is used.
    captured.clear()
    runner.invoke(unified_app, ["--profile", "global-prof", "run", "mission", "hi"])
    assert captured["profile"] == "global-prof"


# ---------------------------------------------------------------------------
# Agent-package discovery wiring
# ---------------------------------------------------------------------------


@pytest.mark.spec("cli.config_dirs_registered_during_top_level_callback")
def test_config_dirs_registered_during_top_level_callback(monkeypatch) -> None:
    """The top-level callback registers agent config dirs once per invocation."""
    calls = {"n": 0}

    def _spy() -> None:
        calls["n"] += 1

    monkeypatch.setattr(
        "taskforce_cli.agent_discovery.register_agent_config_dirs", _spy
    )
    _probe([])
    assert calls["n"] == 1


@pytest.mark.spec("cli.custom_and_roles_subdirs_registered_for_each_agent_package")
def test_custom_and_roles_subdirs_registered(monkeypatch, tmp_path: Path) -> None:
    """``register_agent_config_dirs`` registers configs/ + custom/ + roles/."""
    from taskforce_cli import agent_discovery

    config_dir = tmp_path / "agentpkg" / "configs"
    (config_dir / "custom").mkdir(parents=True)
    (config_dir / "roles").mkdir(parents=True)

    registered: list[str] = []
    monkeypatch.setattr(agent_discovery, "get_agent_config_dirs", lambda: [config_dir])
    monkeypatch.setattr(
        "taskforce.application.profile_loader.register_config_dir",
        lambda p: registered.append(str(Path(p))),
    )

    agent_discovery.register_agent_config_dirs()

    assert str(config_dir) in registered
    assert str(config_dir / "custom") in registered
    assert str(config_dir / "roles") in registered


@pytest.mark.spec("cli.hardcoded_agent_fallback_logged_when_used")
def test_hardcoded_agent_fallback_logged_when_used(monkeypatch) -> None:
    """A hardcoded CLI fallback logs ``event='hardcoded_agent_fallback'``."""
    from taskforce_cli import main as cli_main

    # A fake importable module exposing a Typer app.
    fake_mod = types.ModuleType("fake_agent_pkg_cli")
    fake_mod.app = typer.Typer()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fake_agent_pkg_cli", fake_mod)

    # Ensure the fallback path is taken (name not already registered).
    monkeypatch.setattr(cli_main, "_registered_agent_cli", set())

    warnings: list[tuple[str, dict]] = []

    class _Recorder:
        def warning(self, event: str, **kw: object) -> None:
            warnings.append((event, dict(kw)))

    monkeypatch.setattr("structlog.get_logger", lambda *a, **kw: _Recorder())

    cli_main._register_fallback_cli("fakeagent", "fake_agent_pkg_cli:app")

    assert any(event == "hardcoded_agent_fallback" for event, _ in warnings)


@pytest.mark.spec("cli.cli_apps_entry_point_overrides_hardcoded_fallback")
def test_cli_apps_entry_point_overrides_hardcoded_fallback(monkeypatch) -> None:
    """A name already registered via entry-point skips the hardcoded fallback."""
    from taskforce_cli import main as cli_main

    # Pretend 'epic' was already contributed by a taskforce.cli_apps entry-point.
    monkeypatch.setattr(cli_main, "_registered_agent_cli", {"epic"})

    add_typer_calls: list[str] = []
    monkeypatch.setattr(
        cli_main.app, "add_typer", lambda *a, **kw: add_typer_calls.append(kw.get("name", ""))
    )

    # The fallback for 'epic' must be a no-op — entry-point wins.
    cli_main._register_fallback_cli("epic", "taskforce_coding_agent.cli:app")
    assert add_typer_calls == []


# ---------------------------------------------------------------------------
# .env auto-loading
# ---------------------------------------------------------------------------


@pytest.mark.spec("cli.dotenv_loaded_before_any_subcommand_runs")
def test_dotenv_loaded_before_any_subcommand_runs(tmp_path: Path, monkeypatch) -> None:
    """A local ``.env`` is loaded by ``load_dotenv_if_present`` (CLI bootstrap)."""
    from taskforce.api.cli.env_loader import load_dotenv_if_present

    monkeypatch.delenv("SPEC_DOTENV_VAR", raising=False)
    (tmp_path / ".env").write_text("SPEC_DOTENV_VAR=loaded-value\n", encoding="utf-8")

    load_dotenv_if_present(tmp_path)

    import os

    assert os.environ.get("SPEC_DOTENV_VAR") == "loaded-value"


# ---------------------------------------------------------------------------
# up / serve bind defaults + health poll
# ---------------------------------------------------------------------------


@pytest.mark.spec("cli.up_binds_127_0_0_1_by_default")
def test_up_binds_localhost_by_default(monkeypatch) -> None:
    """``taskforce up`` binds uvicorn to 127.0.0.1 unless --host overrides it."""
    fake_uvicorn = types.ModuleType("uvicorn")
    captured: dict[str, object] = {}

    def _run(app_path: str, **kwargs: object) -> None:
        captured["app"] = app_path
        captured["host"] = kwargs.get("host")

    fake_uvicorn.run = _run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)

    result = runner.invoke(unified_app, ["up", "--no-browser"])
    assert result.exit_code == 0, result.output
    assert captured["host"] == "127.0.0.1"
    assert captured["app"] == "taskforce.api.server:app"


@pytest.mark.spec("cli.up_polls_health_before_opening_browser")
def test_up_polls_health_before_opening_browser(monkeypatch) -> None:
    """The browser opens only after the /health endpoint answers 200."""
    from taskforce_cli.commands import up as up_mod

    # --- health answers 200 → browser opens, after a health probe ---
    health_calls = {"n": 0}

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _ok_urlopen(_url, timeout=2):  # noqa: ANN001
        health_calls["n"] += 1
        return _Resp()

    opened: list[str] = []
    import webbrowser

    monkeypatch.setattr("urllib.request.urlopen", _ok_urlopen)
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))

    up_mod._open_browser_when_ready("http://x", "http://x/health", timeout=5.0)
    assert health_calls["n"] >= 1, "health endpoint must be polled"
    assert opened == ["http://x"]

    # --- health never answers → browser is NOT opened ---
    opened.clear()

    def _bad_urlopen(_url, timeout=2):  # noqa: ANN001
        raise OSError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", _bad_urlopen)
    up_mod._open_browser_when_ready("http://x", "http://x/health", timeout=0.0)
    assert opened == [], "browser must not open before health answers"
