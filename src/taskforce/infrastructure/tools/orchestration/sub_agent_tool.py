"""
Sub-Agent Tool

Provides a tool wrapper that delegates to a specific sub-agent.
Each instance represents one specialist, exposing a simple mission-only interface.
"""

from __future__ import annotations

from typing import Any

from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.tools.orchestration.agent_tool import AgentTool


class SubAgentTool:
    """Tool wrapper that runs a fixed sub-agent via AgentTool."""

    def __init__(
        self,
        agent_tool: AgentTool,
        specialist: str,
        name: str,
        description: str | None = None,
        planning_strategy: str | None = None,
    ) -> None:
        self._agent_tool = agent_tool
        self._specialist = specialist
        self._name = name
        self._description = (
            description
            or f"Delegate a mission to the '{specialist}' sub-agent."
        )
        self._planning_strategy = planning_strategy

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mission": {
                    "type": "string",
                    "description": (
                        "Clear, specific mission description for the sub-agent."
                    ),
                },
            },
            "required": ["mission"],
        }

    @property
    def requires_approval(self) -> bool:
        return True

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.MEDIUM

    @property
    def supports_parallelism(self) -> bool:
        return True

    @property
    def requires_parent_session(self) -> bool:
        """Marker: this tool needs _parent_session_id injection."""
        return True

    async def execute(
        self,
        mission: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await self._agent_tool.execute(
            mission=mission,
            specialist=self._specialist,
            planning_strategy=self._planning_strategy,
            **kwargs,
        )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        mission = kwargs.get("mission")
        if not mission or not mission.strip():
            return False, "Missing or empty required parameter: mission"
        return True, None
