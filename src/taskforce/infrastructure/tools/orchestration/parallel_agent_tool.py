"""
Parallel Agent Tool - Execute multiple sub-agent missions concurrently.

Provides a single tool call that spawns N sub-agents in parallel,
controlled by a configurable concurrency limit. Results are aggregated
and returned as a batch.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import structlog

from taskforce.core.domain.sub_agents import SubAgentSpec
from taskforce.core.interfaces.sub_agents import SubAgentSpawnerProtocol
from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.tools.base_tool import BaseTool

# Per-agent result summary limit (chars). If a sub-agent's final_message
# exceeds this, the full result is persisted to disk and the inline version
# is truncated with a pointer to the file.
_INLINE_RESULT_LIMIT = 3000


class ParallelAgentTool(BaseTool):
    """Execute multiple sub-agent missions in parallel.

    This tool accepts a list of missions and dispatches them concurrently
    to sub-agents, respecting a configurable concurrency limit. Each mission
    can target a different specialist. Partial failures do not cancel
    sibling agents — all results are collected and returned.
    """

    tool_name = "call_agents_parallel"
    tool_description = (
        "Execute multiple sub-agent missions in parallel. "
        "Use this when you have several independent tasks that can run concurrently. "
        "Each mission can target a different specialist (e.g., 'coding_worker'). "
        "Results are aggregated and returned as a batch. "
        "Partial failures do not cancel other agents. "
        "IMPORTANT: Sub-agents cannot see the current conversation. "
        "Include ALL relevant context in the mission string: file paths, "
        "user instructions, and any data the sub-agent needs to complete the task."
    )
    tool_parameters_schema = {
        "type": "object",
        "properties": {
            "missions": {
                "type": "array",
                "description": (
                    "List of missions to execute in parallel. "
                    "Each item specifies a mission and optional specialist."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "mission": {
                            "type": "string",
                            "description": (
                                "Clear, specific mission description. "
                                "MUST include all context the sub-agent needs: "
                                "file paths, URLs, data extracts, user preferences. "
                                "The sub-agent cannot see the parent conversation."
                            ),
                        },
                        "specialist": {
                            "type": "string",
                            "description": (
                                "Specialist profile or custom agent ID "
                                "(e.g., 'pc-agent', 'research_agent', "
                                "'coding_agent')."
                            ),
                        },
                        "planning_strategy": {
                            "type": "string",
                            "description": "Optional planning strategy override.",
                            "enum": [
                                "native_react",
                                "plan_and_execute",
                                "plan_and_react",
                                "spar",
                            ],
                        },
                    },
                    "required": ["mission"],
                },
            },
            "max_concurrency": {
                "type": "integer",
                "description": (
                    "Maximum number of sub-agents running at the same time. " "Defaults to 3."
                ),
                "default": 3,
            },
        },
        "required": ["missions"],
    }

    # The tool manages parallelism internally — no approval needed at parent level.
    # Sub-agents enforce their own tool-level approval internally.
    tool_requires_approval = False
    tool_approval_risk_level = ApprovalRiskLevel.MEDIUM
    tool_supports_parallelism = False  # Manages its own parallelism

    def __init__(
        self,
        sub_agent_spawner: SubAgentSpawnerProtocol,
        *,
        profile: str = "dev",
        work_dir: str | None = None,
        max_steps: int | None = None,
        default_max_concurrency: int = 3,
    ) -> None:
        """Initialize ParallelAgentTool.

        Args:
            sub_agent_spawner: Spawner for creating sub-agents.
            profile: Default profile for sub-agents.
            work_dir: Optional work directory override.
            max_steps: Optional max steps override per sub-agent.
            default_max_concurrency: Default concurrency limit.
        """
        self._spawner = sub_agent_spawner
        self._profile = profile
        self._work_dir = work_dir
        self._max_steps = max_steps
        self._default_max_concurrency = default_max_concurrency
        self._logger = structlog.get_logger().bind(component="parallel_agent_tool")

    @property
    def requires_parent_session(self) -> bool:
        """Marker: this tool needs _parent_session_id injection."""
        return True

    async def _execute(self, **kwargs: Any) -> dict[str, Any]:
        """Execute multiple sub-agent missions in parallel."""
        missions: list[dict[str, Any]] = kwargs.get("missions", [])
        max_concurrency = int(kwargs.get("max_concurrency", self._default_max_concurrency))
        parent_session = kwargs.get("_parent_session_id", "unknown")
        parent_event_sink = kwargs.get("_parent_event_sink")
        parent_agent_path: list[str] = list(kwargs.get("_parent_agent_path", []) or [])

        if not missions:
            return {"success": False, "error": "No missions provided."}

        self._logger.info(
            "parallel_dispatch_start",
            mission_count=len(missions),
            max_concurrency=max_concurrency,
            parent_session=parent_session,
        )

        # ctxman frames are LIFO-only: concurrent siblings cannot share the
        # parent's session as frames. Clear any inherited frame binding so
        # each parallel sub-agent gets its own ctxman session instead.
        from taskforce.infrastructure.context.frame_binding import (
            reset_frame_binding,
            set_frame_binding,
        )

        binding_token = set_frame_binding(None)
        try:
            semaphore = asyncio.Semaphore(max_concurrency)
            tasks = [
                self._run_with_semaphore(
                    semaphore,
                    mission_spec,
                    parent_session,
                    parent_event_sink,
                    parent_agent_path,
                )
                for mission_spec in missions
            ]

            raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            reset_frame_binding(binding_token)

        results = []
        for i, raw in enumerate(raw_results):
            if isinstance(raw, BaseException):
                results.append(
                    {
                        "mission": missions[i].get("mission", ""),
                        "specialist": missions[i].get("specialist"),
                        "success": False,
                        "error": str(raw),
                        "error_kind": "exception",
                    }
                )
            else:
                results.append(raw)

        succeeded = sum(1 for r in results if r.get("success"))
        failed = len(results) - succeeded

        self._logger.info(
            "parallel_dispatch_complete",
            total=len(results),
            succeeded=succeeded,
            failed=failed,
        )

        # Build compact results: persist large outputs to disk, keep inline summaries
        compact_results = []
        for r in results:
            compact_results.append(self._compact_result(r, parent_session))

        return {
            "success": failed == 0,
            "total": len(results),
            "succeeded": succeeded,
            "failed": failed,
            "results": compact_results,
        }

    def _resolve_result_dir(self) -> Path:
        """Resolve the directory where oversized sub-agent results land.

        Consults
        :func:`taskforce.application.infrastructure_overrides.get_sub_agent_result_dir_override`
        at *write-time* (not at tool construction) so a process-
        shared tool instance can still route per-(tenant, user) when
        the enterprise plugin is loaded. Falls back to
        ``<self._work_dir or ".taskforce">/sub_agent_results`` when
        no override is installed — bit-for-bit pre-#212 behaviour.

        Error handling (#222) separates two cases:

        * ``ImportError`` from the framework module — an older
          framework genuinely lacks the hook; fall back silently so
          the tool still works.
        * Any other exception from the provider call — log at ERROR
          level with the traceback and fall back. ERROR (not warning)
          because a misbehaving provider in production is a real bug
          a operator must see in a log scan; the previous
          warning-and-shrug masked rename regressions inside the
          framework.
        """
        try:
            from taskforce.application.infrastructure_overrides import (
                get_sub_agent_result_dir_override,
            )
        except ImportError:
            return Path(self._work_dir or ".taskforce") / "sub_agent_results"

        try:
            override = get_sub_agent_result_dir_override()
            if override is not None:
                resolved = override()
                if resolved is not None:
                    return Path(resolved)
        except Exception:
            self._logger.error(
                "parallel_agent_tool.result_dir_override_failed",
                exc_info=True,
            )
        return Path(self._work_dir or ".taskforce") / "sub_agent_results"

    def _compact_result(self, result: dict[str, Any], parent_session: str) -> dict[str, Any]:
        """Compact a sub-agent result for the calling agent's context.

        If the result text is small enough, return it inline unchanged.
        If it exceeds _INLINE_RESULT_LIMIT, persist the full result to a
        file and return a truncated inline version with a file pointer.
        The full result is NEVER lost — it is always on disk.
        """
        full_text = result.get("result") or ""
        if not full_text or len(full_text) <= _INLINE_RESULT_LIMIT:
            return result

        # Persist full result to disk
        specialist = result.get("specialist") or "agent"
        session_id = result.get("session_id") or "unknown"
        result_dir = self._resolve_result_dir()
        result_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{specialist}_{session_id[-8:]}.md"
        result_path = result_dir / filename
        result_path.write_text(full_text, encoding="utf-8")

        self._logger.info(
            "sub_agent_result_persisted",
            specialist=specialist,
            path=str(result_path),
            full_chars=len(full_text),
            inline_chars=_INLINE_RESULT_LIMIT,
        )

        # Truncate inline and append pointer
        truncated = full_text[:_INLINE_RESULT_LIMIT]
        truncated += (
            f"\n\n[... truncated at {_INLINE_RESULT_LIMIT} chars, "
            f"full result ({len(full_text)} chars) saved to: {result_path}]"
        )

        return {**result, "result": truncated}

    async def _run_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        mission_spec: dict[str, Any],
        parent_session: str,
        parent_event_sink: asyncio.Queue | None,
        parent_agent_path: list[str],
    ) -> dict[str, Any]:
        """Run a single sub-agent mission with semaphore-controlled concurrency."""
        async with semaphore:
            mission = mission_spec.get("mission", "")
            specialist = mission_spec.get("specialist")
            planning_strategy = mission_spec.get("planning_strategy")

            spec = SubAgentSpec(
                mission=mission,
                parent_session_id=parent_session,
                specialist=specialist,
                planning_strategy=planning_strategy,
                profile=self._profile,
                work_dir=self._work_dir,
                max_steps=self._max_steps,
                parent_event_sink=parent_event_sink,
                parent_agent_path=list(parent_agent_path),
            )

            result = await self._spawner.spawn(spec)

            entry: dict[str, Any] = {
                "mission": mission,
                "specialist": specialist,
                "success": result.success,
                "session_id": result.session_id,
                "status": result.status,
                "result": result.final_message,
                "error": result.error,
                "error_kind": result.error_kind,
            }
            # Attach context snapshot for parent /tree inspection
            if result.context_snapshot is not None:
                entry["context_snapshot"] = result.context_snapshot
            return entry
