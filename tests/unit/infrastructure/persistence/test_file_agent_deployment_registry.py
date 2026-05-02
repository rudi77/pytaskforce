from taskforce.infrastructure.persistence.file_agent_deployment_registry import (
    FileAgentDeploymentRegistry,
)
from taskforce.infrastructure.persistence.yaml_io import safe_load_yaml


def test_create_release_and_list_releases(tmp_path):
    registry = FileAgentDeploymentRegistry(tmp_path / ".taskforce" / "deployments")

    created = registry.create_release("agent-a", "r1", {"version": "1.0.0"})

    assert created["release_id"] == "r1"
    releases = registry.list_releases("agent-a")
    assert len(releases) == 1
    assert releases[0]["metadata"]["version"] == "1.0.0"


def test_mark_deployed_updates_active_and_history(tmp_path):
    registry = FileAgentDeploymentRegistry(tmp_path / ".taskforce" / "deployments")
    registry.create_release("agent-a", "r1", {"commit": "abc"})

    deployment = registry.mark_deployed("agent-a", "r1", "prod", {"actor": "ci"})

    assert deployment["environment"] == "prod"
    active = (tmp_path / ".taskforce" / "deployments" / "agent-a" / "active" / "prod.yaml")
    assert active.exists()
    history = (
        tmp_path / ".taskforce" / "deployments" / "agent-a" / "history" / "prod.yaml"
    )
    assert history.exists()


def test_rollback_to_sets_active_and_records_event(tmp_path):
    registry = FileAgentDeploymentRegistry(tmp_path / ".taskforce" / "deployments")
    registry.create_release("agent-a", "r1", {"version": "1.0.0"})
    registry.create_release("agent-a", "r2", {"version": "2.0.0"})
    registry.set_active("agent-a", "staging", "r2")

    rollback = registry.rollback_to("agent-a", "staging", "r1")

    assert rollback["release_id"] == "r1"
    active = registry._active_pointer_path("agent-a", "staging")
    active_data = safe_load_yaml(active)
    assert active.exists()
    assert active_data is not None
    assert active_data["release_id"] == "r1"
