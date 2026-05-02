"""Tests for the AgentDeployment domain model and transitions."""

from datetime import datetime, timezone

import pytest

from taskforce.core.domain.agent_deployment import (
    AgentDeployment,
    AgentDeploymentStatus,
    DeploymentEnvironment,
    validate_unique_deployments,
)


def _make(**overrides) -> AgentDeployment:
    defaults = dict(
        agent_id="writer",
        version="1.0.0",
        status=AgentDeploymentStatus.PENDING,
        environment=DeploymentEnvironment.LOCAL,
    )
    defaults.update(overrides)
    return AgentDeployment(**defaults)


# --- transitions -----------------------------------------------------------


def test_transition_pending_to_validating_is_allowed() -> None:
    record = _make()
    next_record = record.with_status(AgentDeploymentStatus.VALIDATING)
    assert next_record.status is AgentDeploymentStatus.VALIDATING


def test_transition_validating_to_deployed_stamps_metadata() -> None:
    record = _make(status=AgentDeploymentStatus.VALIDATING)
    deployed_at = datetime.now(timezone.utc)

    next_record = record.with_status(
        AgentDeploymentStatus.DEPLOYED,
        deployed_at=deployed_at,
        deployed_by="alice",
    )

    assert next_record.status is AgentDeploymentStatus.DEPLOYED
    assert next_record.deployed_at == deployed_at
    assert next_record.deployed_by == "alice"


def test_invalid_transition_raises_value_error() -> None:
    record = _make()
    with pytest.raises(ValueError, match="Invalid status transition"):
        record.with_status(AgentDeploymentStatus.DEPLOYED)


# --- environment coercion --------------------------------------------------


def test_environment_coerce_accepts_string() -> None:
    assert DeploymentEnvironment.coerce("staging") is DeploymentEnvironment.STAGING


def test_environment_coerce_passthrough_for_enum() -> None:
    assert DeploymentEnvironment.coerce(DeploymentEnvironment.PROD) is DeploymentEnvironment.PROD


def test_environment_coerce_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match="Unknown deployment environment"):
        DeploymentEnvironment.coerce("does-not-exist")


# --- uniqueness invariants -------------------------------------------------


def test_validate_unique_deployments_rejects_multiple_active_versions() -> None:
    deployed_at = datetime.now(timezone.utc)
    deployments = [
        _make(
            version="1.0.0",
            status=AgentDeploymentStatus.DEPLOYED,
            environment=DeploymentEnvironment.PROD,
            deployed_at=deployed_at,
        ),
        _make(
            version="1.1.0",
            status=AgentDeploymentStatus.DEPLOYED,
            environment=DeploymentEnvironment.PROD,
            deployed_at=deployed_at,
        ),
    ]

    with pytest.raises(ValueError, match="Multiple active deployments"):
        validate_unique_deployments(deployments)


def test_validate_unique_deployments_allows_same_version_in_different_envs() -> None:
    deployed_at = datetime.now(timezone.utc)
    validate_unique_deployments(
        [
            _make(
                status=AgentDeploymentStatus.DEPLOYED,
                environment=DeploymentEnvironment.STAGING,
                deployed_at=deployed_at,
            ),
            _make(
                status=AgentDeploymentStatus.DEPLOYED,
                environment=DeploymentEnvironment.PROD,
                deployed_at=deployed_at,
            ),
        ]
    )
