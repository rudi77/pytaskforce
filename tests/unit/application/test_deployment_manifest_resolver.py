"""Tests for the settings-store-aware deployment-manifest resolver."""

from __future__ import annotations

from unittest.mock import patch

from cryptography.fernet import Fernet

from taskforce.application.deployment_manifest_resolver import (
    resolve_deployment_manifest,
)
from taskforce.core.domain.deployment import DeploymentManifest
from taskforce.core.domain.settings import VISIBLE_AGENTS
from taskforce.infrastructure.persistence.file_settings_store import (
    FileSettingsStore,
)


def _store(tmp_path):
    return FileSettingsStore(work_dir=tmp_path, key=Fernet.generate_key())


def test_settings_takes_precedence_over_yaml(tmp_path) -> None:
    store = _store(tmp_path)
    store.put(VISIBLE_AGENTS, {"agents": ["butler", "rag_agent"]})
    yaml_manifest = DeploymentManifest(visible_agents=frozenset({"showcase_coder"}))

    with patch(
        "taskforce.core.domain.deployment.load_deployment_manifest",
        return_value=yaml_manifest,
    ) as mock_load:
        resolved = resolve_deployment_manifest(store)

    assert resolved is not None
    assert resolved.visible_agents == frozenset({"butler", "rag_agent"})
    mock_load.assert_not_called()


def test_falls_back_to_yaml_when_settings_empty(tmp_path) -> None:
    store = _store(tmp_path)
    yaml_manifest = DeploymentManifest(visible_agents=frozenset({"butler"}))

    with patch(
        "taskforce.core.domain.deployment.load_deployment_manifest",
        return_value=yaml_manifest,
    ):
        resolved = resolve_deployment_manifest(store)

    assert resolved is yaml_manifest


def test_returns_none_when_neither_source_resolves(tmp_path) -> None:
    store = _store(tmp_path)
    with patch(
        "taskforce.core.domain.deployment.load_deployment_manifest",
        return_value=None,
    ):
        assert resolve_deployment_manifest(store) is None


def test_settings_with_empty_agents_list_falls_back(tmp_path) -> None:
    store = _store(tmp_path)
    store.put(VISIBLE_AGENTS, {"agents": []})
    yaml_manifest = DeploymentManifest(visible_agents=frozenset({"butler"}))

    with patch(
        "taskforce.core.domain.deployment.load_deployment_manifest",
        return_value=yaml_manifest,
    ):
        assert resolve_deployment_manifest(store) is yaml_manifest


def test_settings_strips_whitespace(tmp_path) -> None:
    store = _store(tmp_path)
    store.put(VISIBLE_AGENTS, {"agents": ["  butler  ", "rag_agent", "  "]})

    resolved = resolve_deployment_manifest(store)
    assert resolved is not None
    assert resolved.visible_agents == frozenset({"butler", "rag_agent"})


def test_none_store_skips_settings_path() -> None:
    yaml_manifest = DeploymentManifest(visible_agents=frozenset({"butler"}))
    with patch(
        "taskforce.core.domain.deployment.load_deployment_manifest",
        return_value=yaml_manifest,
    ):
        assert resolve_deployment_manifest(None) is yaml_manifest
