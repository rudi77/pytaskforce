"""Workflow checkpoint routes for resumable human-in-the-loop flows."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from taskforce.api.dependencies import get_factory, get_workflow_runtime_service
from taskforce.api.errors import http_exception
from taskforce.application.factory import AgentFactory
from taskforce.application.workflow_runtime_service import WorkflowRuntimeService
from taskforce.core.domain.workflow_checkpoint import ResumeEvent

router = APIRouter(prefix="/workflows")


class CreateWaitCheckpointRequest(BaseModel):
    """Payload for creating a waiting workflow checkpoint."""

    session_id: str = Field(..., min_length=1)
    workflow_name: str = Field(..., min_length=1)
    node_id: str = Field(..., min_length=1)
    blocking_reason: str = Field(..., min_length=1)
    required_inputs: dict[str, Any] = Field(default_factory=dict)
    state: dict[str, Any] = Field(default_factory=dict)
    question: str | None = None
    run_id: str | None = None


class ResumeWorkflowRequest(BaseModel):
    """Payload for resuming a paused workflow."""

    input_type: str = Field(default="human_reply")
    payload: dict[str, Any] = Field(default_factory=dict)
    sender_metadata: dict[str, Any] = Field(default_factory=dict)


class ResumeAndContinueRequest(ResumeWorkflowRequest):
    """Payload for resuming and immediately continuing workflow execution."""

    profile: str = Field(default="dev")


@router.post("/wait")
def create_wait_checkpoint(
    request: CreateWaitCheckpointRequest,
    service: WorkflowRuntimeService = Depends(get_workflow_runtime_service),
) -> dict[str, Any]:
    """Create a waiting checkpoint for a workflow run."""
    checkpoint = service.create_wait_checkpoint(
        session_id=request.session_id,
        workflow_name=request.workflow_name,
        node_id=request.node_id,
        blocking_reason=request.blocking_reason,
        required_inputs=request.required_inputs,
        state=request.state,
        question=request.question,
        run_id=request.run_id,
    )
    return {
        "success": True,
        "run_id": checkpoint.run_id,
        "status": checkpoint.status,
        "node_id": checkpoint.node_id,
        "blocking_reason": checkpoint.blocking_reason,
        "required_inputs": checkpoint.required_inputs,
    }


@router.get("/{run_id}")
def get_checkpoint(
    run_id: str,
    service: WorkflowRuntimeService = Depends(get_workflow_runtime_service),
) -> dict[str, Any]:
    """Get workflow checkpoint by run id."""
    checkpoint = service.get(run_id)
    if checkpoint is None:
        raise http_exception(404, f"Workflow run not found: {run_id}", code="not_found")
    return {"success": True, "checkpoint": checkpoint.to_dict()}


@router.post("/{run_id}/resume")
def resume_workflow(
    run_id: str,
    request: ResumeWorkflowRequest,
    service: WorkflowRuntimeService = Depends(get_workflow_runtime_service),
) -> dict[str, Any]:
    """Resume a waiting workflow with external input payload."""
    event = ResumeEvent(
        run_id=run_id,
        input_type=request.input_type,
        payload=request.payload,
        sender_metadata=request.sender_metadata,
    )
    try:
        checkpoint = service.resume(event)
    except ValueError as exc:
        raise http_exception(400, str(exc), code="invalid_request") from exc

    return {
        "success": True,
        "run_id": checkpoint.run_id,
        "status": checkpoint.status,
        "node_id": checkpoint.node_id,
        "state": checkpoint.state,
    }


@router.post("/{run_id}/resume-and-continue")
async def resume_and_continue_workflow(
    run_id: str,
    request: ResumeAndContinueRequest,
    service: WorkflowRuntimeService = Depends(get_workflow_runtime_service),
    factory: AgentFactory = Depends(get_factory),
) -> dict[str, Any]:
    """Resume checkpoint and continue workflow by re-invoking activate_skill."""
    event = ResumeEvent(
        run_id=run_id,
        input_type=request.input_type,
        payload=request.payload,
        sender_metadata=request.sender_metadata,
    )
    try:
        checkpoint = service.resume(event)
    except ValueError as exc:
        raise http_exception(400, str(exc), code="invalid_request") from exc

    if not checkpoint.session_id:
        raise http_exception(
            400,
            "Checkpoint is missing session_id; cannot continue automatically",
            code="invalid_request",
        )

    agent = await factory.create_agent(profile=request.profile)
    tool = agent.tools.get("activate_skill")
    if tool is None:
        raise http_exception(500, "activate_skill tool is not available", code="tool_error")

    execution = await tool.execute(
        skill_name=checkpoint.workflow_name,
        input={
            "session_id": checkpoint.session_id,
            "resume_run_id": run_id,
            "resume_payload": request.payload,
            "resume_input_type": request.input_type,
            "resume_sender_metadata": request.sender_metadata,
        },
    )
    return {
        "success": True,
        "run_id": run_id,
        "checkpoint_status": checkpoint.status,
        "execution": execution,
    }
