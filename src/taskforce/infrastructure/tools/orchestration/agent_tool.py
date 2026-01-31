"""
Agent Tool - Multi-Agent Orchestration

Enables an orchestrator agent to delegate missions to specialist sub-agents.
Each sub-agent runs in an isolated session with its own context, tools, and state.

This tool implements the "Agents as Tools" pattern for multi-agent coordination,
allowing parallel execution of sub-agents and hierarchical session management.
"""

import uuid
from pathlib import Path
from typing import Any, Optional

import structlog

from taskforce.core.domain.sub_agents import SubAgentSpec
from taskforce.core.interfaces.sub_agents import SubAgentSpawnerProtocol
from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol


class AgentTool:
    """
    Tool that delegates missions to specialist sub-agents.

    Allows an orchestrator agent to spawn and execute sub-agents
    with different specialist profiles, tools, and system prompts.

    Each sub-agent execution:
    - Gets isolated session ID (parent_session:sub_{specialist}_{uuid})
    - Has own state management
    - Runs independently with specialist toolset
    - Returns ExecutionResult to parent agent

    Architecture:
        Orchestrator Agent
            └─> AgentTool.execute()
                └─> AgentFactory.create_agent()
                    └─> Sub-Agent.execute()
                        └─> Returns result to orchestrator

    Session Hierarchy:
        - Parent: "session-123"
        - Sub-Agent 1: "session-123:sub_coding_a1b2c3d4"
        - Sub-Agent 2: "session-123:sub_rag_e5f6g7h8"
    """

    def __init__(
        self,
        agent_factory: "AgentFactory",  # type: ignore # noqa: F821
        sub_agent_spawner: SubAgentSpawnerProtocol | None = None,
        profile: str = "dev",
        work_dir: Optional[str] = None,
        max_steps: Optional[int] = None,
        summarize_results: bool = False,
        summary_max_length: int = 2000,
    ):
        """
        Initialize AgentTool with factory for creating sub-agents.

        Args:
            agent_factory: Factory for creating sub-agents
            profile: Configuration profile for sub-agents (dev/staging/prod)
            work_dir: Optional work directory override for sub-agents
            max_steps: Optional max steps override for sub-agents
            summarize_results: Whether to summarize long sub-agent results
            summary_max_length: Max chars before summarization kicks in
        """
        self._factory = agent_factory
        self._spawner = sub_agent_spawner
        self._profile = profile
        self._work_dir = work_dir
        self._max_steps = max_steps
        self._summarize_results = summarize_results
        self._summary_max_length = summary_max_length
        self.logger = structlog.get_logger().bind(component="agent_tool")

    @property
    def name(self) -> str:
        return "call_agent"

    @property
    def description(self) -> str:
        return (
            "Delegate a mission to a specialist sub-agent. "
            "Use this when you need specialized capabilities not available in your current toolset. "
            "Available specialists: "
            "'coding' (file operations, shell commands, git), "
            "'rag' (semantic search, document retrieval), "
            "'wiki' (Wikipedia research). "
            "You can also use custom agent IDs from configs/custom/ (e.g., 'german_tax_expert'). "
            "The sub-agent will execute the mission independently and return results. "
            "Sub-agents can run in parallel for independent tasks."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mission": {
                    "type": "string",
                    "description": (
                        "Clear, specific mission description for the sub-agent. "
                        "Include all necessary context, constraints, and expected output format."
                    ),
                },
                "specialist": {
                    "type": "string",
                    "description": (
                        "Specialist profile or custom agent ID. "
                        "Standard specialists: 'coding', 'rag', 'wiki'. "
                        "Custom agents: any ID from configs/custom/ (e.g., 'code_reviewer'). "
                        "Choose based on mission requirements."
                    ),
                },
                "planning_strategy": {
                    "type": "string",
                    "description": (
                        "Optional planning strategy for sub-agent: "
                        "'native_react' (default - best for most tasks), "
                        "'plan_and_execute' (create full plan upfront, then execute), "
                        "'plan_and_react' (hybrid approach)"
                    ),
                    "enum": ["native_react", "plan_and_execute", "plan_and_react"],
                },
            },
            "required": ["mission"],
        }

    @property
    def requires_approval(self) -> bool:
        # Sub-agent spawning requires approval (sub-agent may execute risky tools)
        return True

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        # Medium risk: sub-agent has limited toolset, but can still modify files
        return ApprovalRiskLevel.MEDIUM

    @property
    def supports_parallelism(self) -> bool:
        # Sub-agents can run in parallel (isolated sessions)
        return True

    def get_approval_preview(self, **kwargs: Any) -> str:
        """Generate approval preview for sub-agent execution."""
        specialist = kwargs.get("specialist", "generic")
        mission = kwargs.get("mission", "")
        mission_preview = mission[:150] + "..." if len(mission) > 150 else mission

        return (
            f"🤖 SUB-AGENT EXECUTION\n"
            f"Tool: {self.name}\n"
            f"Specialist: {specialist}\n"
            f"Mission: {mission_preview}\n"
            f"Risk: Sub-agent will have access to its specialist toolset"
        )

    def _find_agent_config(self, specialist: str) -> Path | None:
        """
        Find agent config file by specialist name.

        Search order:
        1. configs/custom/{specialist}.yaml - Single file custom agent
        2. configs/custom/{specialist}/ - Directory-based custom agent
        3. plugins/*/configs/agents/{specialist}.yaml - Plugin agents

        Args:
            specialist: The specialist/agent name to search for

        Returns:
            Path to config file if found, None otherwise.
        """
        config_dir = self._factory.config_dir

        # 1. Check configs/custom/{specialist}.yaml
        custom_path = config_dir / "custom" / f"{specialist}.yaml"
        if custom_path.exists():
            return custom_path

        # 2. Check configs/custom/{specialist}/ directory
        custom_dir = config_dir / "custom" / specialist
        if custom_dir.is_dir():
            # Look for {specialist}.yaml in the directory
            custom_dir_path = custom_dir / f"{specialist}.yaml"
            if custom_dir_path.exists():
                return custom_dir_path
            # Fallback: return first .yaml file found
            for yaml_file in custom_dir.glob("*.yaml"):
                return yaml_file

        # 3. Check plugins/*/configs/agents/{specialist}.yaml
        # Try new location first: src/taskforce_extensions/plugins
        # Then old location: plugins/ (for backward compatibility)
        plugins_dirs = []
        
        # New location: if config_dir is src/taskforce_extensions/configs, plugins is sibling
        if config_dir.name == "configs" and config_dir.parent.name == "taskforce_extensions":
            plugins_dirs.append(config_dir.parent / "plugins")
        
        # Old location: plugins/ at project root (sibling of configs)
        plugins_dirs.append(config_dir.parent / "plugins")
        
        # Also check project root plugins if config_dir is nested
        project_root_plugins = config_dir
        # Navigate up to find project root (where plugins/ might be)
        for _ in range(5):  # Max depth check
            if (project_root_plugins / "plugins").exists():
                plugins_dirs.append(project_root_plugins / "plugins")
                break
            if project_root_plugins.parent == project_root_plugins:  # Reached filesystem root
                break
            project_root_plugins = project_root_plugins.parent
        
        for plugins_dir in plugins_dirs:
            if plugins_dir.exists():
                for plugin_dir in plugins_dir.iterdir():
                    if plugin_dir.is_dir():
                        agent_config = plugin_dir / "configs" / "agents" / f"{specialist}.yaml"
                        if agent_config.exists():
                            self.logger.debug(
                                "found_plugin_agent_config",
                                specialist=specialist,
                                plugin=plugin_dir.name,
                                config_path=str(agent_config),
                            )
                            return agent_config

        return None

    async def execute(
        self,
        mission: str,
        specialist: Optional[str] = None,
        planning_strategy: Optional[str] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Execute mission in sub-agent with isolated context.

        Args:
            mission: Mission description for sub-agent
            specialist: Optional specialist profile ("coding", "rag", "wiki")
                       or custom agent ID from configs/custom/
            planning_strategy: Optional strategy override
            **kwargs: Additional parameters (includes _parent_session_id)

        Returns:
            Dictionary with:
            - success: bool - True if sub-agent completed successfully
            - result: str - Final answer from sub-agent
            - session_id: str - Sub-agent session ID
            - steps_taken: int - Number of execution steps
            - error: str - Error message (if failed)
        """
        # Get parent session from kwargs (injected by ToolExecutor)
        parent_session = kwargs.get("_parent_session_id", "unknown")

        # Generate unique session ID for sub-agent
        sub_session_suffix = specialist or "generic"
        sub_session_id = (
            f"{parent_session}:sub_{sub_session_suffix}_{uuid.uuid4().hex[:8]}"
        )

        try:
            if self._spawner:
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
                return self._format_spawner_result(result)

            self.logger.info(
                "spawning_sub_agent",
                parent_session=parent_session,
                sub_session_id=sub_session_id,
                specialist=specialist,
                mission_length=len(mission),
                hierarchy_level=parent_session.count(":") + 1,
            )

            # Create sub-agent based on specialist or custom profile
            if specialist:
                # Search for custom agent config in multiple locations
                custom_agent_path = self._find_agent_config(specialist)

                if custom_agent_path:
                    # Load custom agent from config file path
                    self.logger.debug(
                        "loading_custom_agent",
                        specialist=specialist,
                        config_path=str(custom_agent_path),
                    )

                    # Create agent from config file
                    sub_agent = await self._factory.create_agent(
                        config=str(custom_agent_path),
                        work_dir=self._work_dir,
                        planning_strategy=planning_strategy,
                    )
                else:
                    # Standard specialist agent (coding/rag/wiki)
                    sub_agent = await self._factory.create_agent(
                        config=self._profile,
                        specialist=specialist,
                        work_dir=self._work_dir,
                        planning_strategy=planning_strategy,
                    )
            else:
                # Generic agent (no specialist)
                sub_agent = await self._factory.create_agent(
                    config=self._profile,
                    work_dir=self._work_dir,
                    planning_strategy=planning_strategy,
                )

            # Override max_steps if configured
            if self._max_steps:
                sub_agent.max_steps = self._max_steps

            # Execute mission in sub-agent
            self.logger.debug(
                "executing_sub_agent_mission",
                sub_session_id=sub_session_id,
                max_steps=sub_agent.max_steps,
            )

            result = await sub_agent.execute(
                mission=mission,
                session_id=sub_session_id,
            )

            # Cleanup sub-agent resources (MCP connections, etc.)
            await sub_agent.cleanup()

            # Determine success based on status
            success = result.status in ("completed", "paused")

            self.logger.info(
                "sub_agent_completed",
                sub_session_id=sub_session_id,
                status=result.status,
                success=success,
            )

            # Prepare result for parent agent
            result_text = result.final_message or "No result"

            # Optionally summarize long results
            if (
                self._summarize_results
                and len(result_text) > self._summary_max_length
            ):
                self.logger.debug(
                    "summarizing_long_result",
                    original_length=len(result_text),
                    max_length=self._summary_max_length,
                )
                # TODO: Implement summarization via LLM
                # For now, just truncate
                result_text = (
                    result_text[: self._summary_max_length]
                    + f"\n\n[Result truncated - original length: {len(result_text)} chars]"
                )

            # Return result to parent agent
            return {
                "success": success,
                "result": result_text,
                "session_id": sub_session_id,
                "status": result.status,
                "error": result.final_message if not success else None,
            }

        except Exception as e:
            self.logger.error(
                "sub_agent_execution_failed",
                sub_session_id=sub_session_id,
                error=str(e),
                error_type=type(e).__name__,
            )

            return {
                "success": False,
                "error": f"Sub-agent execution failed: {str(e)}",
                "error_type": type(e).__name__,
                "session_id": sub_session_id,
            }

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        mission = kwargs.get("mission")

        if not mission or not mission.strip():
            return False, "Missing or empty required parameter: mission"

        # Validate planning_strategy if provided
        planning_strategy = kwargs.get("planning_strategy")
        if planning_strategy and planning_strategy not in [
            "native_react",
            "plan_and_execute",
            "plan_and_react",
        ]:
            return (
                False,
                f"Invalid planning_strategy: {planning_strategy}. Must be one of: native_react, plan_and_execute, plan_and_react",
            )

        return True, None

    def _format_spawner_result(self, result: Any) -> dict[str, Any]:
        if not hasattr(result, "session_id"):
            return {
                "success": False,
                "error": "Sub-agent spawner returned invalid result.",
                "error_type": "InvalidSubAgentResult",
                "session_id": "unknown",
            }
        success = getattr(result, "success", False)
        return {
            "success": success,
            "result": getattr(result, "final_message", "") or "No result",
            "session_id": getattr(result, "session_id", "unknown"),
            "status": getattr(result, "status", "unknown"),
            "error": None if success else getattr(result, "error", None),
        }
