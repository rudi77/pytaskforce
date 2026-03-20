"""
Parallel Agent Tool - Execute multiple sub-agent missions concurrently.

Provides a single tool call that spawns N sub-agents in parallel,
controlled by a configurable concurrency limit. Results are aggregated
and returned as a batch.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from taskforce.core.domain.sub_agents import SubAgentSpec
from taskforce.core.interfaces.sub_agents import SubAgentSpawnerProtocol
from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.tools.base_tool import BaseTool


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
        "Partial failures do not cancel other agents."
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
                            "description": "Clear, specific mission description.",
                        },
                        "specialist": {
                            "type": "string",
                            "description": (
                                "Specialist profile or custom agent ID "
                                "(e.g., 'web-agent', 'research_agent', "
                                "'coding_agent', 'analysis_agent')."
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
                    "Maximum number of sub-agents running at the same time. "
                    "Defaults to 3."
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

        if not missions:
            return {"success": False, "error": "No missions provided."}

        self._logger.info(
            "parallel_dispatch_start",
            mission_count=len(missions),
            max_concurrency=max_concurrency,
            parent_session=parent_session,
        )

        semaphore = asyncio.Semaphore(max_concurrency)
        tasks = [
            self._run_with_semaphore(semaphore, mission_spec, parent_session)
            for mission_spec in missions
        ]

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        results = []
        for i, raw in enumerate(raw_results):
            if isinstance(raw, BaseException):
                results.append({
                    "mission": missions[i].get("mission", ""),
                    "specialist": missions[i].get("specialist"),
                    "success": False,
                    "error": str(raw),
                })
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

        return {
            "success": failed == 0,
            "total": len(results),
            "succeeded": succeeded,
            "failed": failed,
            "results": results,
        }

    async def _run_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        mission_spec: dict[str, Any],
        parent_session: str,
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
            )

            result = await self._spawner.spawn(spec)

            return {
                "mission": mission,
                "specialist": specialist,
                "success": result.success,
                "session_id": result.session_id,
                "status": result.status,
                "result": result.final_message,
                "error": result.error,
            }
