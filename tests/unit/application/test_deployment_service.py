from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from taskforce.application.deployment_service import (
    DeploymentReadinessError,
    DeploymentService,
)


def test_validate_readiness_marks_failed_when_profile_missing() -> None:
    service = DeploymentService(factory=MagicMock())
    deployment = {"status": "pending"}

    with pytest.raises(DeploymentReadinessError) as exc_info:
        service.validate_readiness(deployment=deployment)

    assert exc_info.value.code == "invalid_agent_config"
    assert deployment["status"] == "failed"


def test_validate_readiness_rejects_unknown_native_tools() -> None:
    factory = MagicMock()
    factory.get_profile_config.return_value = {
        "tools": ["not_a_real_tool"],
        "agent": {"planning_strategy": "native_react"},
    }
    service = DeploymentService(factory=factory)

    with pytest.raises(DeploymentReadinessError) as exc_info:
        service.validate_readiness(deployment={"profile": "demo"})

    assert exc_info.value.code == "invalid_tool_config"


def test_validate_readiness_dry_run_failure_marks_deployment_failed() -> None:
    factory = MagicMock()
    factory.get_profile_config.return_value = {
        "tools": [],
        "agent": {"planning_strategy": "native_react"},
    }
    factory.create_agent.side_effect = RuntimeError("boom")
    service = DeploymentService(factory=factory)
    deployment = {"profile": "demo", "status": "pending"}

    with pytest.raises(DeploymentReadinessError) as exc_info:
        service.validate_readiness(deployment=deployment, dry_run=True)

    assert exc_info.value.code == "agent_instantiation_failed"
    assert deployment["status"] == "failed"
