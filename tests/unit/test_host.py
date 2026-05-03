"""Tests for the public ``taskforce.host`` integration API."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taskforce import host
from taskforce.application.profile_loader import (
    clear_extra_config_dirs,
    get_extra_config_dirs,
)
from taskforce.application.skill_service import (
    clear_extra_skill_dirs,
    get_extra_skill_dirs,
    reset_skill_service,
)
from taskforce.infrastructure.tools.registry import (
    unregister_tool,
)

# ------------------------------------------------------------------
# Fixtures / housekeeping
# ------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_registries():
    """Each test starts with empty extra-dir registries."""
    clear_extra_config_dirs()
    clear_extra_skill_dirs()
    reset_skill_service()
    yield
    clear_extra_config_dirs()
    clear_extra_skill_dirs()
    reset_skill_service()


# ------------------------------------------------------------------
# register_tool
# ------------------------------------------------------------------


def test_register_tool_round_trip():
    """register_tool followed by unregister_tool keeps the registry clean."""
    name = "host_test_dummy_tool"
    assert not host.is_tool_registered(name)
    host.register_tool(name, "DummyTool", "tests.fixtures.dummy_tool")
    try:
        assert host.is_tool_registered(name)
    finally:
        unregister_tool(name)
    assert not host.is_tool_registered(name)


def test_register_tool_is_idempotent():
    """Re-registering the same name must not raise (host apps may reload)."""
    name = "host_test_idempotent_tool"
    host.register_tool(name, "DummyTool", "tests.fixtures.dummy_tool")
    try:
        # Second call is a no-op, NOT a ValueError.
        host.register_tool(name, "DummyTool", "tests.fixtures.dummy_tool")
        assert host.is_tool_registered(name)
    finally:
        unregister_tool(name)


# ------------------------------------------------------------------
# register_profile_dir
# ------------------------------------------------------------------


def test_register_profile_dir_appends_to_extra_dirs(tmp_path):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()

    host.register_profile_dir(str(profile_dir))

    extra = [str(p) for p in get_extra_config_dirs()]
    assert str(profile_dir.resolve()) in extra


def test_register_profile_dir_dedupes(tmp_path):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()

    host.register_profile_dir(str(profile_dir))
    host.register_profile_dir(str(profile_dir))

    assert len(get_extra_config_dirs()) == 1


# ------------------------------------------------------------------
# register_skill_dir
# ------------------------------------------------------------------


def test_register_skill_dir_appends_to_extras(tmp_path):
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()

    host.register_skill_dir(str(skill_dir))

    assert skill_dir.resolve() in get_extra_skill_dirs()


def test_register_skill_dir_dedupes_relative_and_absolute(tmp_path, monkeypatch):
    """./foo and foo (and trailing-slash variants) must collapse into one entry."""
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    monkeypatch.chdir(tmp_path)

    host.register_skill_dir("skills")
    host.register_skill_dir("./skills")
    host.register_skill_dir(str(skill_dir))  # absolute

    assert len(get_extra_skill_dirs()) == 1
    assert get_extra_skill_dirs()[0] == skill_dir.resolve()


def test_register_skill_dir_propagates_to_live_singleton(tmp_path):
    """Late registration after SkillService init must hot-add the directory
    AND make the new skill discoverable via the public API."""
    from taskforce.application.skill_service import get_skill_service

    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    sample = skill_dir / "sample-host-test"
    sample.mkdir()
    (sample / "SKILL.md").write_text(
        "---\n"
        "name: sample-host-test\n"
        "description: Sample skill for tests.\n"
        "---\n\n"
        "Sample body.\n",
        encoding="utf-8",
    )

    # Force singleton creation BEFORE registration so we exercise the
    # late-registration code path.
    service = get_skill_service()
    assert "sample-host-test" not in service.list_skills()

    host.register_skill_dir(str(skill_dir))

    refreshed_dirs = {Path(d).resolve() for d in service.registry.directories}
    assert skill_dir.resolve() in refreshed_dirs
    # The skill itself must now show up via the standard discovery API.
    assert "sample-host-test" in service.list_skills()


# ------------------------------------------------------------------
# Router enumeration
# ------------------------------------------------------------------


def test_available_routers_lists_known_names():
    names = host.available_routers()
    # Spot-check a couple — full list intentionally not asserted to keep
    # the test from churning every time we add a router.
    for expected in ("execution", "gateway", "skills", "tools", "health"):
        assert expected in names


# ------------------------------------------------------------------
# mount_routes
# ------------------------------------------------------------------


def test_mount_routes_default_mounts_all_under_prefix():
    app = FastAPI()
    mounted = host.mount_routes(app)
    assert set(mounted) == set(host.available_routers())

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    # Health is prefixless …
    assert any(p.startswith("/health") for p in paths)
    # … the others should have the /api/v1 prefix.
    assert any(p.startswith("/api/v1/gateway") for p in paths)


def test_mount_routes_include_subset():
    app = FastAPI()
    mounted = host.mount_routes(app, include=["health", "execution"])
    assert mounted == ["health", "execution"]

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert any(p.startswith("/health") for p in paths)
    assert any(p.startswith("/api/v1/execute") or p.startswith("/api/v1/runs") for p in paths)
    # Gateway was NOT in include — must not be mounted.
    assert not any(p.startswith("/api/v1/gateway") for p in paths)


def test_mount_routes_exclude_removes_routers():
    app = FastAPI()
    mounted = host.mount_routes(app, exclude=["evals", "agent_deployments"])
    assert "evals" not in mounted
    assert "agent_deployments" not in mounted
    assert "gateway" in mounted


def test_mount_routes_unknown_name_raises():
    app = FastAPI()
    with pytest.raises(ValueError, match="Unknown router 'no_such_router'"):
        host.mount_routes(app, include=["no_such_router"])


def test_mount_routes_unknown_exclude_raises():
    app = FastAPI()
    with pytest.raises(ValueError, match="Unknown router\\(s\\) in exclude"):
        host.mount_routes(app, exclude=["no_such_router"])


def test_mount_routes_is_idempotent():
    """Calling mount_routes twice must not register duplicate paths."""
    app = FastAPI()
    first = host.mount_routes(app, include=["health", "execution"])
    paths_after_first = [route.path for route in app.routes]  # type: ignore[attr-defined]
    second = host.mount_routes(app, include=["health", "execution"])
    paths_after_second = [route.path for route in app.routes]  # type: ignore[attr-defined]

    assert first == ["health", "execution"]
    assert second == []  # nothing new mounted on the second call
    assert paths_after_first == paths_after_second


def test_mount_routes_custom_prefix():
    app = FastAPI()
    host.mount_routes(app, prefix="/v2/agent", include=["execution"])
    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert any(p.startswith("/v2/agent") for p in paths)


def test_mount_routes_health_endpoint_responds():
    """End-to-end sanity check: mounted health route serves 200."""
    app = FastAPI()
    host.mount_routes(app, include=["health"])
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200


# ------------------------------------------------------------------
# create_embedded_app
# ------------------------------------------------------------------


def test_create_embedded_app_subset():
    app = host.create_embedded_app(
        include=["health", "skills"],
        title="Embedded Test",
    )
    assert app.title == "Embedded Test"
    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert any(p.startswith("/health") for p in paths)
    assert any(p.startswith("/api/v1/skills") for p in paths)
    assert not any(p.startswith("/api/v1/gateway") for p in paths)


def test_create_embedded_app_health_responds():
    app = host.create_embedded_app(include=["health"])
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
