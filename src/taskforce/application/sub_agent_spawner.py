"""Sub-agent spawning helpers for orchestration workflows."""

from __future__ import annotations

import threading
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
from taskforce.infrastructure.tools.orchestration._event_forwarding import (
    run_sub_agent_with_forwarding,
)

if TYPE_CHECKING:
    from taskforce.application.factory import AgentFactory
    from taskforce.core.domain.agent import Agent


# Process-wide registry of running sub-agents keyed by their parent's
# session_id. Multiple SubAgentSpawner instances exist (one per
# orchestration tool build), but interrupt propagation is a cross-cutting
# concern: when the AgentExecutor receives ``interrupt(parent_session_id)``
# it consults this registry to forward the cooperative-pause signal to
# every running child.
_ACTIVE_CHILDREN: dict[str, list[Agent]] = {}
# Parents whose interrupt has already been requested. Tracked so children
# spawned *after* the interrupt is signalled still get the pause request.
# Cleared automatically when the last child of a parent deregisters.
_INTERRUPTED_PARENTS: set[str] = set()
_ACTIVE_CHILDREN_LOCK = threading.Lock()


def _register_child(parent_session_id: str, child: Agent) -> bool:
    """Register a child for a parent. Returns True if the parent is already
    flagged as interrupted (so the caller can immediately signal the child).
    """
    with _ACTIVE_CHILDREN_LOCK:
        _ACTIVE_CHILDREN.setdefault(parent_session_id, []).append(child)
        return parent_session_id in _INTERRUPTED_PARENTS


def _deregister_child(parent_session_id: str, child: Agent) -> None:
    with _ACTIVE_CHILDREN_LOCK:
        children = _ACTIVE_CHILDREN.get(parent_session_id)
        if not children:
            return
        try:
            children.remove(child)
        except ValueError:
            pass
        if not children:
            _ACTIVE_CHILDREN.pop(parent_session_id, None)
            _INTERRUPTED_PARENTS.discard(parent_session_id)


def request_interrupt_for_parent(parent_session_id: str) -> int:
    """Forward a cooperative-pause request to every running sub-agent.

    Called by :meth:`AgentExecutor.interrupt` so an interrupt on the root
    session also pauses any sub-agents spawned by orchestration tools
    (``call_agent``, ``call_agents_parallel``). Future children spawned
    while the parent is still flagged also receive the signal.

    Returns the number of children that were signalled.
    """
    with _ACTIVE_CHILDREN_LOCK:
        _INTERRUPTED_PARENTS.add(parent_session_id)
        children = list(_ACTIVE_CHILDREN.get(parent_session_id, ()))
    for child in children:
        try:
            child.request_interrupt()
        except Exception:  # pragma: no cover — best-effort propagation
            pass
    return len(children)


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
        propagate_complexity: bool = False,
    ) -> None:
        self._agent_factory = agent_factory
        self._profile = profile
        self._work_dir = work_dir
        self._max_steps = max_steps
        self._tool_overrides = tool_overrides
        self._propagate_complexity = propagate_complexity
        self._complexity_override: str | None = None
        self._logger = structlog.get_logger().bind(component="SubAgentSpawner")

    async def spawn(self, spec: SubAgentSpec) -> SubAgentResult:
        session_id = build_sub_agent_session_id(
            spec.parent_session_id,
            spec.specialist or "generic",
        )
        self._logger.info(
            "sub_agent_session",
            session_id=session_id,
            specialist=spec.specialist,
            reusing_session=True,  # Deterministic IDs mean we always try to resume
        )
        context_snapshot = None
        try:
            agent = await self._create_agent(spec)
            if self._tool_overrides:
                self._apply_tool_overrides(agent)
            if spec.max_steps:
                agent.max_steps = spec.max_steps
            elif self._max_steps:
                agent.max_steps = self._max_steps
            # Inherit parent's complexity override to sub-agent router
            self._propagate_complexity_override(agent)
            # Clear stale ask_user state so new missions are not
            # misinterpreted as answers to a previous question.
            await self._clear_stale_pause(agent, session_id, spec.mission)
            # Register the child so a parent's cooperative interrupt
            # (ADR-019) propagates to this sub-agent. If the parent is
            # already interrupted, signal the child immediately so it
            # pauses at its first ReAct boundary instead of running a
            # full extra step.
            parent_already_interrupted = _register_child(
                spec.parent_session_id, agent
            )
            try:
                if parent_already_interrupted:
                    agent.request_interrupt()
                outcome = await run_sub_agent_with_forwarding(
                    agent,
                    mission=spec.mission,
                    session_id=session_id,
                    parent_session_id=spec.parent_session_id,
                    parent_event_sink=spec.parent_event_sink,
                    parent_agent_path=spec.parent_agent_path,
                    specialist=spec.specialist,
                )
                # Capture context snapshot before closing the agent
                if hasattr(agent, "context") and agent.context.is_initialized:
                    context_snapshot = agent.context.snapshot(
                        include_content=True,
                        skill_manager=agent.skill_manager,
                        memory_context=getattr(agent, "_memory_context", None),
                    )
            finally:
                _deregister_child(spec.parent_session_id, agent)
                await agent.close()
        except Exception as exc:
            import traceback

            self._logger.error(
                "sub_agent_spawn_failed",
                session_id=session_id,
                error=str(exc),
                error_type=type(exc).__name__,
                traceback=traceback.format_exc(),
            )
            return SubAgentResult(
                session_id=session_id,
                status=ExecutionStatus.FAILED.value,
                success=False,
                final_message="",
                error=str(exc),
                error_kind="spawn_failed",
            )

        success = outcome.success
        # Prefer the structured ERROR-event message over final_message for
        # the ``error`` field — when the LLM stream gets aborted (content
        # filter, repeated provider errors) the agent never produces a
        # final_message, but the outcome still carries the cause.
        # Both ``error`` and ``error_kind`` must clear on success, otherwise
        # a transient mid-run ERROR followed by a recovered FINAL_ANSWER
        # would still tag the result with a stale error category.
        if success:
            error_text: str | None = None
            error_kind: str | None = None
        else:
            error_text = outcome.error_message or outcome.final_message or None
            error_kind = outcome.error_kind or None
        return SubAgentResult(
            session_id=session_id,
            status=outcome.status,
            success=success,
            final_message=outcome.final_message or "",
            error=error_text,
            error_kind=error_kind,
            context_snapshot=context_snapshot,
        )

    async def _clear_stale_pause(
        self, agent: Agent, session_id: str, mission: str
    ) -> None:
        """Clear stale ``pending_question`` state so a new mission is not
        misinterpreted as an answer to a previous ``ask_user`` question.

        When the sub-agent session is deterministic (reused across parent
        invocations), an old ``ask_user`` pause may still be persisted.
        If we simply call ``agent.execute(mission=...)``, the resume logic
        treats the new mission text as the user's answer — which corrupts
        the conversation and often triggers content-policy violations from
        the LLM provider.

        This method detects and clears the stale state *before* execute().
        """
        try:
            state = await agent.state_manager.load_state(session_id)
        except Exception:
            return  # No state yet — nothing to clear

        if not state or state.get("pending_question") is None:
            return

        # State has a pending question from a previous run — clear it.
        for key in [
            "pending_question",
            "paused_messages",
            "paused_tool_call_id",
            "paused_step",
            "paused_plan",
            "paused_plan_step_idx",
            "paused_plan_iteration",
            "paused_phase",
        ]:
            state.pop(key, None)

        # Also clear conversation history so the new mission starts fresh
        state.pop("conversation_history", None)

        await agent.state_manager.save_state(session_id, state)
        self._logger.info(
            "stale_pause_cleared",
            session_id=session_id,
            mission_preview=mission[:80],
        )

    def _propagate_complexity_override(self, agent: Agent) -> None:
        """Optionally copy parent's complexity classification to sub-agent's router.

        Disabled by default (``propagate_complexity=False``).  Sub-agents are
        specialized and need their configured model to work correctly — e.g.
        the accountant does multi-step OCR + Excel + archival, which fails
        badly when downgraded to a nano model.
        """
        if not self._propagate_complexity:
            self._logger.debug(
                "complexity_override_skipped",
                reason="sub_agents_use_own_model",
                parent_override=self._complexity_override,
            )
            return
        if not self._complexity_override:
            return
        from taskforce.infrastructure.llm.llm_router import LLMRouter

        if isinstance(agent.llm_provider, LLMRouter):
            agent.llm_provider.complexity_override = self._complexity_override
            self._logger.debug(
                "complexity_override_propagated",
                override=self._complexity_override,
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
        agent.tool_executor = ToolExecutor(tools=agent.tools, logger=agent.logger)
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
        # Refuse to silently fall back to the parent profile when a specialist
        # was explicitly requested — that path causes infinite recursion when
        # e.g. butler delegates to ``coding_agent`` and the resolver only finds
        # the parent profile. Surfacing the error makes the misconfiguration
        # visible instead of looping until the stream gets cancelled.
        if spec.specialist and spec.specialist != profile:
            raise ValueError(
                f"No agent config found for specialist {spec.specialist!r}. "
                "Add a profile YAML under agents/<pkg>/configs/, "
                "agents/<pkg>/configs/custom/, or "
                f"{Path(self._agent_factory.config_dir) / 'custom'}."
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
            # Top-level profiles in the parent's own configs/ (e.g. butler.yaml)
            config_dir / f"{specialist}.yaml",
            config_dir / f"{specialist}.agent.md",
        ]
        # Search agent package config directories (agents/*/configs[/custom]/)
        from taskforce.core.utils.paths import get_base_path

        agents_dir = get_base_path() / "agents"
        if agents_dir.is_dir():
            for agent_dir in agents_dir.iterdir():
                agent_configs = agent_dir / "configs"
                if not agent_configs.is_dir():
                    continue
                # Top-level package profile (e.g. agents/coding-agent/configs/coding_agent.yaml)
                candidates.append(agent_configs / f"{specialist}.yaml")
                candidates.append(agent_configs / f"{specialist}.agent.md")
                # Nested custom/ directory
                agent_custom = agent_configs / "custom"
                if agent_custom.is_dir():
                    candidates.append(agent_custom / f"{specialist}.yaml")
                    candidates.append(
                        agent_custom / specialist / f"{specialist}.yaml"
                    )
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
