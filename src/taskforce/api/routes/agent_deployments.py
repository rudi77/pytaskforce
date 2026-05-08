"""Agent deployment routes — deploy, rollback, history, active version.

All routes delegate to :class:`AgentDeploymentService` which is wired
via :func:`get_agent_deployment_service` (see ``api/dependencies.py``).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from taskforce.api.dependencies import get_agent_deployment_service, require_permission
from taskforce.api.errors import http_exception
from taskforce.api.schemas.agent_deployment_schemas import (
    AgentDeploymentListResponse,
    AgentDeploymentResponse,
    DeployRequest,
    RollbackRequest,
)
from taskforce.api.schemas.errors import ErrorResponse
from taskforce.application.agent_deployment_service import (
    AgentDeploymentService,
    DeploymentPreflightError,
)
from taskforce.core.domain.agent_deployment import DeploymentEnvironment

router = APIRouter()


def _preflight_to_http(exc: DeploymentPreflightError):
    """Map preflight errors to standard HTTP responses."""
    code_to_status = {
        "agent_not_found": status.HTTP_404_NOT_FOUND,
        "rollback_target_not_found": status.HTTP_404_NOT_FOUND,
        "agent_not_custom": status.HTTP_409_CONFLICT,
    }
    return http_exception(
        status_code=code_to_status.get(exc.code, status.HTTP_400_BAD_REQUEST),
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )


@router.post(
    "/agents/{agent_id}/deploy",
    response_model=AgentDeploymentResponse,
    status_code=status.HTTP_200_OK,
    summary="Deploy a custom agent",
    description=(
        "Validate and deploy the current definition of a custom agent. "
        "On success the agent becomes the active version for the target "
        "environment and is immediately available to ``POST /api/v1/execute``."
    ),
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def deploy_agent(
    agent_id: str,
    request: DeployRequest | None = None,
    _permission: None = Depends(require_permission("agent:update")),
    service: AgentDeploymentService = Depends(get_agent_deployment_service),
) -> AgentDeploymentResponse:
    payload = request or DeployRequest()
    try:
        deployment = service.deploy(
            agent_id,
            environment=payload.environment,
            deployed_by=payload.deployed_by,
            message=payload.message,
        )
    except DeploymentPreflightError as exc:
        raise _preflight_to_http(exc) from exc
    return AgentDeploymentResponse.from_domain(deployment)


@router.post(
    "/agents/{agent_id}/rollback",
    response_model=AgentDeploymentResponse,
    summary="Roll back to a previously deployed version",
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def rollback_agent(
    agent_id: str,
    request: RollbackRequest,
    _permission: None = Depends(require_permission("agent:update")),
    service: AgentDeploymentService = Depends(get_agent_deployment_service),
) -> AgentDeploymentResponse:
    try:
        deployment = service.rollback(
            agent_id,
            to_version=request.to_version,
            environment=request.environment,
            deployed_by=request.deployed_by,
            message=request.message,
        )
    except DeploymentPreflightError as exc:
        raise _preflight_to_http(exc) from exc
    return AgentDeploymentResponse.from_domain(deployment)


@router.get(
    "/agents/{agent_id}/deployments",
    response_model=AgentDeploymentListResponse,
    summary="List deployment history (newest first)",
)
def list_deployments(
    agent_id: str,
    _permission: None = Depends(require_permission("agent:read")),
    service: AgentDeploymentService = Depends(get_agent_deployment_service),
) -> AgentDeploymentListResponse:
    history = service.list_history(agent_id)
    return AgentDeploymentListResponse(
        deployments=[AgentDeploymentResponse.from_domain(d) for d in history]
    )


@router.get(
    "/agents/{agent_id}/active",
    response_model=AgentDeploymentResponse,
    summary="Get the currently active deployment for an environment",
    responses={404: {"model": ErrorResponse}},
)
def get_active_deployment(
    agent_id: str,
    environment: DeploymentEnvironment = Query(default=DeploymentEnvironment.LOCAL),
    _permission: None = Depends(require_permission("agent:read")),
    service: AgentDeploymentService = Depends(get_agent_deployment_service),
) -> AgentDeploymentResponse:
    deployment = service.get_active(agent_id, environment)
    if deployment is None:
        raise http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="deployment_not_found",
            message=(
                f"No active deployment found for agent '{agent_id}' "
                f"in environment '{environment.value}'."
            ),
        )
    return AgentDeploymentResponse.from_domain(deployment)
