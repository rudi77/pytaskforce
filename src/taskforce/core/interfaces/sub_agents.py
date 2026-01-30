"""Protocol definitions for sub-agent orchestration."""

from __future__ import annotations

from typing import Protocol

from taskforce.core.domain.sub_agents import SubAgentResult, SubAgentSpec


class SubAgentSpawnerProtocol(Protocol):
    """Protocol for creating sub-agents."""

    async def spawn(self, spec: SubAgentSpec) -> SubAgentResult:
        """Spawn and execute a sub-agent based on the spec."""
        ...
