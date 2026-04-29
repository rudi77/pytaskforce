"""Unit tests for the read-only profile discovery routes."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from taskforce.api.server import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_list_profiles_returns_known_profiles(client: TestClient) -> None:
    response = client.get("/api/v1/profiles")
    assert response.status_code == 200
    body = response.json()
    assert "profiles" in body
    names = {p["name"] for p in body["profiles"]}
    # default.yaml is shipped with the framework and must always be discoverable.
    assert "default" in names


def test_list_profiles_excludes_reserved_names(client: TestClient) -> None:
    response = client.get("/api/v1/profiles")
    body = response.json()
    names = {p["name"] for p in body["profiles"]}
    assert "llm_config" not in names
    assert "defaults" not in names


def test_get_profile_returns_config_and_yaml(client: TestClient) -> None:
    response = client.get("/api/v1/profiles/default")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "default"
    assert body["format"] in {"yaml", "agent_md"}
    assert body["yaml_text"]
    assert isinstance(body["config"], dict)


def test_get_profile_404_for_unknown(client: TestClient) -> None:
    response = client.get("/api/v1/profiles/this-does-not-exist-1234")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "profile_not_found"


def test_subagent_endpoint_excludes_param(client: TestClient) -> None:
    response = client.get("/api/v1/profiles/available-as-subagent?exclude=default")
    assert response.status_code == 200
    body = response.json()
    names = {p["name"] for p in body["profiles"]}
    assert "default" not in names
