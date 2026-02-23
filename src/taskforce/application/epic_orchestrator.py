"""Epic orchestration for planner/worker/judge workflows."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

import structlog

from taskforce.application.epic_state_store import EpicStateStore, create_epic_state_store
from taskforce.application.factory import AgentFactory
from taskforce.core.domain.epic import EpicRunResult, EpicTask, EpicTaskResult
from taskforce.core.domain.sub_agents import build_sub_agent_session_id
from taskforce.core.interfaces.messaging import MessageBusProtocol
from taskforce.core.utils.time import utc_now as _utc_now


def _build_planner_prompt(
    mission: str,
    scope: str | None,
    state_context: str | None,
) -> str:
    """Build planner mission prompt for task generation."""
    scope_text = f"\n\nScope focus: {scope}" if scope else ""
    state_text = f"\n\n{state_context}" if state_context else ""
    return (
        "You are a planner. Produce a JSON array of tasks with fields: "
        "task_id (optional), title, description, acceptance_criteria (list of strings). "
        "Keep each task independent and assignable to a worker."
        f"\n\nEpic mission: {mission}{scope_text}{state_text}"
    )


def _build_worker_prompt(task: EpicTask, epic_context: str) -> str:
    """Build worker mission prompt for task execution."""
    criteria = "\n".join(f"- {item}" for item in task.acceptance_criteria)
    criteria_text = f"\nAcceptance criteria:\n{criteria}" if criteria else ""
    return (
        f"Epic context: {epic_context}\n\n"
        f"Task {task.task_id}: {task.title}\n{task.description}"
        f"{criteria_text}\n\n"
        "Implement the task fully. Update files and tests as needed. "
        "Summarize changes and test results at the end."
    )


def _build_judge_prompt(
    epic_context: str,
    worker_results: list[EpicTaskResult],
    auto_commit: bool,
    commit_message: str | None,
    round_index: int,
) -> str:
    """Build judge mission prompt for consolidation."""
    summaries = "\n".join(
        f"- {result.task_id}: {result.status} ({result.summary})"
        for result in worker_results
    )
    commit_text = (
        "If changes are correct, commit them using git." if auto_commit else ""
    )
    commit_hint = f"Commit message: {commit_message}." if commit_message else ""
    return (
        f"Epic context: {epic_context}\n\nWorker summaries:\n{summaries}\n\n"
        "Review the code changes in the repo, consolidate any conflicts, "
        "and ensure the epic is coherent. "
        f"{commit_text} {commit_hint}"
        "\n\nReturn JSON with fields: summary (string), continue (boolean). "
        f"Round: {round_index}."
    ).strip()


def _extract_json_payload(text: str) -> str | None:
    """Extract JSON array payload from text."""
    fenced = re.search(r"```json\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    bracket = re.search(r"(\[\s*\{.*\}\s*\])", text, re.DOTALL)
    return bracket.group(1) if bracket else None


def _extract_json_object(text: str) -> str | None:
    """Extract JSON object payload from text."""
    fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    inline = re.search(r"(\{[\s\S]*\})", text)
    return inline.group(1) if inline else None


_module_logger = structlog.get_logger(__name__)


def _parse_task_payload(payload: str) -> list[dict[str, Any]]:
    """Parse JSON payload into task dicts."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        _module_logger.warning(
            "epic.task_payload_parse_failed",
            error=str(exc),
            payload_snippet=payload[:200],
        )
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    _module_logger.warning(
        "epic.task_payload_unexpected_type",
        actual_type=type(data).__name__,
        payload_snippet=payload[:200],
    )
    return []


def _parse_json_object(payload: str) -> dict[str, Any]:
    """Parse JSON object payload."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        _module_logger.warning(
            "epic.json_object_parse_failed",
            error=str(exc),
            payload_snippet=payload[:200],
        )
        return {}
    if isinstance(data, dict):
        return data
    _module_logger.warning(
        "epic.json_object_unexpected_type",
        actual_type=type(data).__name__,
        payload_snippet=payload[:200],
    )
    return {}


def _parse_bullet_tasks(text: str) -> list[dict[str, Any]]:
    """Fallback parser for bullet list tasks."""
    tasks = []
    for line in text.splitlines():
        candidate = line.strip().lstrip("-*").strip()
        if candidate:
            tasks.append({"title": candidate, "description": candidate})
    return tasks


def _normalize_tasks(task_dicts: list[dict[str, Any]], source: str) -> list[EpicTask]:
    """Normalize raw task dicts into EpicTask objects."""
    normalized: list[EpicTask] = []
    for index, payload in enumerate(task_dicts, start=1):
        task_id = str(payload.get("task_id") or f"task-{index}")
        title = str(payload.get("title") or payload.get("description") or task_id)
        description = str(payload.get("description") or title)
        criteria = payload.get("acceptance_criteria") or []
        normalized.append(
            EpicTask(
                task_id=task_id,
                title=title,
                description=description,
                acceptance_criteria=[str(item) for item in criteria],
                source=source,
            )
        )
    return normalized


@dataclass
class _EpicRunContext:
    """Bundles the immutable parameters of an epic run to reduce arg-passing."""

    run_id: str
    mission: str
    state_store: EpicStateStore
    planner_profile: str
    worker_profile: str
    judge_profile: str
    worker_count: int
    max_rounds: int
    sub_planner_scopes: list[str]
    auto_commit: bool
    commit_message: str | None
    started_at: datetime


class EpicOrchestrator:
    """Coordinate planner, worker, and judge agents for epic workflows."""

    def __init__(
        self,
        factory: AgentFactory | None = None,
        message_bus: MessageBusProtocol | None = None,
    ) -> None:
        self._factory = factory or AgentFactory()
        if message_bus is None:
            from taskforce.application.infrastructure_builder import InfrastructureBuilder

            message_bus = InfrastructureBuilder().build_message_bus()
        self._bus = message_bus
        self._logger = structlog.get_logger().bind(component="epic_orchestrator")

    async def run_epic(
        self,
        mission: str,
        *,
        planner_profile: str,
        worker_profile: str,
        judge_profile: str,
        worker_count: int,
        max_rounds: int = 3,
        sub_planner_scopes: list[str] | None = None,
        auto_commit: bool = False,
        commit_message: str | None = None,
    ) -> EpicRunResult:
        """Run an epic orchestration cycle."""
        run_id = uuid4().hex[:8]
        state_store = create_epic_state_store(run_id)
        state_store.initialize(mission)
        ctx = _EpicRunContext(
            run_id=run_id,
            mission=mission,
            state_store=state_store,
            planner_profile=planner_profile,
            worker_profile=worker_profile,
            judge_profile=judge_profile,
            worker_count=worker_count,
            max_rounds=max_rounds,
            sub_planner_scopes=sub_planner_scopes or [],
            auto_commit=auto_commit,
            commit_message=commit_message,
            started_at=_utc_now(),
        )
        self._log_run_start(
            run_id,
            planner_profile=planner_profile,
            worker_profile=worker_profile,
            judge_profile=judge_profile,
            worker_count=worker_count,
        )
        return await self._run_rounds(ctx)

    async def _run_rounds(self, ctx: _EpicRunContext) -> EpicRunResult:
        """Execute planning/worker/judge rounds until done or max reached."""
        tasks, worker_results, round_summaries, start_round = self._restore_checkpoint(
            ctx.state_store
        )
        status = "completed"

        for round_index in range(start_round, ctx.max_rounds + 1):
            round_result = await self._run_round(ctx, round_index)
            status = self._apply_round_result(
                round_result,
                tasks=tasks,
                worker_results=worker_results,
                round_summaries=round_summaries,
                round_index=round_index,
                max_rounds=ctx.max_rounds,
            )
            ctx.state_store.save_checkpoint(
                last_completed_round=round_index,
                tasks=tasks,
                worker_results=worker_results,
                round_summaries=round_summaries,
                status=status,
            )
            if not round_result["continue"]:
                break

        return self._build_run_result(
            ctx.run_id, tasks, worker_results, round_summaries, status, ctx.started_at
        )

    def _restore_checkpoint(
        self, state_store: EpicStateStore
    ) -> tuple[list[EpicTask], list[EpicTaskResult], list[dict[str, Any]], int]:
        """Restore accumulated state from a checkpoint file if available.

        Returns (tasks, worker_results, round_summaries, start_round).
        ``start_round`` is 1 when no checkpoint exists, otherwise the
        round after the last completed one.
        """
        checkpoint = state_store.load_checkpoint()
        if checkpoint is None:
            return [], [], [], 1

        last_round = int(checkpoint.get("last_completed_round", 0))
        tasks = [EpicTask.from_dict(t) for t in checkpoint.get("tasks", [])]
        worker_results = [
            EpicTaskResult(**r) for r in checkpoint.get("worker_results", [])
        ]
        round_summaries: list[dict[str, Any]] = checkpoint.get("round_summaries", [])
        self._logger.info(
            "epic.checkpoint_restored",
            last_completed_round=last_round,
            task_count=len(tasks),
            result_count=len(worker_results),
        )
        return tasks, worker_results, round_summaries, last_round + 1

    async def _run_round(
        self, ctx: _EpicRunContext, round_index: int
    ) -> dict[str, Any]:
        """Execute a single planning → workers → judge round."""
        tasks = await self._plan_tasks(
            ctx.run_id,
            ctx.mission,
            ctx.planner_profile,
            ctx.sub_planner_scopes,
            ctx.state_store,
        )
        await self._publish_tasks(tasks, ctx.worker_count)
        worker_results = await self._run_workers(
            ctx.run_id, ctx.mission, ctx.worker_profile, ctx.worker_count
        )
        judge_summary = await self._run_judge(
            ctx.run_id,
            ctx.mission,
            worker_results,
            ctx.judge_profile,
            ctx.auto_commit,
            ctx.commit_message,
            round_index,
        )
        decision = self._parse_judge_decision(judge_summary)
        self._persist_round_state(ctx.state_store, round_index, decision, tasks, worker_results)
        return {
            "tasks": tasks,
            "worker_results": worker_results,
            "summary": {
                "round": round_index,
                "summary": decision["summary"],
                "continue": decision["continue"],
            },
            "continue": decision["continue"],
        }

    def _persist_round_state(
        self,
        state_store: EpicStateStore,
        round_index: int,
        decision: dict[str, Any],
        tasks: list[EpicTask],
        worker_results: list[EpicTaskResult],
    ) -> None:
        """Write round outcome to the state store and memory log."""
        state_store.update_current_state(
            round_index=round_index,
            judge_summary=decision["summary"],
            tasks=tasks,
            worker_results=worker_results,
        )
        state_store.append_memory(
            round_index=round_index,
            judge_summary=decision["summary"],
            tasks=tasks,
            worker_results=worker_results,
        )

    async def _plan_tasks(
        self,
        run_id: str,
        mission: str,
        planner_profile: str,
        sub_planner_scopes: list[str] | None,
        state_store: EpicStateStore,
    ) -> list[EpicTask]:
        primary_tasks = await self._run_planner(
            run_id, mission, planner_profile, None, state_store
        )
        sub_tasks = await self._run_sub_planners(
            run_id, mission, planner_profile, sub_planner_scopes or [], state_store
        )
        return self._deduplicate_tasks(primary_tasks + sub_tasks)

    async def _run_planner(
        self,
        run_id: str,
        mission: str,
        planner_profile: str,
        scope: str | None,
        state_store: EpicStateStore,
    ) -> list[EpicTask]:
        prompt = _build_planner_prompt(
            mission, scope, state_store.format_state_context()
        )
        agent = await self._factory.create_agent(profile=planner_profile)
        try:
            session_id = build_sub_agent_session_id(run_id, scope or "planner")
            result = await agent.execute(prompt, session_id)
            return self._parse_tasks(result.final_message, scope or "planner")
        finally:
            await agent.close()

    async def _run_sub_planners(
        self,
        run_id: str,
        mission: str,
        planner_profile: str,
        scopes: list[str],
        state_store: EpicStateStore,
    ) -> list[EpicTask]:
        tasks: list[EpicTask] = []
        for scope in scopes:
            tasks.extend(
                await self._run_planner(run_id, mission, planner_profile, scope, state_store)
            )
        return tasks

    async def _publish_tasks(self, tasks: list[EpicTask], worker_count: int) -> None:
        for task in tasks:
            await self._bus.publish("epic.tasks", task.to_dict())
        for _ in range(worker_count):
            await self._bus.publish("epic.tasks", {"type": "shutdown"})

    async def _run_workers(
        self,
        run_id: str,
        mission: str,
        worker_profile: str,
        worker_count: int,
    ) -> list[EpicTaskResult]:
        results: list[EpicTaskResult] = []
        lock = asyncio.Lock()
        tasks = [
            asyncio.create_task(
                self._worker_loop(run_id, mission, worker_profile, results, lock)
            )
            for _ in range(worker_count)
        ]
        await asyncio.gather(*tasks)
        return results

    async def _worker_loop(
        self,
        run_id: str,
        mission: str,
        worker_profile: str,
        results: list[EpicTaskResult],
        lock: asyncio.Lock,
    ) -> None:
        agent = await self._factory.create_agent(profile=worker_profile)
        try:
            async for message in await self._bus.subscribe("epic.tasks"):
                payload = message.payload
                if payload.get("type") == "shutdown":
                    await self._bus.ack(message.message_id)
                    break
                task = EpicTask.from_dict(payload)
                result = await self._execute_worker(agent, run_id, mission, task)
                async with lock:
                    results.append(result)
                await self._bus.ack(message.message_id)
        finally:
            await agent.close()

    async def _execute_worker(
        self,
        agent: Any,
        run_id: str,
        mission: str,
        task: EpicTask,
    ) -> EpicTaskResult:
        session_id = build_sub_agent_session_id(run_id, f"worker_{task.task_id}")
        prompt = _build_worker_prompt(task, mission)
        result = await agent.execute(prompt, session_id)
        status = "completed" if result.status == "completed" else result.status
        summary = (result.final_message or "").strip()
        return EpicTaskResult(
            task_id=task.task_id,
            worker_session_id=session_id,
            status=status,
            summary=summary,
        )

    async def _run_judge(
        self,
        run_id: str,
        mission: str,
        worker_results: list[EpicTaskResult],
        judge_profile: str,
        auto_commit: bool,
        commit_message: str | None,
        round_index: int,
    ) -> str:
        prompt = _build_judge_prompt(
            mission, worker_results, auto_commit, commit_message, round_index
        )
        agent = await self._factory.create_agent(profile=judge_profile)
        try:
            session_id = build_sub_agent_session_id(run_id, "judge")
            result = await agent.execute(prompt, session_id)
            return result.final_message or ""
        finally:
            await agent.close()

    def _parse_tasks(self, output: str, source: str) -> list[EpicTask]:
        payload = _extract_json_payload(output)
        task_dicts = _parse_task_payload(payload) if payload else []
        if not task_dicts:
            self._logger.info(
                "epic.task_parse_fallback_to_bullets",
                source=source,
                json_payload_found=payload is not None,
            )
            task_dicts = _parse_bullet_tasks(output)
        if not task_dicts:
            self._logger.warning(
                "epic.no_tasks_parsed",
                source=source,
                output_snippet=output[:200],
            )
        return _normalize_tasks(task_dicts, source)

    def _deduplicate_tasks(self, tasks: list[EpicTask]) -> list[EpicTask]:
        seen: set[str] = set()
        unique: list[EpicTask] = []
        for task in tasks:
            key = task.title.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(task)
        return unique

    def _build_run_result(
        self,
        run_id: str,
        tasks: list[EpicTask],
        worker_results: list[EpicTaskResult],
        round_summaries: list[dict[str, Any]],
        status: str,
        started_at: datetime,
    ) -> EpicRunResult:
        judge_summary = round_summaries[-1]["summary"] if round_summaries else ""
        return EpicRunResult(
            run_id=run_id,
            started_at=started_at,
            completed_at=_utc_now(),
            status=status,
            tasks=tasks,
            worker_results=worker_results,
            judge_summary=judge_summary,
            round_summaries=round_summaries,
        )

    def _apply_round_result(
        self,
        round_result: dict[str, Any],
        *,
        tasks: list[EpicTask],
        worker_results: list[EpicTaskResult],
        round_summaries: list[dict[str, Any]],
        round_index: int,
        max_rounds: int,
    ) -> str:
        tasks.extend(round_result["tasks"])
        worker_results.extend(round_result["worker_results"])
        round_summaries.append(round_result["summary"])
        if round_result["continue"] and round_index == max_rounds:
            return "max_rounds_reached"
        return "completed"

    def _parse_judge_decision(self, output: str) -> dict[str, Any]:
        payload = _extract_json_object(output)
        decision = _parse_json_object(payload) if payload else {}
        return {
            "summary": str(decision.get("summary") or output).strip(),
            "continue": bool(decision.get("continue", False)),
        }

    def _log_run_start(
        self,
        run_id: str,
        *,
        planner_profile: str,
        worker_profile: str,
        judge_profile: str,
        worker_count: int,
    ) -> None:
        self._logger.info(
            "epic_run_start",
            run_id=run_id,
            planner_profile=planner_profile,
            worker_profile=worker_profile,
            judge_profile=judge_profile,
            worker_count=worker_count,
        )
