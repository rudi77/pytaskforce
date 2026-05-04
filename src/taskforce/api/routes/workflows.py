"""Workflow checkpoint routes for resumable human-in-the-loop flows."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from taskforce.api.dependencies import get_executor, get_factory, get_workflow_runtime_service
from taskforce.api.errors import http_exception
from taskforce.application.executor import AgentExecutor
from taskforce.application.factory import AgentFactory
from taskforce.application.workflow_runtime_service import WorkflowRuntimeService
from taskforce.core.domain.workflow_checkpoint import ResumeEvent
from taskforce.core.domain.workflow_definition import WorkflowDefinition, WorkflowStep

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

    profile: str = Field(default="butler")


class WorkflowStepRequest(BaseModel):
    """API payload for one workflow step."""

    step_id: str = Field(..., min_length=1)
    agent: str = Field(..., min_length=1)
    task: str = Field(..., min_length=1)
    depends_on: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowDefinitionRequest(BaseModel):
    """API payload for saving a workflow definition."""

    workflow_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = ""
    trigger: str = "manual"
    steps: list[WorkflowStepRequest] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunWorkflowDefinitionRequest(BaseModel):
    """Payload for running a stored workflow definition."""

    session_id: str | None = None


def _workflow_from_request(request: WorkflowDefinitionRequest) -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id=request.workflow_id,
        name=request.name,
        description=request.description,
        trigger=request.trigger,
        steps=[
            WorkflowStep(
                step_id=step.step_id,
                agent=step.agent,
                task=step.task,
                depends_on=step.depends_on,
                metadata=step.metadata,
            )
            for step in request.steps
        ],
        metadata=request.metadata,
    )


@router.get("/definitions")
def list_workflow_definitions(
    service: WorkflowRuntimeService = Depends(get_workflow_runtime_service),
) -> dict[str, Any]:
    """List first-class workflow definitions."""
    return {
        "success": True,
        "workflows": [definition.to_dict() for definition in service.list_definitions()],
    }


@router.post("/definitions")
def save_workflow_definition(
    request: WorkflowDefinitionRequest,
    service: WorkflowRuntimeService = Depends(get_workflow_runtime_service),
) -> dict[str, Any]:
    """Create or update a first-class workflow definition."""
    definition = service.save_definition(_workflow_from_request(request))
    return {"success": True, "workflow": definition.to_dict()}


@router.get("/definitions/{workflow_id}")
def get_workflow_definition(
    workflow_id: str,
    service: WorkflowRuntimeService = Depends(get_workflow_runtime_service),
) -> dict[str, Any]:
    """Get a first-class workflow definition."""
    definition = service.get_definition(workflow_id)
    if definition is None:
        raise http_exception(
            status_code=404,
            code="not_found",
            message=f"Workflow definition not found: {workflow_id}",
        )
    return {"success": True, "workflow": definition.to_dict()}


@router.delete("/definitions/{workflow_id}")
def delete_workflow_definition(
    workflow_id: str,
    service: WorkflowRuntimeService = Depends(get_workflow_runtime_service),
) -> dict[str, Any]:
    """Delete a first-class workflow definition."""
    deleted = service.delete_definition(workflow_id)
    if not deleted:
        raise http_exception(
            status_code=404,
            code="not_found",
            message=f"Workflow definition not found: {workflow_id}",
        )
    return {"success": True, "deleted": True}


async def _execute_workflow_steps(
    workflow_id: str,
    service: WorkflowRuntimeService,
    executor: AgentExecutor,
    session_id: str | None,
) -> list[dict[str, Any]]:
    """Run a workflow's ordered steps and return per-step results.

    Shared by the explicit ``/run`` endpoint and the webhook-trigger
    endpoint so both paths produce identical step result shapes.
    """
    steps = service.ordered_steps(workflow_id)
    results: dict[str, dict[str, Any]] = {}
    for step in steps:
        mission = _mission_for_step(step, results)
        execution = await executor.execute_mission(
            mission=mission,
            profile=step.agent,
            session_id=session_id,
        )
        results[step.step_id] = {
            "step_id": step.step_id,
            "agent": step.agent,
            "status": getattr(execution, "status", "completed"),
            "final_message": getattr(execution, "final_message", ""),
        }
    return list(results.values())


@router.post("/definitions/{workflow_id}/run")
async def run_workflow_definition(
    workflow_id: str,
    request: RunWorkflowDefinitionRequest,
    service: WorkflowRuntimeService = Depends(get_workflow_runtime_service),
    executor: AgentExecutor = Depends(get_executor),
) -> dict[str, Any]:
    """Run a first-class workflow definition sequentially by dependency order."""
    try:
        results = await _execute_workflow_steps(
            workflow_id, service, executor, request.session_id
        )
    except ValueError as exc:
        raise http_exception(status_code=400, code="invalid_workflow", message=str(exc)) from exc

    return {
        "success": True,
        "workflow_id": workflow_id,
        "steps": results,
    }


@router.post("/webhooks/{trigger_path:path}")
async def trigger_workflow_webhook(
    trigger_path: str,
    payload: dict[str, Any] | None = None,
    service: WorkflowRuntimeService = Depends(get_workflow_runtime_service),
    executor: AgentExecutor = Depends(get_executor),
) -> dict[str, Any]:
    """Run the workflow whose ``webhook`` trigger matches ``trigger_path``.

    ADR-022 §7: a workflow definition with::

        trigger: webhook
        trigger_config:
          path: hooks/daily-report

    becomes reachable at ``POST /api/v1/workflows/webhooks/hooks/daily-report``.
    The request body is forwarded into the run via ``session_id`` (when
    provided) — the steps themselves are agent missions, not raw HTTP
    handlers, so any custom payload semantics are the workflow's
    responsibility to interpret.
    """
    definition = service.find_webhook_workflow(trigger_path)
    if definition is None:
        raise http_exception(
            status_code=404,
            code="webhook_workflow_not_found",
            message=f"No workflow registered for webhook path: {trigger_path}",
        )

    session_id = None
    if isinstance(payload, dict):
        raw_session = payload.get("session_id")
        if isinstance(raw_session, str) and raw_session:
            session_id = raw_session

    try:
        results = await _execute_workflow_steps(
            definition.workflow_id, service, executor, session_id
        )
    except ValueError as exc:
        raise http_exception(status_code=400, code="invalid_workflow", message=str(exc)) from exc

    return {
        "success": True,
        "workflow_id": definition.workflow_id,
        "trigger_path": trigger_path,
        "steps": results,
    }


def _mission_for_step(step: WorkflowStep, results: dict[str, dict[str, Any]]) -> str:
    if not step.depends_on:
        return step.task
    dependency_lines = [
        f"- {dependency_id}: {results[dependency_id].get('final_message', '')}"
        for dependency_id in step.depends_on
    ]
    return f"{step.task}\n\nDependency results:\n" + "\n".join(dependency_lines)


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
        raise http_exception(
            status_code=404, code="not_found", message=f"Workflow run not found: {run_id}"
        )
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
        raise http_exception(status_code=400, code="invalid_request", message=str(exc)) from exc

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
        raise http_exception(status_code=400, code="invalid_request", message=str(exc)) from exc

    if not checkpoint.session_id:
        raise http_exception(
            status_code=400,
            code="invalid_request",
            message="Checkpoint is missing session_id; cannot continue automatically",
        )

    agent = await factory.create_agent(profile=request.profile)
    tool = agent.tools.get("activate_skill")
    if tool is None:
        raise http_exception(
            status_code=500,
            code="tool_error",
            message="activate_skill tool is not available",
        )

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
