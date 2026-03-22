"""Sub-agent spawning helpers for orchestration workflows."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiofiles
import structlog
import yaml

from taskforce.core.domain.enums import ExecutionStatus
from taskforce.core.domain.sub_agents import (
    SubAgentResult,
    SubAgentSpec,
    build_sub_agent_session_id,
)
from taskforce.core.interfaces.sub_agents import SubAgentSpawnerProtocol
from taskforce.core.interfaces.tools import ToolProtocol

if TYPE_CHECKING:
    from taskforce.application.factory import AgentFactory
    from taskforce.core.domain.agent import Agent


class SubAgentSpawner(SubAgentSpawnerProtocol):
    """Spawn sub-agents using the AgentFactory."""

    def __init__(
        self,
        agent_factory: AgentFactory,
        *,
        profile: str = "dev",
        work_dir: str | None = None,
        max_steps: int | None = None,
        tool_overrides: list[ToolProtocol] | None = None,
    ) -> None:
        self._agent_factory = agent_factory
        self._profile = profile
        self._work_dir = work_dir
        self._max_steps = max_steps
        self._tool_overrides = tool_overrides
        self._logger = structlog.get_logger().bind(component="SubAgentSpawner")

    async def spawn(self, spec: SubAgentSpec) -> SubAgentResult:
        session_id = build_sub_agent_session_id(
            spec.parent_session_id,
            spec.specialist or "generic",
        )
        try:
            agent = await self._create_agent(spec)
            if self._tool_overrides:
                self._apply_tool_overrides(agent)
            if spec.max_steps:
                agent.max_steps = spec.max_steps
            elif self._max_steps:
                agent.max_steps = self._max_steps
            try:
                result = await agent.execute(mission=spec.mission, session_id=session_id)
            finally:
                await agent.close()
        except Exception as exc:
            self._logger.error(
                "sub_agent_spawn_failed",
                session_id=session_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return SubAgentResult(
                session_id=session_id,
                status=ExecutionStatus.FAILED.value,
                success=False,
                final_message="",
                error=str(exc),
            )

        success = result.status in {
            ExecutionStatus.COMPLETED.value,
            ExecutionStatus.PAUSED.value,
        }
        return SubAgentResult(
            session_id=session_id,
            status=result.status,
            success=success,
            final_message=result.final_message or "",
            error=None if success else result.final_message,
        )

    def _apply_tool_overrides(self, agent: Agent) -> None:
        """Replace agent tools with override instances.

        Used when sub-agents must share specific tool instances with
        their parent (e.g. sandbox-aware tools in SWE-bench evaluation).
        """
        from taskforce.core.domain.lean_agent_components.tool_executor import (
            ToolExecutor,
        )
        from taskforce.core.tools.tool_converter import tools_to_openai_format

        tools_dict = {t.name: t for t in self._tool_overrides}
        agent._planner = None
        agent.tools = tools_dict
        agent._openai_tools = tools_to_openai_format(agent.tools)
        agent.tool_executor = ToolExecutor(
            tools=agent.tools, logger=agent.logger
        )
        agent.message_history_manager._openai_tools = agent._openai_tools
        self._logger.debug(
            "tool_overrides_applied",
            tool_names=[t.name for t in self._tool_overrides],
        )

    async def _create_agent(self, spec: SubAgentSpec) -> Agent:
        profile = spec.profile or self._profile
        work_dir = spec.work_dir or self._work_dir

        # Prefer loading as config file to get full settings (context_management,
        # context_policy, etc.) rather than the inline path which drops fields.
        if spec.specialist:
            config_path = self._find_agent_config(spec.specialist)
            if config_path:
                return await self._agent_factory.create_agent(
                    config=str(config_path),
                    work_dir=work_dir,
                    planning_strategy=spec.planning_strategy,
                )

        custom_definition = spec.agent_definition
        if custom_definition:
            # Fallback: inline parameters from agent_definition dict
            return await self._agent_factory.create_agent(
                system_prompt=custom_definition.get("system_prompt"),
                tools=custom_definition.get("tool_allowlist") or custom_definition.get("tools"),
                mcp_servers=custom_definition.get("mcp_servers"),
                llm=custom_definition.get("llm"),
                context_policy=custom_definition.get("context_policy"),
                work_dir=work_dir,
                planning_strategy=spec.planning_strategy,
                specialist=custom_definition.get("specialist"),
            )
        # Use profile config
        return await self._agent_factory.create_agent(
            config=profile,
            specialist=spec.specialist,
            work_dir=work_dir,
            planning_strategy=spec.planning_strategy,
        )

    async def _load_custom_definition(self, spec: SubAgentSpec) -> dict[str, Any] | None:
        if not spec.specialist:
            return None
        config_path = self._find_agent_config(spec.specialist)
        if not config_path:
            return None
        async with aiofiles.open(config_path, encoding="utf-8") as handle:
            content = await handle.read()
            return yaml.safe_load(content) or None

    def _find_agent_config(self, specialist: str) -> Path | None:
        config_dir = Path(self._agent_factory.config_dir)
        for path in self._candidate_paths(config_dir, specialist):
            if path.exists():
                return path
        return None

    def _candidate_paths(self, config_dir: Path, specialist: str) -> list[Path]:
        candidates = [
            config_dir / "custom" / f"{specialist}.yaml",
            config_dir / "custom" / specialist / f"{specialist}.yaml",
        ]
        candidates.extend(self._plugin_candidates(config_dir, specialist))
        return candidates

    def _plugin_candidates(self, config_dir: Path, specialist: str) -> list[Path]:
        plugin_dirs = self._plugin_directories(config_dir)
        return [
            plugin / "configs" / "agents" / f"{specialist}.yaml"
            for plugin in plugin_dirs
            if plugin.is_dir()
        ]

    def _plugin_directories(self, config_dir: Path) -> list[Path]:
        plugin_roots = [config_dir.parent / "plugins", config_dir / "plugins"]
        for parent in config_dir.parents:
            plugin_roots.append(parent / "plugins")
        roots = [root for root in plugin_roots if root.exists()]
        directories: list[Path] = []
        for root in roots:
            directories.extend([path for path in root.iterdir() if path.is_dir()])
        return directories
