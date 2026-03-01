"""Application Layer - Workflow Orchestrator.

Coordinates resumable workflow execution with pause/resume, integrating
workflow engines (LangGraph, etc.) with the skill system, persistence,
and the Communication Gateway for async human-in-the-loop input.
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import structlog

from taskforce.core.domain.skill import Skill
from taskforce.core.domain.workflow import (
    WorkflowRunRecord,
    WorkflowRunResult,
    WorkflowStatus,
)
from taskforce.core.interfaces.workflow import (
    WorkflowEngineProtocol,
    WorkflowRunStoreProtocol,
)
from taskforce.core.utils.time import utc_now

logger = structlog.get_logger(__name__)

# Default entrypoint function name in workflow scripts.
DEFAULT_ENTRYPOINT = "create_workflow"


class WorkflowOrchestrator:
    """Orchestrates resumable workflow start, pause, and resume.

    Responsibilities:
    - Load workflow definitions from skill scripts
    - Select and delegate to the appropriate engine
    - Persist workflow run state for pause/resume
    - Integrate with PendingChannelQuestionStore for channel-targeted questions
    """

    def __init__(
        self,
        engines: dict[str, WorkflowEngineProtocol],
        run_store: WorkflowRunStoreProtocol,
        pending_question_store: Any | None = None,
    ) -> None:
        """Initialize the workflow orchestrator.

        Args:
            engines: Mapping of engine name to engine adapter instance.
            run_store: Persistence store for workflow run records.
            pending_question_store: Optional PendingChannelQuestionStoreProtocol
                for registering channel-targeted questions.
        """
        self._engines = engines
        self._run_store = run_store
        self._pending_question_store = pending_question_store

    async def start_workflow(
        self,
        *,
        session_id: str,
        skill: Skill,
        input_data: dict[str, Any],
        tool_executor: Callable[[str, dict[str, Any]], Awaitable[Any]],
    ) -> WorkflowRunResult:
        """Start a skill's workflow script.

        Loads the Python script from the skill directory, calls the
        entrypoint to get the workflow definition, selects the engine,
        and executes the workflow.

        Args:
            session_id: Parent agent session identifier.
            skill: The skill with a ``script`` field.
            input_data: Input variables for the workflow.
            tool_executor: Callback to execute Taskforce tools.

        Returns:
            WorkflowRunResult (may be COMPLETED, WAITING_FOR_INPUT, or FAILED).
        """
        if not skill.has_script:
            return WorkflowRunResult(
                status=WorkflowStatus.FAILED,
                error=f"Skill '{skill.name}' has no script defined.",
            )

        # 1. Load workflow definition from script
        workflow_def = self._load_workflow_definition(skill)
        if workflow_def is None:
            return WorkflowRunResult(
                status=WorkflowStatus.FAILED,
                error=f"Failed to load workflow from '{skill.script}'.",
            )

        # 2. Select engine
        engine_name = skill.script_engine or self._default_engine_name()
        engine = self._engines.get(engine_name)
        if engine is None:
            return WorkflowRunResult(
                status=WorkflowStatus.FAILED,
                error=f"Workflow engine '{engine_name}' not available. "
                f"Installed engines: {list(self._engines.keys())}",
            )

        # 3. Generate run_id and execute
        run_id = str(uuid.uuid4())

        logger.info(
            "workflow.starting",
            run_id=run_id,
            session_id=session_id,
            skill=skill.name,
            engine=engine_name,
        )

        result = await engine.start(
            run_id=run_id,
            workflow_definition=workflow_def,
            input_data=input_data,
            tool_executor=tool_executor,
        )

        # 4. Handle result
        if result.status == WorkflowStatus.WAITING_FOR_INPUT:
            await self._persist_pause(
                run_id=run_id,
                session_id=session_id,
                skill=skill,
                engine=engine,
                engine_name=engine_name,
                input_data=input_data,
                result=result,
            )
        elif result.status == WorkflowStatus.COMPLETED:
            logger.info("workflow.completed", run_id=run_id, skill=skill.name)
        else:
            logger.warning(
                "workflow.failed",
                run_id=run_id,
                skill=skill.name,
                error=result.error,
            )

        return result

    async def resume_workflow(
        self,
        *,
        run_id: str,
        response: str,
        tool_executor: Callable[[str, dict[str, Any]], Awaitable[Any]] | None = None,
        skill: Skill | None = None,
    ) -> WorkflowRunResult:
        """Resume a paused workflow with the human's response.

        Args:
            run_id: The workflow run identifier.
            response: Human's response text.
            tool_executor: Optional tool executor callback. If None,
                a no-op executor is used (tools won't work on resume
                unless the executor is re-provided).
            skill: Optional skill reference for re-registering the
                workflow definition after a process restart.

        Returns:
            WorkflowRunResult (may pause again or complete).
        """
        record = await self._run_store.load(run_id)
        if record is None:
            return WorkflowRunResult(
                status=WorkflowStatus.FAILED,
                error=f"No workflow run found for run_id={run_id}",
            )

        engine = self._engines.get(record.engine)
        if engine is None:
            return WorkflowRunResult(
                status=WorkflowStatus.FAILED,
                error=f"Engine '{record.engine}' not available for resume.",
            )

        executor = tool_executor or _noop_tool_executor

        # Re-register graph if the engine lost it (e.g. after restart).
        if skill and skill.has_script and hasattr(engine, "register_graph"):
            graphs = getattr(engine, "_graphs", {})
            if run_id not in graphs:
                workflow_def = self._load_workflow_definition(skill)
                if workflow_def is not None:
                    engine.register_graph(run_id, workflow_def, executor)
                    logger.info("workflow.graph_re_registered", run_id=run_id)

        logger.info(
            "workflow.resuming",
            run_id=run_id,
            session_id=record.session_id,
            engine=record.engine,
        )

        result = await engine.resume(
            run_id=run_id,
            checkpoint=record.checkpoint,
            response=response,
            tool_executor=executor,
        )

        if result.status == WorkflowStatus.WAITING_FOR_INPUT:
            # Another pause - update the stored record
            record.status = WorkflowStatus.WAITING_FOR_INPUT
            record.checkpoint = engine.get_checkpoint(run_id)
            record.human_input_request = result.human_input_request
            record.updated_at = utc_now()
            await self._run_store.save(record)

            if result.human_input_request and result.human_input_request.channel:
                await self._register_pending_question(record, result)

            logger.info("workflow.paused_again", run_id=run_id)
        else:
            # Completed or failed - clean up
            await self._run_store.delete(run_id)
            await self._remove_pending_question(record)
            logger.info(
                "workflow.resume_completed",
                run_id=run_id,
                status=result.status.value,
            )

        return result

    async def resume_by_session(
        self,
        session_id: str,
        response: str,
        tool_executor: Callable[[str, dict[str, Any]], Awaitable[Any]] | None = None,
    ) -> WorkflowRunResult | None:
        """Resume a workflow by session_id (used by Gateway).

        Args:
            session_id: The agent session identifier.
            response: Human's response text.
            tool_executor: Optional tool executor callback.

        Returns:
            WorkflowRunResult, or None if no active workflow for session.
        """
        record = await self._run_store.load_by_session(session_id)
        if record is None:
            return None
        return await self.resume_workflow(
            run_id=record.run_id,
            response=response,
            tool_executor=tool_executor,
        )

    async def check_timeouts(self) -> list[WorkflowRunRecord]:
        """Check for timed-out workflow runs.

        Returns a list of records that have exceeded their timeout.
        Callers (e.g. Butler daemon) can decide how to handle them.
        """
        waiting = await self._run_store.list_waiting()
        timed_out: list[WorkflowRunRecord] = []
        now = utc_now()
        for record in waiting:
            hir = record.human_input_request
            if hir and hir.timeout_seconds:
                elapsed = (now - record.updated_at).total_seconds()
                if elapsed > hir.timeout_seconds:
                    timed_out.append(record)
        return timed_out

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_workflow_definition(self, skill: Skill) -> Any | None:
        """Load the workflow definition from a skill's Python script."""
        script_path = (Path(skill.source_path) / skill.script).resolve()
        skill_dir = Path(skill.source_path).resolve()
        # Path traversal protection: ensure script is within skill directory
        if not str(script_path).startswith(str(skill_dir)):
            logger.error(
                "workflow.script_path_traversal",
                skill=skill.name,
                path=str(script_path),
            )
            return None
        if not script_path.exists():
            logger.error(
                "workflow.script_not_found",
                skill=skill.name,
                path=str(script_path),
            )
            return None

        entrypoint = skill.script_entrypoint or DEFAULT_ENTRYPOINT

        try:
            module = self._import_script(script_path, skill.name)
            factory_fn = getattr(module, entrypoint, None)
            if factory_fn is None:
                logger.error(
                    "workflow.entrypoint_not_found",
                    skill=skill.name,
                    entrypoint=entrypoint,
                    path=str(script_path),
                )
                return None
            return factory_fn()
        except Exception as exc:
            logger.error(
                "workflow.script_load_failed",
                skill=skill.name,
                path=str(script_path),
                error=str(exc),
            )
            return None

    def _import_script(self, script_path: Path, skill_name: str) -> Any:
        """Import a Python script as a module."""
        module_name = f"taskforce_workflow_{skill_name.replace('-', '_')}"
        spec = importlib.util.spec_from_file_location(module_name, script_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create module spec for {script_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    def _default_engine_name(self) -> str:
        """Return the default engine name (first available)."""
        if self._engines:
            return next(iter(self._engines))
        return "langgraph"

    async def _persist_pause(
        self,
        *,
        run_id: str,
        session_id: str,
        skill: Skill,
        engine: WorkflowEngineProtocol,
        engine_name: str,
        input_data: dict[str, Any],
        result: WorkflowRunResult,
    ) -> None:
        """Persist workflow state on pause."""
        record = WorkflowRunRecord(
            run_id=run_id,
            session_id=session_id,
            workflow_name=skill.name,
            status=WorkflowStatus.WAITING_FOR_INPUT,
            engine=engine_name,
            input_data=input_data,
            checkpoint=engine.get_checkpoint(run_id),
            human_input_request=result.human_input_request,
        )
        await self._run_store.save(record)

        if result.human_input_request and result.human_input_request.channel:
            await self._register_pending_question(record, result)

        logger.info(
            "workflow.paused",
            run_id=run_id,
            session_id=session_id,
            channel=result.human_input_request.channel if result.human_input_request else None,
        )

    async def _register_pending_question(
        self,
        record: WorkflowRunRecord,
        result: WorkflowRunResult,
    ) -> None:
        """Register a pending question for channel-targeted input."""
        if not self._pending_question_store or not result.human_input_request:
            return

        hir = result.human_input_request
        if not hir.channel or not hir.recipient_id:
            return

        try:
            await self._pending_question_store.register(
                session_id=record.session_id,
                channel=hir.channel,
                recipient_id=hir.recipient_id,
                question=hir.question,
                metadata={"workflow_run_id": record.run_id, **hir.metadata},
            )
        except Exception as exc:
            logger.warning(
                "workflow.pending_question_register_failed",
                run_id=record.run_id,
                error=str(exc),
            )

    async def _remove_pending_question(
        self,
        record: WorkflowRunRecord,
    ) -> None:
        """Remove any pending question for a completed/failed workflow."""
        if not self._pending_question_store:
            return
        try:
            if hasattr(self._pending_question_store, "remove"):
                await self._pending_question_store.remove(
                    session_id=record.session_id,
                )
        except Exception as exc:
            logger.debug(
                "workflow.pending_question_remove_failed",
                run_id=record.run_id,
                error=str(exc),
            )


async def _noop_tool_executor(tool_name: str, params: dict[str, Any]) -> Any:
    """No-op tool executor used when no executor is provided on resume."""
    logger.warning("workflow.noop_tool_executor", tool=tool_name)
    return {"success": False, "error": "No tool executor available"}
