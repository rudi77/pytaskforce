"""Agent deployment routes for deploy, rollback, and status visibility."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from taskforce.api.errors import http_exception
from taskforce.api.schemas.errors import ErrorResponse

router = APIRouter()


class DeploymentActionRequest(BaseModel):
    """Request payload for deployment actions."""

    version: str = Field(..., min_length=1)
    environment: str = Field(default="production", min_length=1)
    message: str | None = None


class AgentDeploymentResponse(BaseModel):
    """Standard deployment response for UI progress/status rendering."""

    status: Literal["queued", "in_progress", "success", "failed", "rolled_back"]
    version: str
    environment: str
    message: str
    timestamp: datetime


class AgentDeploymentListResponse(BaseModel):
    """Deployment history response."""

    deployments: list[AgentDeploymentResponse]


_DEPLOYMENTS: dict[str, list[AgentDeploymentResponse]] = {}


def _require_agent(agent_id: str) -> None:
    """Validate an agent identifier before deployment actions."""
    if not agent_id.strip():
        raise http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_agent_id",
            message="agent_id must not be empty",
        )


def _latest_deployment(agent_id: str) -> AgentDeploymentResponse:
    """Return latest deployment or raise standardized 404 error."""
    deployments = _DEPLOYMENTS.get(agent_id, [])
    if not deployments:
        raise http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="deployment_not_found",
            message=f"No deployments found for agent '{agent_id}'",
        )
    return deployments[-1]


@router.post(
    "/agents/{agent_id}/deploy",
    response_model=AgentDeploymentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def deploy_agent(agent_id: str, request: DeploymentActionRequest) -> AgentDeploymentResponse:
    """Create a deployment record for an agent."""
    _require_agent(agent_id)

    deployment = AgentDeploymentResponse(
        status="queued",
        version=request.version,
        environment=request.environment,
        message=request.message or "Deployment queued",
        timestamp=datetime.now(timezone.utc),
    )
    _DEPLOYMENTS.setdefault(agent_id, []).append(deployment)
    return deployment


@router.post(
    "/agents/{agent_id}/rollback",
    response_model=AgentDeploymentResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def rollback_agent(agent_id: str, request: DeploymentActionRequest) -> AgentDeploymentResponse:
    """Append a rollback record for an agent deployment."""
    _require_agent(agent_id)
    _latest_deployment(agent_id)

    rollback = AgentDeploymentResponse(
        status="rolled_back",
        version=request.version,
        environment=request.environment,
        message=request.message or "Rollback completed",
        timestamp=datetime.now(timezone.utc),
    )
    _DEPLOYMENTS.setdefault(agent_id, []).append(rollback)
    return rollback


@router.get(
    "/agents/{agent_id}/deployments",
    response_model=AgentDeploymentListResponse,
    responses={400: {"model": ErrorResponse}},
)
def list_deployments(agent_id: str) -> AgentDeploymentListResponse:
    """List known deployments for an agent."""
    _require_agent(agent_id)
    return AgentDeploymentListResponse(deployments=_DEPLOYMENTS.get(agent_id, []))


@router.get(
    "/agents/{agent_id}/active",
    response_model=AgentDeploymentResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_active_deployment(agent_id: str) -> AgentDeploymentResponse:
    """Return the currently active deployment for an agent."""
    _require_agent(agent_id)
    return _latest_deployment(agent_id)
