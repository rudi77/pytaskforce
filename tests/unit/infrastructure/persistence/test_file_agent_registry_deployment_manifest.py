"""Tests for ``FileAgentRegistry`` deployment-manifest filtering.

The deployment manifest is an allowlist that controls which agents
appear in user-facing listings. ``get_agent`` is unaffected so a
master agent can still extend a hidden sub-agent by id.
"""

from __future__ import annotations

import yaml

from taskforce.core.domain.deployment import DeploymentManifest
from taskforce.infrastructure.persistence.file_agent_registry import (
    FileAgentRegistry,
)


def _write_profile(configs_dir, name: str) -> None:
    profile_data = {
        "profile": name,
        "specialist": "generic",
        "tools": [],
        "mcp_servers": [],
        "llm": {"config_path": "configs/llm_config.yaml", "default_model": "main"},
        "persistence": {"type": "file", "work_dir": ".taskforce"},
    }
    with open(configs_dir / f"{name}.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(profile_data, f)


def test_list_agents_without_manifest_returns_all(tmp_path) -> None:
    """Backward compatibility: no manifest → no filtering."""
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    (configs_dir / "custom").mkdir()
    _write_profile(configs_dir, "butler")
    _write_profile(configs_dir, "showcase_coder")

    registry = FileAgentRegistry(configs_dir=str(configs_dir))

    profiles = {a.profile for a in registry.list_agents()}
    assert profiles == {"butler", "showcase_coder"}


def test_list_agents_filters_by_deployment_manifest(tmp_path) -> None:
    """With a manifest installed, only allowlisted profiles surface."""
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    (configs_dir / "custom").mkdir()
    _write_profile(configs_dir, "butler")
    _write_profile(configs_dir, "rag_agent")
    _write_profile(configs_dir, "showcase_coder")
    _write_profile(configs_dir, "ap_poc_agent")

    manifest = DeploymentManifest(visible_agents=frozenset({"butler", "rag_agent"}))
    registry = FileAgentRegistry(
        configs_dir=str(configs_dir),
        deployment_manifest=manifest,
    )

    profiles = {a.profile for a in registry.list_agents()}
    assert profiles == {"butler", "rag_agent"}


def test_list_agents_include_hidden_returns_all(tmp_path) -> None:
    """``include_hidden=True`` bypasses the manifest filter."""
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    (configs_dir / "custom").mkdir()
    _write_profile(configs_dir, "butler")
    _write_profile(configs_dir, "showcase_coder")

    manifest = DeploymentManifest(visible_agents=frozenset({"butler"}))
    registry = FileAgentRegistry(
        configs_dir=str(configs_dir),
        deployment_manifest=manifest,
    )

    profiles_default = {a.profile for a in registry.list_agents()}
    profiles_unfiltered = {a.profile for a in registry.list_agents(include_hidden=True)}

    assert profiles_default == {"butler"}
    assert profiles_unfiltered == {"butler", "showcase_coder"}


def test_get_agent_unaffected_by_manifest(tmp_path) -> None:
    """Sub-agent resolution by id keeps working even for hidden agents."""
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    (configs_dir / "custom").mkdir()
    _write_profile(configs_dir, "butler")
    _write_profile(configs_dir, "showcase_coder")

    manifest = DeploymentManifest(visible_agents=frozenset({"butler"}))
    registry = FileAgentRegistry(
        configs_dir=str(configs_dir),
        deployment_manifest=manifest,
    )

    hidden = registry.get_agent("showcase_coder")
    assert hidden is not None
    assert hidden.profile == "showcase_coder"


def test_load_deployment_manifest_reads_yaml(tmp_path) -> None:
    """The loader resolves a YAML file into a frozenset-backed manifest."""
    from taskforce.core.domain.deployment import load_deployment_manifest

    manifest_path = tmp_path / "deployment.yaml"
    manifest_path.write_text(
        "version: 1\nvisible_agents:\n  - butler\n  - rag_agent\n",
        encoding="utf-8",
    )

    manifest = load_deployment_manifest(manifest_path)
    assert manifest is not None
    assert manifest.visible_agents == frozenset({"butler", "rag_agent"})
    assert manifest.is_visible("butler")
    assert not manifest.is_visible("showcase_coder")


def test_load_deployment_manifest_missing_file_returns_none(tmp_path) -> None:
    """A non-existent path resolves to ``None`` rather than raising."""
    from taskforce.core.domain.deployment import load_deployment_manifest

    assert load_deployment_manifest(tmp_path / "does-not-exist.yaml") is None


def test_load_deployment_manifest_invalid_yaml_returns_none(tmp_path) -> None:
    """A malformed YAML body is treated as "no manifest"."""
    from taskforce.core.domain.deployment import load_deployment_manifest

    bad = tmp_path / "deployment.yaml"
    bad.write_text("visible_agents: not-a-list\n", encoding="utf-8")
    assert load_deployment_manifest(bad) is None
