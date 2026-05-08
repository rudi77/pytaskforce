"""Workflow checkpoint routes for resumable human-in-the-loop flows."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from taskforce.api.dependencies import (
    get_executor,
    get_factory,
    get_workflow_runtime_service,
    require_permission,
)
from taskforce.api.errors import http_exception
from taskforce.application.executor import AgentExecutor
from taskforce.application.factory import AgentFactory
from taskforce.application.workflow_runtime_service import WorkflowRuntimeService
from taskforce.core.domain.workflow_checkpoint import ResumeEvent
from taskforce.core.domain.workflow_definition import WorkflowDefinition, WorkflowStep

router = APIRouter(prefix="/workflows")
logger = structlog.get_logger(__name__)


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
    acp_peer: str | None = None


class WorkflowDefinitionRequest(BaseModel):
    """API payload for saving a workflow definition."""

    workflow_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = ""
    trigger: str = "manual"
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    steps: list[WorkflowStepRequest] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunWorkflowDefinitionRequest(BaseModel):
    """Payload for running a stored workflow definition."""

    session_id: str | None = None


def _workflow_from_request(request: WorkflowDefinitionRequest) -> WorkflowDefinition:
    from taskforce.application.infrastructure_overrides import get_current_tenant_id

    metadata = dict(request.metadata)
    metadata.setdefault("tenant_id", get_current_tenant_id())
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
                acp_peer=step.acp_peer,
            )
            for step in request.steps
        ],
        trigger_config=request.trigger_config,
        metadata=metadata,
    )


@router.get("/definitions")
def list_workflow_definitions(
    _permission: None = Depends(require_permission("agent:read")),
    service: WorkflowRuntimeService = Depends(get_workflow_runtime_service),
) -> dict[str, Any]:
    """List first-class workflow definitions."""
    return {
        "success": True,
        "workflows": [definition.to_dict() for definition in service.list_definitions()],
    }


@router.post("/definitions")
async def save_workflow_definition(
    request: WorkflowDefinitionRequest,
    _permission: None = Depends(require_permission("agent:update")),
    service: WorkflowRuntimeService = Depends(get_workflow_runtime_service),
) -> dict[str, Any]:
    """Create or update a first-class workflow definition.

    ADR-022 §7 / G3: when the definition's trigger is ``schedule``, the
    runtime mirror-registers the cron job in the framework's scheduler
    so the workflow actually fires on its expression. Re-saving with a
    different cron is idempotent — the prior job is removed first.
    Removing the schedule trigger entirely also removes the registered
    job.
    """
    try:
        definition = service.save_definition(_workflow_from_request(request))
    except ValueError as exc:
        raise http_exception(
            status_code=400, code="invalid_workflow", message=str(exc)
        ) from exc
    job_id = await service.register_schedule_for(definition)
    return {
        "success": True,
        "workflow": definition.to_dict(),
        "scheduled_job_id": job_id,
    }


@router.get("/definitions/{workflow_id}")
def get_workflow_definition(
    workflow_id: str,
    _permission: None = Depends(require_permission("agent:read")),
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
async def delete_workflow_definition(
    workflow_id: str,
    _permission: None = Depends(require_permission("agent:delete")),
    service: WorkflowRuntimeService = Depends(get_workflow_runtime_service),
) -> dict[str, Any]:
    """Delete a first-class workflow definition and its scheduled job."""
    deleted = service.delete_definition(workflow_id)
    if not deleted:
        raise http_exception(
            status_code=404,
            code="not_found",
            message=f"Workflow definition not found: {workflow_id}",
        )
    # ADR-022 §7 / G3: also drop any cron job that mirrored this
    # definition's schedule trigger.
    await service.unregister_schedule_for(workflow_id)
    return {"success": True, "deleted": True}


async def _execute_workflow_steps(
    workflow_id: str,
    service: WorkflowRuntimeService,
    executor: AgentExecutor,
    session_id: str | None,
) -> list[dict[str, Any]]:
    """Run a workflow's steps and return per-step results.

    Independent steps in the same dependency level run in parallel
    (ADR-022 §7, G6). Delegates to ``WorkflowRuntimeService.run_workflow_id``
    so the explicit ``/run`` endpoint and the webhook-trigger endpoint
    see identical execution semantics.
    """
    return await service.run_workflow_id(workflow_id, executor, session_id=session_id)


@router.post("/definitions/{workflow_id}/run")
async def run_workflow_definition(
    workflow_id: str,
    request: RunWorkflowDefinitionRequest,
    _permission: None = Depends(require_permission("agent:execute")),
    service: WorkflowRuntimeService = Depends(get_workflow_runtime_service),
    executor: AgentExecutor = Depends(get_executor),
) -> dict[str, Any]:
    """Run a first-class workflow definition sequentially by dependency order."""
    logger.info(
        "workflow.definition.run_requested",
        workflow_id=workflow_id,
        session_id=request.session_id,
    )
    try:
        results = await _execute_workflow_steps(workflow_id, service, executor, request.session_id)
    except ValueError as exc:
        logger.warning(
            "workflow.definition.run_rejected",
            workflow_id=workflow_id,
            error=str(exc),
        )
        raise http_exception(status_code=400, code="invalid_workflow", message=str(exc)) from exc

    logger.info(
        "workflow.definition.run_completed",
        workflow_id=workflow_id,
        step_count=len(results),
    )
    return {
        "success": True,
        "workflow_id": workflow_id,
        "steps": results,
    }


def _resolve_webhook_secret(trigger_config: dict[str, Any]) -> str | None:
    """Pull the webhook HMAC secret from the trigger config.

    Operators can supply the secret either inline (``trigger_config.secret``)
    or by environment-variable reference (``trigger_config.secret_env``).
    The env-var form is preferred because YAML definitions land on disk
    and may be checked into source control. Returns ``None`` when no
    secret is configured at all — that turns the webhook into an open
    endpoint, which is the operator's explicit choice.
    """
    secret = trigger_config.get("secret")
    if isinstance(secret, str) and secret:
        return secret
    env_var = trigger_config.get("secret_env")
    if isinstance(env_var, str) and env_var:
        return os.getenv(env_var)
    return None


def _verify_webhook_signature(
    body: bytes,
    trigger_config: dict[str, Any],
    headers: dict[str, str],
) -> bool:
    """Verify an HMAC signature carried in the request headers.

    Supports the two common formats:

    * Plain hex digest (``X-Signature: abc123...``)
    * GitHub-style ``<algo>=<hex>`` (``X-Hub-Signature-256: sha256=abc...``)

    The secret is read via :func:`_resolve_webhook_secret`. If no secret
    is configured this returns ``True`` — the operator opted into an
    unsigned webhook. Returns ``False`` when a secret IS configured but
    the header is missing or the digest does not match.
    """
    secret = _resolve_webhook_secret(trigger_config)
    if secret is None:
        return True

    header_name = trigger_config.get("signature_header") or "X-Signature"
    algo = (trigger_config.get("signature_algo") or "sha256").lower()
    if algo not in {"sha1", "sha256", "sha512"}:
        return False

    # FastAPI normalises header lookups; mimic that here.
    received = (
        headers.get(header_name)
        or headers.get(header_name.lower())
        or headers.get(header_name.title())
    )
    if not received:
        return False

    # Strip an optional ``<algo>=`` prefix.
    if "=" in received:
        prefix, _, digest_hex = received.partition("=")
        if prefix.lower() != algo:
            return False
    else:
        digest_hex = received

    expected = hmac.new(
        secret.encode("utf-8"),
        body,
        getattr(hashlib, algo),
    ).hexdigest()
    return hmac.compare_digest(expected.lower(), digest_hex.strip().lower())


@router.post("/webhooks/{trigger_path:path}")
async def trigger_workflow_webhook(
    trigger_path: str,
    request: Request,
    service: WorkflowRuntimeService = Depends(get_workflow_runtime_service),
    executor: AgentExecutor = Depends(get_executor),
) -> dict[str, Any]:
    """Run the workflow whose ``webhook`` trigger matches ``trigger_path``.

    ADR-022 §7: a workflow definition with::

        trigger: webhook
        trigger_config:
          path: hooks/daily-report
          secret_env: GITHUB_WEBHOOK_SECRET   # or: secret: <inline>
          signature_header: X-Hub-Signature-256
          signature_algo: sha256

    becomes reachable at ``POST /api/v1/workflows/webhooks/hooks/daily-report``.
    The route bypasses the auth middleware (the path prefix is in
    ``exempt_path_prefixes``) and verifies the per-workflow HMAC
    signature itself before invoking the runtime. With no secret
    configured the webhook is open — that is the operator's choice and
    must be made deliberately.

    Tenant routing (WF-05): the route is auth-exempt so it has no
    tenant in the request context. We first try the framework's
    current-tenant store; on a miss, we ask
    :func:`get_webhook_workflow_resolver` which tenant owns the path
    and re-run the lookup + execute under that tenant via
    :func:`get_tenant_context_runner`. With no resolver installed
    (single-tenant builds) behaviour is unchanged.
    """
    raw_body = await request.body()
    headers = dict(request.headers.items())

    async def _execute_with(svc: WorkflowRuntimeService, ex: AgentExecutor) -> dict[str, Any]:
        definition = svc.find_webhook_workflow(trigger_path)
        if definition is None:
            raise http_exception(
                status_code=404,
                code="webhook_workflow_not_found",
                message=f"No workflow registered for webhook path: {trigger_path}",
            )
        if not _verify_webhook_signature(
            body=raw_body,
            trigger_config=dict(definition.trigger_config or {}),
            headers=headers,
        ):
            raise http_exception(
                status_code=401,
                code="invalid_webhook_signature",
                message="Webhook signature verification failed.",
            )

        payload: Any = None
        if raw_body:
            try:
                payload = json.loads(raw_body)
            except json.JSONDecodeError:
                payload = None
        session_id = None
        if isinstance(payload, dict):
            raw_session = payload.get("session_id")
            if isinstance(raw_session, str) and raw_session:
                session_id = raw_session

        try:
            results = await _execute_workflow_steps(
                definition.workflow_id, svc, ex, session_id
            )
        except ValueError as exc:
            raise http_exception(
                status_code=400, code="invalid_workflow", message=str(exc)
            ) from exc
        return {
            "success": True,
            "workflow_id": definition.workflow_id,
            "trigger_path": trigger_path,
            "steps": results,
        }

    # Fast path: workflow lives in the current tenant.
    if service.find_webhook_workflow(trigger_path) is not None:
        return await _execute_with(service, executor)

    # Cross-tenant fallback: ask the resolver who owns this path, then
    # re-enter under that tenant's context.
    from taskforce.application.infrastructure_overrides import (
        get_tenant_context_runner,
        get_webhook_workflow_resolver,
    )

    resolver = get_webhook_workflow_resolver()
    runner = get_tenant_context_runner()
    if resolver is not None and runner is not None:
        owner_tenant_id = await resolver(trigger_path)
        if owner_tenant_id:

            async def _within_tenant() -> dict[str, Any]:
                # Resolve the per-tenant runtime+executor under the new
                # tenant context. This mirrors how the schedule
                # dispatcher hands a tenant tick off to the right tenant.
                fresh_service = get_workflow_runtime_service()
                fresh_executor = get_executor()
                return await _execute_with(fresh_service, fresh_executor)

            return await runner(owner_tenant_id, _within_tenant)

    # No resolver installed (single-tenant) or the resolver doesn't
    # know the path — original 404 behaviour.
    raise http_exception(
        status_code=404,
        code="webhook_workflow_not_found",
        message=f"No workflow registered for webhook path: {trigger_path}",
    )


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
