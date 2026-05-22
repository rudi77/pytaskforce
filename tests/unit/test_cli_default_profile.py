"""Default-profile detection for the unified CLI.

Spec: docs/spec/profiles.md — the unified CLI defaults to ``butler`` when
the butler config-dir entry-point is present, otherwise ``dev``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("taskforce_cli")

from taskforce_cli.main import _detect_default_profile


@pytest.mark.spec("profiles.cli_default_is_butler_when_installed_else_dev")
def test_default_profile_is_butler_when_config_dir_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the ``butler`` config-dir entry-point is discovered, the unified
    CLI default profile is ``butler``."""
    monkeypatch.setattr(
        "taskforce.application.agent_plugin_registry.load_config_dirs",
        lambda: {"butler": Path("/x/configs"), "coding_agent": Path("/y/configs")},
    )
    assert _detect_default_profile() == "butler"


@pytest.mark.spec("profiles.cli_default_is_butler_when_installed_else_dev")
def test_default_profile_is_dev_when_butler_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a ``butler`` config-dir entry-point, the default falls back
    to ``dev``."""
    monkeypatch.setattr(
        "taskforce.application.agent_plugin_registry.load_config_dirs",
        lambda: {"coding_agent": Path("/y/configs")},
    )
    assert _detect_default_profile() == "dev"
