"""Regression: bootstrap_config_dirs registers configs/custom + configs/roles.

Issue #235: previously only the top-level ``configs/`` dir of each
agent package was registered, hiding every sub-agent (Butler's
custom/roles, the coding sub-agent suite). The framework's
``FileAgentRegistry`` scans only the registered dirs as flat YAML
roots — without registering the nested subdirs, those YAMLs are
silently invisible to ``GET /api/v1/agents``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from taskforce.application.bootstrap_config_dirs import (
    _NESTED_PROFILE_SUBDIRS,
    bootstrap_config_dirs,
)


@pytest.fixture(autouse=True)
def _reset_bootstrap_state(monkeypatch):
    """Force fresh discovery on every test by toggling the module flag."""
    import taskforce.application.bootstrap_config_dirs as mod

    monkeypatch.setattr(mod, "_initialized", False)
    yield
    monkeypatch.setattr(mod, "_initialized", False)


def test_includes_known_subdirs_when_present(tmp_path):
    """When configs/custom and configs/roles exist, both are registered."""
    pkg_root = tmp_path / "pkg"
    configs = pkg_root / "configs"
    (configs / "custom").mkdir(parents=True)
    (configs / "roles").mkdir(parents=True)

    with patch(
        "taskforce.application.bootstrap_config_dirs._discover_agent_config_dirs",
        wraps=lambda: [configs, configs / "custom", configs / "roles"],
    ):
        registered = bootstrap_config_dirs(force=True)

    # The top-level + both subdirs all surface.
    assert configs in registered
    assert configs / "custom" in registered
    assert configs / "roles" in registered


def test_nested_subdirs_constant_pins_the_contract():
    """The constant is the public source of truth for what subdirs we scan."""
    assert "custom" in _NESTED_PROFILE_SUBDIRS
    assert "roles" in _NESTED_PROFILE_SUBDIRS


def test_discover_includes_existing_subdirs(tmp_path, monkeypatch):
    """The discover helper recurses into known subdirs of each package's configs/."""
    # Build a fake agent package layout
    pkg_root = tmp_path / "agents" / "butler"
    src_pkg = pkg_root / "src" / "taskforce_butler"
    src_pkg.mkdir(parents=True)
    (src_pkg / "__init__.py").write_text("")
    (pkg_root / "configs").mkdir()
    (pkg_root / "configs" / "custom").mkdir()
    (pkg_root / "configs" / "roles").mkdir()
    # No "extras" subdir — must not be registered

    # Inject the package via importlib mock
    import importlib

    class _FakeMod:
        __file__ = str(src_pkg / "__init__.py")

    real_import = importlib.import_module

    def fake_import(name):
        if name == "taskforce_butler":
            return _FakeMod()
        if name in {"taskforce_coding_agent", "taskforce_rag_agent"}:
            raise ImportError(name)
        return real_import(name)

    monkeypatch.setattr(importlib, "import_module", fake_import)

    from taskforce.application.bootstrap_config_dirs import _discover_agent_config_dirs

    dirs = _discover_agent_config_dirs()
    dirs_as_str = [str(Path(d)) for d in dirs]

    assert str(pkg_root / "configs") in dirs_as_str
    assert str(pkg_root / "configs" / "custom") in dirs_as_str
    assert str(pkg_root / "configs" / "roles") in dirs_as_str
    # extras-shaped subdir is not in the constant → not registered
    assert not any(d.endswith("extras") for d in dirs_as_str)
