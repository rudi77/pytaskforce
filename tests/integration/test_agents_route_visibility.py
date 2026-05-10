"""Integration tests for ``GET /api/v1/agents`` deployment-manifest filtering.

The route exposes ``include_hidden=true`` for power users who need to
inspect every discovered agent (e.g. to populate the upcoming
visibility editor in the UI). The default response is the manifest's
allowlisted subset.
"""

from __future__ import annotations

import pytest
import yaml

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from taskforce.api.dependencies import get_agent_registry  # noqa: E402
from taskforce.api.server import create_app  # noqa: E402
from taskforce.core.domain.deployment import DeploymentManifest  # noqa: E402
from taskforce.infrastructure.persistence.file_agent_registry import (  # noqa: E402
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


@pytest.fixture
def client(tmp_path):
    """A TestClient backed by a registry with a deployment manifest installed."""
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

    app = create_app()
    app.dependency_overrides[get_agent_registry] = lambda: registry
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_list_agents_filters_by_manifest_by_default(client):
    response = client.get("/api/v1/agents")
    assert response.status_code == 200
    profiles = {a["profile"] for a in response.json()["agents"] if a["source"] == "profile"}
    assert profiles == {"butler", "rag_agent"}


def test_list_agents_include_hidden_returns_all(client):
    response = client.get("/api/v1/agents", params={"include_hidden": "true"})
    assert response.status_code == 200
    profiles = {a["profile"] for a in response.json()["agents"] if a["source"] == "profile"}
    assert profiles == {"butler", "rag_agent", "showcase_coder", "ap_poc_agent"}


def test_get_hidden_agent_by_id_still_works(client):
    """Hidden agents stay reachable by id so sub-agent extension works."""
    response = client.get("/api/v1/agents/showcase_coder")
    assert response.status_code == 200
    assert response.json()["profile"] == "showcase_coder"


def test_legacy_registry_without_include_hidden_kwarg(tmp_path):
    """The route must tolerate plugin-installed registries with the older
    ``list_agents()`` signature (no ``include_hidden`` kwarg) — the enterprise
    PostgresAgentRegistry is the canonical example. Without the graceful
    fallback the route raises ``TypeError`` and returns 500.
    """

    class LegacyRegistry:
        def list_agents(self):  # NB: no include_hidden parameter
            from taskforce.core.domain.agent_models import ProfileAgentDefinition

            return [
                ProfileAgentDefinition(
                    profile="butler",
                    specialist="generic",
                    tools=[],
                    mcp_servers=[],
                    llm={},
                    persistence={},
                )
            ]

        def get_agent(self, agent_id):
            return None

    app = create_app()
    app.dependency_overrides[get_agent_registry] = lambda: LegacyRegistry()
    try:
        c = TestClient(app)
        # Both query forms must succeed; the kwarg is silently dropped.
        for url in ("/api/v1/agents", "/api/v1/agents?include_hidden=true"):
            resp = c.get(url)
            assert resp.status_code == 200, (url, resp.status_code, resp.text)
            profiles = {a["profile"] for a in resp.json()["agents"] if a["source"] == "profile"}
            assert profiles == {"butler"}
    finally:
        app.dependency_overrides.clear()
